"""Contract: la ingesta asíncrona de Keep (INFRA-1572, P2 de INFRA-1336).

Sin Redis, `receive_event` procesaba el evento en un ThreadPoolExecutor dentro
del worker gunicorn de keep-backend que sirve el webhook de Alertmanager: la
ráfaga saturaba el executor y el pool de Postgres del propio worker, y
Alertmanager abandonaba el POST perdiendo lotes (keep-hub-degraded e1144f20eb,
SC-5390). Con REDIS=true el handler responde 202 y encola a KEEP_ARQ_QUEUE_BASIC;
`keepsvc-worker` es el consumidor.

Lo que fija este test (y lo que rompe el orden si se pierde):

1. keep-backend: REDIS=true + REDIS_HOST, y `command` API-only — sin workers ARQ
   dentro del pod de la API. Con REDIS=true el entrypoint de la imagen arranca
   los suyos (KEEP_WORKERS default 2): dos consumidores reordenan la cola.
2. keepsvc-worker: consumidor ÚNICO FIFO — replicas=1, Recreate, gunicorn
   --workers 1 con la clase ARQGunicornWorker, KEEP_EVENT_WORKERS=1 y el pool
   basic_processing (el VALOR en minúsculas: otra cadena lanza ValueError y el
   worker se sale; consts.py lo compara literal).
3. keepsvc-redis: con AOF (appendonly yes) — un evento encolado no se pierde si
   Redis reinicia.
4. El tag de la imagen del worker va en pareja con el appVersion del chart.
5. keepsvc-scheduler sigue siendo el ÚNICO ejecutor de intervalos (contrato
   Aurora intacto): WORKFLOWS_INTERVAL_ENABLED=false en backend y worker.
"""

from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
VALUES = ROOT / "keep" / "values.yaml"
WORKER = ROOT / "keep" / "worker.yaml"
REDIS = ROOT / "keep" / "redis.yaml"
SCHEDULER = ROOT / "keep" / "scheduler.yaml"
APP = ROOT / "apps" / "keep.yaml"

# appVersion del chart keep por targetRevision (apps/keep.yaml). El chart vive
# fuera del repo (keephq.github.io/helm-charts): este mapa es el pin de la
# pareja chart<->imagen. Al subir `targetRevision`, actualizar aquí y los tags
# de keep/scheduler.yaml y keep/worker.yaml (falla si no lo haces).
CHART_APPVERSION = {"0.1.96": "0.52.1"}


def env_of(entries):
    return {e["name"]: e.get("value") for e in entries}


def deployment(path, name):
    for doc in yaml.safe_load_all(path.read_text()):
        if doc and doc.get("kind") == "Deployment" and doc["metadata"]["name"] == name:
            return doc
    raise AssertionError(f"Deployment {name} not found in {path.name}")


def docs(path):
    return [d for d in yaml.safe_load_all(path.read_text()) if d]


def container(doc):
    return doc["spec"]["template"]["spec"]["containers"][0]


class BackendIsNotAConsumer(unittest.TestCase):
    def setUp(self):
        self.values = yaml.safe_load(VALUES.read_text())
        self.backend = self.values["backend"]

    def test_backend_enqueues_to_redis(self):
        env = env_of(self.backend["env"])
        self.assertEqual(
            env.get("REDIS"), "true",
            "sin REDIS=true el POST /alerts/event/prometheus sigue procesando en "
            "el thread pool del worker de la API (la acoplación que INFRA-1336 "
            "elimina: keep-hub-degraded e1144f20eb)",
        )
        self.assertEqual(env.get("REDIS_HOST"), "keepsvc-redis")

    def test_backend_command_is_api_only(self):
        command = self.backend.get("command")
        self.assertTrue(command, "backend.command debe fijarse API-only: con "
                                 "REDIS=true el entrypoint de la imagen arranca 2 "
                                 "workers ARQ dentro del pod de la API, y dos "
                                 "consumidores reordenan la cola (orden "
                                 "firing→resolved)")
        joined = " ".join(str(part) for part in command)
        self.assertNotIn(
            "arq_worker", joined,
            "el command del backend no debe arrancar el worker ARQ de gunicorn",
        )
        self.assertIn("keep.api.api:get_app", joined)

    def test_backend_still_not_the_interval_executor(self):
        env = env_of(self.backend["env"])
        self.assertEqual(env.get("SCHEDULER"), "true")
        self.assertEqual(env.get("WORKFLOWS_INTERVAL_ENABLED"), "false")


class WorkerIsTheOnlyConsumer(unittest.TestCase):
    def setUp(self):
        self.doc = deployment(WORKER, "keepsvc-worker")
        self.c = container(self.doc)
        self.env = env_of(self.c["env"])

    def test_single_consumer_shape(self):
        self.assertEqual(self.doc["spec"]["replicas"], 1)
        self.assertEqual(self.doc["spec"]["strategy"]["type"], "Recreate",
                         "Recreate: RollingUpdate solapa dos consumidores y "
                         "rompe el orden FIFO firing→resolved")

    def test_serial_worker_process(self):
        joined = " ".join(str(part) for part in self.c["command"])
        self.assertIn("keep.api.arq_worker_gunicorn.ARQGunicornWorker", joined,
                      "clase real en keep 0.52.1 (keep/api/arq_worker_gunicorn.py)")
        self.assertIn("--workers 1", joined)
        self.assertEqual(self.env.get("KEEP_EVENT_WORKERS"), "1",
                         "pool interno de 1 hilo: serializa FIFO en orden de llegada")
        self.assertEqual(
            self.env.get("KEEP_ARQ_TASK_POOL"), "basic_processing",
            "el VALOR del pool en minúsculas (consts.py): otra cadena lanza "
            "ValueError y run_arq_worker sale con os._exit(1)",
        )

    def test_worker_reads_the_same_redis(self):
        self.assertEqual(self.env.get("REDIS"), "true")
        self.assertEqual(self.env.get("REDIS_HOST"), "keepsvc-redis")

    def test_worker_is_not_the_interval_executor(self):
        # El único ejecutor de intervalos sigue siendo keepsvc-scheduler
        # (contrato Aurora sin cambios).
        self.assertEqual(self.env.get("WORKFLOWS_INTERVAL_ENABLED"), "false")
        sched = env_of(container(deployment(SCHEDULER, "keepsvc-scheduler"))["env"])
        self.assertEqual(sched.get("WORKFLOWS_INTERVAL_ENABLED"), "true")

    def test_image_tag_paired_with_chart_appversion(self):
        app = yaml.safe_load(APP.read_text())
        chart_source = next(
            s for s in app["spec"]["sources"] if s.get("chart") == "keep"
        )
        chart_version = str(chart_source["targetRevision"])
        self.assertIn(
            chart_version, CHART_APPVERSION,
            f"chart keep {chart_version} sin appVersion fijado: actualizar "
            "CHART_APPVERSION y los tags de keep/scheduler.yaml y keep/worker.yaml",
        )
        expected = f"keep-api:{CHART_APPVERSION[chart_version]}"
        self.assertTrue(
            self.c["image"].endswith(expected),
            f"imagen del worker {self.c['image']} no va en pareja con el "
            f"appVersion del chart {chart_version} (esperado ...{expected})",
        )


class RedisQueueIsDurable(unittest.TestCase):
    def setUp(self):
        self.docs = docs(REDIS)

    def test_deployment_with_aof(self):
        dep = next(d for d in self.docs if d.get("kind") == "Deployment")
        self.assertEqual(dep["metadata"]["name"], "keepsvc-redis")
        joined = " ".join(str(part) for part in container(dep)["command"])
        self.assertIn("--appendonly yes", joined,
                      "sin AOF un reinicio de Redis con la cola llena pierde los "
                      "eventos encolados en silencio")

    def test_pvc_and_service(self):
        pvc = next(d for d in self.docs if d.get("kind") == "PersistentVolumeClaim")
        self.assertEqual(pvc["metadata"]["name"], "keepsvc-redis-data")
        svc = next(d for d in self.docs if d.get("kind") == "Service")
        self.assertEqual(svc["metadata"]["name"], "keepsvc-redis")
        port = svc["spec"]["ports"][0]
        self.assertEqual(port["port"], 6379)
        # El backend apunta a este nombre de Service (keep/values.yaml REDIS_HOST).
        values = yaml.safe_load(VALUES.read_text())
        self.assertEqual(
            env_of(values["backend"]["env"]).get("REDIS_HOST"),
            svc["metadata"]["name"],
        )


if __name__ == "__main__":
    unittest.main()

"""Contract de la red de seguridad ArgoCD→Keep (SC-5269 / INFRA-1547).

El resolved de ArgoCD Notifications solo se emite en la transición que el
controller observa (dedup por app+trigger): una app que se recupera sin sync
nuevo deja su incident `ArgoCDAppDegraded`/`ArgoCDSyncFailed` firing para
siempre (segunda ruta de SC-5203, medido al cerrar SC-5249).

INFRA-1547 (SC-5617): el CronJob */10 pasó a un Deployment-informer de
applications.argoproj.io. El push de notifications cubre el caso feliz; el
informer cubre el push perdido reaccionando al watch (resync nativo como red),
sin CronJob (veredicto INFRA-1547). El test EXTRAE el reconcile.py real del
ConfigMap, lo importa y ejercita reconcile_once() end-to-end con call/live_app
simulados, además de pinear el manifiesto y la huella:

* Renderiza 5 objetos (SA, Role, RoleBinding, ConfigMap, Deployment); el script
  compila; Deployment replicas 1 Recreate; NO queda CronJob; Role get/list/watch
  (lectura, sin escritura).
* La huella del resolved es la MISMA que fija la plantilla de ArgoCD:
  sha256("argocd/<app>/<tipo>")[:16].
* Condiciones por alerta, espejo de los triggers resolved de SC-5249:
  degraded -> health Healthy; sync-failed -> operationState Succeeded. NO un AND.
* SC-5867: nadie llama a `/incidents/<id>/alerts` (fuga el pool -> 500); leen con
  `POST /alerts/query`. El reaper (CronJob) sale ruidoso exit!=0 si el fetch falla;
  el informer NO sale el proceso (perdería el watch): grita en el log, no resuelve
  nada y el resync reintenta.
* Comportamiento: app sana -> resolved; app enferma -> nada; GRACE -> diferido;
  Keep caído -> no resuelve y no crashea; app borrada -> resolved; cada alerta se
  resuelve por su propia condición (sync-failed con health Degraded se resuelve).
"""

import hashlib
import importlib.util
import os
import pathlib
import tempfile
import unittest
from unittest import mock

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
RECONCILER = ROOT / "keep" / "maintenance" / "argocd-reconciler.yaml"
REAPER = ROOT / "keep" / "maintenance" / "stale-reaper.yaml"


def docs(path):
    return [d for d in yaml.safe_load_all(path.read_text()) if d]


def _module():
    """Importa el reconcile.py real del ConfigMap (main() no corre: va bajo __name__)."""
    os.environ.setdefault("KEEP_API_URL", "http://keep.test:8080")
    os.environ.setdefault("KEEP_API_KEY", "test-key")
    cm = next(d for d in docs(RECONCILER) if d["kind"] == "ConfigMap")
    src = cm["data"]["reconcile.py"]
    with tempfile.TemporaryDirectory() as tmp:
        p = pathlib.Path(tmp, "reconcile.py")
        p.write_text(src)
        spec = importlib.util.spec_from_file_location("keep_reconcile", p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    return mod


G = _module()


def _inc(iid, last_seen="2026-11-24T00:00:00"):
    return {"id": iid, "last_seen_time": last_seen}


def _alert(name, app, iid, status="firing"):
    return {"name": name, "status": status, "source": ["argocd"],
            "labels": {"app": app}, "incident": iid}


def _fake_call(incidents, alerts, fresh_status="resolved",
               fail_incidents=False, fail_alerts=False):
    """call() simulado que enruta por URL y registra los resolved emitidos."""
    emitted = []
    status_posts = []

    def call(url, method="GET", payload=None, headers=None, ctx=None):
        if "/incidents?cel=" in url:
            if fail_incidents:
                raise RuntimeError("keep caído")
            return {"items": incidents}
        if "/alerts/query" in url:
            if fail_alerts:
                raise RuntimeError("alerts query falló")
            return {"results": alerts, "count": len(alerts)}
        if "/alerts/event" in url:
            emitted.append(payload)
            return None
        if url.endswith("/status"):
            status_posts.append(payload)
            return None
        if "/incidents/" in url:  # GET del incident fresco tras el replay
            return {"status": fresh_status}
        raise AssertionError(f"URL inesperada: {url}")

    return call, emitted, status_posts


def _run(incidents, alerts, app_obj, **kw):
    call, emitted, status_posts = _fake_call(incidents, alerts, **kw)
    with mock.patch.object(G, "call", call), \
         mock.patch.object(G, "live_app", lambda name: app_obj), \
         mock.patch.object(G.time, "sleep", lambda *a: None):
        G.reconcile_once()
    return emitted, status_posts


class TestManifiesto(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.objs = docs(RECONCILER)
        cls.by_kind = {}
        for d in cls.objs:
            cls.by_kind.setdefault(d["kind"], []).append(d)

    def test_renderiza_cinco_objetos_sin_cronjob(self):
        self.assertEqual(len(self.objs), 5)
        self.assertNotIn("CronJob", self.by_kind)  # INFRA-1547: el */10 muere
        self.assertEqual(self.by_kind["ServiceAccount"][0]["metadata"]["namespace"], "monitoring")
        role = self.by_kind["Role"][0]
        self.assertEqual(role["metadata"]["namespace"], "argocd")
        self.assertEqual(role["rules"][0]["apiGroups"], ["argoproj.io"])
        self.assertEqual(role["rules"][0]["resources"], ["applications"])
        # get/list/watch: lectura para el informer; SIN escritura.
        self.assertEqual(sorted(role["rules"][0]["verbs"]), ["get", "list", "watch"])
        rb = self.by_kind["RoleBinding"][0]
        self.assertEqual(rb["roleRef"]["apiGroup"], "rbac.authorization.k8s.io")
        self.assertEqual(rb["roleRef"]["name"], "keepsvc-argocd-reconciler")
        self.assertEqual(rb["subjects"][0]["namespace"], "monitoring")

    def test_informer_deployment_single_recreate(self):
        dep = self.by_kind["Deployment"][0]
        self.assertEqual(dep["spec"]["replicas"], 1)
        self.assertEqual(dep["spec"]["strategy"]["type"], "Recreate")
        tmpl = dep["spec"]["template"]
        self.assertEqual(tmpl["spec"]["serviceAccountName"], "keepsvc-argocd-reconciler")
        env = {e["name"]: e.get("value") for e in tmpl["spec"]["containers"][0]["env"]}
        self.assertEqual(env.get("RESYNC_SECONDS"), "900")

    def test_script_embebido_compila(self):
        src = self.by_kind["ConfigMap"][0]["data"]["reconcile.py"]
        compile(src, "reconcile.py", "exec")

    def test_huella_igual_que_la_plantilla_argocd(self):
        src = self.by_kind["ConfigMap"][0]["data"]["reconcile.py"]
        self.assertIn('f"argocd/{app}/{kind}"', src)
        self.assertIn("hexdigest()[:16]", src)
        self.assertEqual(len(hashlib.sha256(b"argocd/redroid/degraded").hexdigest()[:16]), 16)

    def test_condiciones_espejo_de_los_triggers_resolved(self):
        src = self.by_kind["ConfigMap"][0]["data"]["reconcile.py"]
        self.assertIn('"ArgoCDAppDegraded": "degraded"', src)
        self.assertIn('"ArgoCDSyncFailed": "sync-failed"', src)
        self.assertIn('get("health") or {}).get("status") == "Healthy"', src)
        self.assertIn('get("operationState") or {}).get("phase") == "Succeeded"', src)
        self.assertIn("if app_obj is None", src)

    def test_canal_de_ingesta_el_mismo_que_argocd(self):
        src = self.by_kind["ConfigMap"][0]["data"]["reconcile.py"]
        self.assertIn('/alerts/event', src)
        self.assertIn('"source": ["argocd"]', src)

    def test_filtra_abiertos_no_solo_firing(self):
        src = self.by_kind["ConfigMap"][0]["data"]["reconcile.py"]
        self.assertIn('status == "firing" || status == "acknowledged"', src)
        self.assertIn('a.get("status") in ("firing", "acknowledged")', src)

    def test_watch_y_resync_en_el_bucle(self):
        src = self.by_kind["ConfigMap"][0]["data"]["reconcile.py"]
        self.assertIn("applications?watch=true", src)
        self.assertIn("changed.wait(RESYNC)", src)


class TestComportamiento(unittest.TestCase):
    def test_app_sana_degraded_resolved(self):
        inc = _inc("i1")
        al = _alert("ArgoCDAppDegraded", "redroid", "i1")
        app = {"status": {"health": {"status": "Healthy"}}}
        emitted, _ = _run([inc], [al], app)
        self.assertEqual(len(emitted), 1)
        self.assertEqual(emitted[0]["status"], "resolved")
        self.assertEqual(emitted[0]["fingerprint"],
                         hashlib.sha256(b"argocd/redroid/degraded").hexdigest()[:16])

    def test_app_enferma_no_resuelve(self):
        inc = _inc("i1")
        al = _alert("ArgoCDAppDegraded", "redroid", "i1")
        app = {"status": {"health": {"status": "Degraded"}}}
        emitted, _ = _run([inc], [al], app)
        self.assertEqual(emitted, [])

    def test_sync_failed_se_resuelve_por_su_condicion_no_and(self):
        # App Healthy en health pero el caso residual: operationState Succeeded con
        # health Degraded. La alerta sync-failed se resuelve por Succeeded (no AND).
        inc = _inc("i1")
        al = _alert("ArgoCDSyncFailed", "redroid", "i1")
        app = {"status": {"health": {"status": "Degraded"},
                          "operationState": {"phase": "Succeeded"}}}
        emitted, _ = _run([inc], [al], app)
        self.assertEqual(len(emitted), 1)
        self.assertEqual(emitted[0]["fingerprint"],
                         hashlib.sha256(b"argocd/redroid/sync-failed").hexdigest()[:16])

    def test_grace_difiere_incident_reciente(self):
        import time as _t
        recent = _t.strftime("%Y-%m-%dT%H:%M:%S", _t.gmtime())
        inc = _inc("i1", last_seen=recent)
        al = _alert("ArgoCDAppDegraded", "redroid", "i1")
        app = {"status": {"health": {"status": "Healthy"}}}
        emitted, _ = _run([inc], [al], app)
        self.assertEqual(emitted, [])  # visto hace <GRACE: fuera, lo coge el resync

    def test_app_borrada_resolved(self):
        inc = _inc("i1")
        al = _alert("ArgoCDAppDegraded", "redroid", "i1")
        emitted, _ = _run([inc], [al], {})  # live_app 404 -> {} -> sana
        self.assertEqual(len(emitted), 1)

    def test_keep_incidents_caido_no_resuelve_no_crashea(self):
        al = _alert("ArgoCDAppDegraded", "redroid", "i1")
        app = {"status": {"health": {"status": "Healthy"}}}
        emitted, _ = _run([_inc("i1")], [al], app, fail_incidents=True)
        self.assertEqual(emitted, [])  # devuelve sin resolver, sin excepción

    def test_alerts_fetch_falla_no_resuelve(self):
        al = _alert("ArgoCDAppDegraded", "redroid", "i1")
        app = {"status": {"health": {"status": "Healthy"}}}
        emitted, _ = _run([_inc("i1")], [al], app, fail_alerts=True)
        self.assertEqual(emitted, [])

    def test_estado_vivo_no_confirmable_no_toca(self):
        inc = _inc("i1")
        al = _alert("ArgoCDAppDegraded", "redroid", "i1")
        emitted, _ = _run([inc], [al], None)  # live_app None -> no confirmable
        self.assertEqual(emitted, [])


class TestFetchSinFugaSC5867(unittest.TestCase):
    """SC-5867: `/incidents/<id>/alerts` en keep 0.52.1 fuga una transacción por
    llamada y agota el pool -> 500. `POST /alerts/query` no fuga. El reaper
    (CronJob) sale exit!=0 si el fetch falla; el informer grita y no resuelve,
    sin salir el proceso (el resync reintenta)."""

    def _srcs(self):
        r = next(d for d in docs(RECONCILER) if d["kind"] == "ConfigMap")["data"]["reconcile.py"]
        p = next(d for d in docs(REAPER) if d["kind"] == "ConfigMap")["data"]["reaper.py"]
        return r, p

    def test_nadie_llama_al_endpoint_que_fuga(self):
        for src in self._srcs():
            self.assertNotIn("/incidents/{inc['id']}/alerts", src)
            self.assertNotIn("/alerts?limit=1000", src)

    def test_usan_alerts_query_agrupado(self):
        for src in self._srcs():
            self.assertIn("/alerts/query", src)
            self.assertIn('"cel"', src)

    def test_reaper_ruidoso_exit_si_fetch_falla(self):
        p = next(d for d in docs(REAPER) if d["kind"] == "ConfigMap")["data"]["reaper.py"]
        self.assertIn("no puedo decidir, salgo con error", p)
        self.assertIn("sys.exit(1)", p)

    def test_informer_ruidoso_sin_salir_el_proceso(self):
        r = next(d for d in docs(RECONCILER) if d["kind"] == "ConfigMap")["data"]["reconcile.py"]
        # Grita y no resuelve; NO sys.exit en la pasada (perdería el watch).
        self.assertIn("no puedo decidir, no resuelvo", r)
        self.assertIn("def reconcile_once", r)
        self.assertIn("changed.wait(RESYNC)", r)


class TestStaleReaperCedeArgocd(unittest.TestCase):
    def test_reaper_no_toca_alertas_argocd(self):
        src = next(d for d in docs(REAPER) if d["kind"] == "ConfigMap")["data"]["reaper.py"]
        self.assertIn('"argocd" not in (a.get("source") or [])', src)


if __name__ == "__main__":
    unittest.main()
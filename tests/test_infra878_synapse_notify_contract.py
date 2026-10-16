"""INFRA-878: la alarma de colas sin consumidor y el crashloop de Synapse llegan a quien atiende.

Pina tres cosas medidas el 16-10 en SKIRM-162 (la alarma del gmail de SKIRM-161
saltó y nadie actuó):

1. `KubePodCrashLooping` y `K8sCronJobFailed` del ns `synapse` pasan por el
   backstop-telegram (repite mientras sigan firing — `notify-incident` es
   `on: create` y calló 6 días) y SIGUEN yendo a Keep (`continue: true`).
2. `notify-alert-summary` (type: alert, only_on_change: [status]) incluye
   KubePodCrashLooping del ns synapse: cada alerta nueva avisa con su summary,
   no solo el título del incidente agrupado.
3. La regla de correlación `synapse-pipeline` agrupa por [alertname, queue]:
   una cola nueva sin consumidor abre su propio incidente (con `[]` se unía al
   incidente abierto de otra cola y no avisaba). Y la lista `chronic` no
   resucita (INFRA-882: tapaba alertas reales).
"""

import importlib.util
from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("alert_routing", ROOT / "scripts" / "alert_routing.py")
alert_routing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(alert_routing)

ROUTE = yaml.safe_load((ROOT / "manifests" / "alertmanager-config.yaml").read_text())["spec"]["route"]
VALUES = ROOT / "keep" / "values.yaml"
CORRELATION = ROOT / "keep" / "rules" / "correlation-rules.yaml"


def workflows():
    values = yaml.safe_load(VALUES.read_text())
    return {w["id"]: w for w in values["backend"]["provision"]["workflows"]}


def rule(name):
    rules = yaml.safe_load(CORRELATION.read_text())["rules"]
    for r in rules:
        if r["ruleName"] == name:
            return r
    raise AssertionError(f"rule {name} not found")


class SynapseCrashloopBackstopTest(unittest.TestCase):
    def receivers(self, alertname, namespace):
        labels = {"alertname": alertname, "severity": "warning", "namespace": namespace}
        return alert_routing.resolve(ROUTE, labels)

    def test_synapse_crashloop_goes_to_telegram_and_keep(self):
        self.assertEqual(self.receivers("KubePodCrashLooping", "synapse"), ["backstop-telegram", "keep"])

    def test_synapse_cronjob_failed_goes_to_telegram_and_keep(self):
        self.assertEqual(self.receivers("K8sCronJobFailed", "synapse"), ["backstop-telegram", "keep"])

    def test_other_namespaces_not_added_to_the_backstop(self):
        # el criterio de la Request es el ns synapse; el resto sigue solo a Keep
        self.assertEqual(self.receivers("KubePodCrashLooping", "monitoring"), ["keep"])

    def test_existing_backstop_entry_is_untouched(self):
        labels = {"alertname": "RabbitmqFunctionalQueueNoConsumer", "severity": "warning",
                  "namespace": "monitoring", "queue": "adapter.expenses.process"}
        self.assertEqual(alert_routing.resolve(ROUTE, labels), ["backstop-telegram", "keep"])


class AlertSummaryCoversSynapseCrashloopTest(unittest.TestCase):
    def test_cel_includes_synapse_crashloop_and_keeps_the_old_two(self):
        trigger = workflows()["notify-alert-summary"]["triggers"][0]
        self.assertEqual(trigger["only_on_change"], ["status"])
        cel = trigger["cel"]
        for needle in ("BrainIngestConsecutiveFailures", "K8sCronJobFailed",
                       'name == "KubePodCrashLooping"', 'labels.namespace == "synapse"'):
            self.assertIn(needle, cel)


class SynapsePipelineGroupsPerQueueTest(unittest.TestCase):
    def test_groups_by_alertname_and_queue(self):
        self.assertEqual(rule("synapse-pipeline")["groupingCriteria"], ["alertname", "queue"])

    def test_covers_the_no_consumer_alert(self):
        self.assertIn("Rabbitmq", rule("synapse-pipeline")["celQuery"])

    def test_chronic_list_stays_dead(self):
        # INFRA-882: la lista chronic tapaba alertas reales (el gmail, 3 h). No vuelve.
        text = CORRELATION.read_text()
        self.assertNotIn("chronic-debt", text)


if __name__ == "__main__":
    unittest.main()

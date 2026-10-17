"""INFRA-878: cada cola de Synapse sin consumidor abre su incidente y despierta a ops-watch.

Modelo tras INFRA-912 (Dani: «las alertas en Telegram son inútiles»): el
incidente de Keep es la notificación y ops-watch la convierte en Request (el
despertar de ops-sre). Lo que pina este test es que ese camino existe para la
alarma de colas sin consumidor, que es la única que ve un consumidor muerto
(caso gmail, SKIRM-161: 3 h sin nadie):

1. `RabbitmqFunctionalQueueNoConsumer` llega a Keep (catch-all: sin regla de
   correlación una warning queda registrada y calla).
2. La regla `synapse-pipeline` agrupa por [alertname, queue]: una cola nueva sin
   consumidor abre su propio incidente (con `[]` se unía al incidente abierto de
   otra cola y no avisaba — el patrón que INFRA-378 ya cazó para CRON).
3. La lista `chronic` no resucita (INFRA-882: tapaba alertas reales — la del
   gmail estuvo 3 h en «Deuda de alertas conocida» sin despertar a nadie).
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
CORRELATION = ROOT / "keep" / "rules" / "correlation-rules.yaml"


def rule(name):
    rules = yaml.safe_load(CORRELATION.read_text())["rules"]
    for r in rules:
        if r["ruleName"] == name:
            return r
    raise AssertionError(f"rule {name} not found")


class NoConsumerReachesKeepTest(unittest.TestCase):
    def test_the_alert_goes_to_keep(self):
        labels = {"alertname": "RabbitmqFunctionalQueueNoConsumer", "severity": "warning",
                  "namespace": "monitoring", "queue": "adapter.gmail.webhooks"}
        self.assertEqual(alert_routing.resolve(ROUTE, labels), ["keep"])


class SynapsePipelineGroupsPerQueueTest(unittest.TestCase):
    def test_groups_by_alertname_and_queue(self):
        self.assertEqual(rule("synapse-pipeline")["groupingCriteria"], ["alertname", "queue"])

    def test_covers_the_no_consumer_alert(self):
        self.assertIn("Rabbitmq", rule("synapse-pipeline")["celQuery"])

    def test_chronic_list_stays_dead(self):
        # INFRA-882: la lista chronic tapaba alertas reales (el gmail, 3 h). No vuelve.
        self.assertNotIn("chronic-debt", CORRELATION.read_text())


if __name__ == "__main__":
    unittest.main()

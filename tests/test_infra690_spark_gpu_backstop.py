"""INFRA-690: SparkGpuClockStuckLow llega a Telegram directo (backstop-telegram) y sigue a Keep.

Usa el simulador de rutas del repo (scripts/alert_routing.py, la misma semántica de
matching de Alertmanager) sobre manifests/alertmanager-config.yaml, el CR que ArgoCD aplica.
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


class SparkGpuBackstopTest(unittest.TestCase):
    def receivers(self, alertname, severity="warning"):
        labels = {"alertname": alertname, "severity": severity, "namespace": "monitoring"}
        return alert_routing.resolve(ROUTE, labels)

    def test_spark_gpu_alert_goes_to_telegram_and_keep(self):
        self.assertEqual(self.receivers("SparkGpuClockStuckLow"), ["backstop-telegram", "keep"])

    def test_the_regex_is_an_exact_match(self):
        # fullmatch: un alertname que solo contiene el nombre no se cuela en el backstop
        self.assertEqual(self.receivers("SparkGpuClockStuckLowX"), ["keep"])

    def test_existing_backstop_entry_is_untouched(self):
        self.assertEqual(self.receivers("KubeNodeNotReady"), ["backstop-telegram", "keep"])


if __name__ == "__main__":
    unittest.main()

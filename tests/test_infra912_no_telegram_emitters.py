"""INFRA-912 (2026-10-17): ningún emisor de alertas de este repo apunta a Telegram.

Cubre la superficie que no vive en keep/values.yaml (eso lo fija
test_infra378_keep_notify_contract.py): el enrutado de Alertmanager, los
manifiestos y los secretos. Es el pin de la aceptación de la historia sobre
este repo: si algo vuelve a hablar con la Bot API, este test ruge.
"""

from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = ROOT / "manifests"


def parsed(path):
    return yaml.safe_load(path.read_text())


class AlertmanagerRoutingTest(unittest.TestCase):
    def setUp(self):
        self.spec = parsed(MANIFESTS / "alertmanager-config.yaml")["spec"]

    def test_no_telegram_receiver(self):
        names = [r["name"] for r in self.spec["receivers"]]
        self.assertEqual(names, ["blackhole", "keep"])
        for r in self.spec["receivers"]:
            self.assertNotIn("telegram_configs", r)

    def test_no_route_targets_a_telegram_receiver(self):
        def walk(route):
            yield route
            for child in route.get("routes") or []:
                yield from walk(child)
        receivers = {rt.get("receiver") for rt in walk(self.spec["route"])}
        self.assertTrue(receivers <= {"keep", "blackhole", None}, receivers)

    def test_telegram_backup_secret_is_gone(self):
        self.assertFalse((MANIFESTS / "alertmanager-secrets.yaml").exists())
        text = (MANIFESTS / "alertmanager-config.yaml").read_text()
        self.assertNotIn("alertmanager-telegram-backup", text)


class ManifestsTest(unittest.TestCase):
    def test_backup_alert_reports_file_is_gone(self):
        self.assertFalse((MANIFESTS / "backup-alert-reports.yaml").exists())

    def test_kustomization_does_not_reference_retired_files(self):
        text = (ROOT / "kustomization.yaml").read_text()
        self.assertNotIn("backup-alert-reports", text)
        self.assertNotIn("alertmanager-secrets", text)

    def test_health_watcher_has_no_telegram(self):
        docs = [d for d in yaml.safe_load_all((MANIFESTS / "dgx-cluster-health-watcher.yaml").read_text()) if d]
        text = yaml.dump(docs)
        self.assertNotIn("telegram", text.lower())
        self.assertNotIn("api.telegram.org", text)
        self.assertNotIn("POST_MODE", text)
        # el reporte sigue en el log del Job
        self.assertIn("REPORT", text)

    def test_keep_secrets_has_no_telegram_provider(self):
        docs = list(yaml.safe_load_all((MANIFESTS / "keep-secrets.yaml").read_text()))
        providers = next(
            d["spec"]["target"]["template"]["data"]["KEEP_PROVIDERS"]
            for d in docs
            if d and d.get("metadata", {}).get("name") == "keepsvc-provisioning"
        )
        self.assertNotIn("telegram", providers.lower())
        self.assertNotIn("telegram_bot_token", providers)


if __name__ == "__main__":
    unittest.main()

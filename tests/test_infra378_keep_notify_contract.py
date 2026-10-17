"""Contract for the cron-job-failed grouping (INFRA-378) — and its INFRA-912 half.

Pins:

1. The `cron-job-failed` correlation rule groups by [namespace, alertname] and
   its incident name carries the alertname, so a BrainIngestConsecutiveFailures
   alert can no longer be absorbed silently into an old CRON incident opened by
   K8sCronJobFailed (incident 9d403a3e suppressed every re-alert for 9 days).

2. INFRA-912 (2026-10-17, Dani: «las alertas en Telegram son inútiles»): the
   Telegram notify lanes (`notify-incident`, `notify-incident-critical`,
   `notify-alert-summary`, `incident-summary`) are GONE from keep/values.yaml.
   Nothing in the Keep provisioning talks to Telegram any more; the incident is
   the notification and ops-watch turns it into a Request.
"""

from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
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


class CronJobFailedGroupingTest(unittest.TestCase):
    def test_groups_by_namespace_and_alertname(self):
        self.assertEqual(rule("cron-job-failed")["groupingCriteria"], ["namespace", "alertname"])

    def test_incident_name_carries_alertname(self):
        template = rule("cron-job-failed")["incidentNameTemplate"]
        self.assertIn("{{ alertname }}", template)
        self.assertIn("{{ namespace }}", template)

    def test_rule_still_covers_both_alerts(self):
        cel = rule("cron-job-failed")["celQuery"]
        self.assertIn("K8sCronJobFailed", cel)
        self.assertIn("BrainIngestConsecutiveFailures", cel)


class TelegramNotifyLanesRetiredTest(unittest.TestCase):
    """INFRA-912: los workflows de aviso por Telegram no deben volver."""

    def test_notify_workflows_are_gone(self):
        wf = workflows()
        for wf_id in ("notify-incident", "notify-incident-critical",
                      "notify-alert-summary", "incident-summary"):
            self.assertNotIn(wf_id, wf)

    def test_parsed_values_have_no_telegram_data(self):
        # Los comentarios históricos pueden nombrar Telegram; el DATO no.
        import json
        data = json.dumps(yaml.safe_load(VALUES.read_text()), ensure_ascii=False)
        self.assertNotIn("telegram", data.lower())
        self.assertNotIn("-1004409526898", data)


if __name__ == "__main__":
    unittest.main()

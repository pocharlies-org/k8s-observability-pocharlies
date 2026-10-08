"""Contract for the Keep Telegram alert-summary notify path (INFRA-378).

Pins two things the epic depends on:

1. The `cron-job-failed` correlation rule groups by [namespace, alertname] and
   its incident name carries the alertname, so a BrainIngestConsecutiveFailures
   alert can no longer be absorbed silently into an old CRON incident opened by
   K8sCronJobFailed (incident 9d403a3e suppressed every re-alert for 9 days).
2. The alert summaries reach Telegram through the `notify-alert-summary`
   workflow: `type: alert` with `only_on_change: [status]`, no steps (a failing
   step = zero notifications in Keep 0.52.1), no parse_mode (summaries can
   carry `<`, `>`, `&` and Telegram answers 400 on html), topic 1248 and the
   same on-failure retry as the incident lanes.

`notify-incident` / `notify-incident-critical` must stay `events: [created]`:
Alertmanager re-sends every minute, and notifying on `updated` would turn that
into one message per minute.
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


class IncidentNotifyLanesUnchangedTest(unittest.TestCase):
    def test_notify_incident_lanes_stay_created_only(self):
        wf = workflows()
        for wf_id in ("notify-incident", "notify-incident-critical"):
            triggers = wf[wf_id]["triggers"]
            self.assertEqual([t["events"] for t in triggers], [["created"]], wf_id)


class NotifyAlertSummaryTest(unittest.TestCase):
    def setUp(self):
        self.wf = workflows()["notify-alert-summary"]

    def test_is_alert_triggered_with_status_only_change(self):
        (trigger,) = self.wf["triggers"]
        self.assertEqual(trigger["type"], "alert")
        self.assertEqual(trigger["only_on_change"], ["status"])
        for alert in ("BrainIngestConsecutiveFailures", "K8sCronJobFailed"):
            self.assertIn(alert, trigger["cel"])

    def test_has_no_steps(self):
        # Un step que falla = cero avisos (Keep 0.52.1): el aviso debe salir
        # siempre, así que este workflow vive de sus acciones, sin steps.
        self.assertNotIn("steps", self.wf)

    def test_action_targets_topic_1248_without_parse_mode(self):
        (action,) = self.wf["actions"]
        self.assertEqual(action["name"], "telegram-alert-summary")
        with_ = action["provider"]["with"]
        self.assertEqual(with_["chat_id"], "-1004409526898")
        self.assertEqual(with_["topic_id"], 1248)
        self.assertNotIn("parse_mode", with_)
        self.assertNotIn("message_thread_id", with_)

    def test_action_carries_retry(self):
        (action,) = self.wf["actions"]
        self.assertEqual(action["on-failure"]["retry"], {"count": 3, "interval": 15})

    def test_message_carries_the_alert_summary(self):
        (action,) = self.wf["actions"]
        self.assertIn("{{ alert.annotations.summary }}", action["provider"]["with"]["message"])


if __name__ == "__main__":
    unittest.main()

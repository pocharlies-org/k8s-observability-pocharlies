"""Contract for the BrainIngestConsecutiveFailures alert (INFRA-286).

Pins the YAML text: the VMRule, its intentional lack of a success ``unless``,
the retired cron-alert-analyzer wording, and the Keep CRON correlation hook.
"""

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "manifests" / "rules.yaml"
CORRELATION = ROOT / "keep" / "rules" / "correlation-rules.yaml"


def alert_block(text: str, name: str) -> str:
    match = re.search(
        r"^ {8}- alert: " + re.escape(name) + r"\n(?P<block>.*?)(?=^ {8}- alert: |^ {4}- name: |^---|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if not match:
        raise AssertionError(f"{name} alert not found")
    return match.group("block")


def expr_of(block: str) -> str:
    match = re.search(r"^ {10}expr: \|\n(?P<expr>(?: {12}.*\n)+)", block, re.MULTILINE)
    if not match:
        raise AssertionError("expr not found")
    return match.group("expr")


class BrainIngestAlertTest(unittest.TestCase):
    def setUp(self):
        self.text = RULES.read_text()
        self.block = alert_block(self.text, "BrainIngestConsecutiveFailures")

    def test_expr_counts_two_failed_jobs(self):
        expr = expr_of(self.block)
        self.assertIn('condition="true"', expr)
        self.assertIn(">= 2", expr)

    def test_expr_has_no_success_unless(self):
        self.assertNotIn("unless", expr_of(self.block))

    def test_stale_cron_alert_analyzer_annotation_gone(self):
        cron = alert_block(self.text, "K8sCronJobFailed")
        self.assertNotIn("cron-alert-analyzer will post", cron)


class KeepCronCorrelationTest(unittest.TestCase):
    def test_cron_job_failed_covers_both_alerts(self):
        text = CORRELATION.read_text()
        match = re.search(
            r"^  - ruleName: cron-job-failed\n(?P<block>.*?)(?=^  - ruleName: |\Z)",
            text,
            re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(match, "cron-job-failed rule not found")
        block = match.group("block")
        cel = re.search(r"^    celQuery: (.*)$", block, re.MULTILINE).group(1)
        self.assertIn("K8sCronJobFailed", cel)
        self.assertIn("BrainIngestConsecutiveFailures", cel)
        self.assertIn("name in (", block)


if __name__ == "__main__":
    unittest.main()

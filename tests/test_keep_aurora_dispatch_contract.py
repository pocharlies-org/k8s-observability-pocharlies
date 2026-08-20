"""Contract for Keep's critical-only Aurora dispatch lane.

The workflow is Helm values rather than Python.  Keep renders its ``if`` expression
at runtime, so this test pins both independent defences: the SQL claim must reject
non-critical incidents before writing the fingerprint, and the webhook action must
also require critical severity.
"""

from pathlib import Path
import re
import unittest


VALUES = Path(__file__).resolve().parents[1] / "keep" / "values.yaml"


def aurora_investigate_block(text: str) -> str:
    match = re.search(
        r"^      - id: aurora-investigate\n(?P<block>.*?)(?=^      - id: |\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if not match:
        raise AssertionError("aurora-investigate workflow not found")
    return match.group("block")


class KeepAuroraDispatchContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.block = aurora_investigate_block(VALUES.read_text())

    def test_warning_neither_claims_nor_dispatches(self):
        self.assertRegex(
            self.block,
            r"AS severity\s+-- Defensa antes del claim:[\s\S]*?"
            r"WHERE '\{\{ incident\.severity \}\}' = 'critical'",
        )
        self.assertIn(
            "if: \"'{{ incident.severity }}' == 'critical' and "
            "'{{ steps.claim-dispatch.results.0.0 }}' != ''\"",
            self.block,
        )

    def test_critical_claims_and_dispatches_when_fingerprint_is_new(self):
        self.assertIn(
            "NULLIF('{{ incident.severity }}', '') AS severity",
            self.block,
        )
        self.assertIn("ON CONFLICT (fingerprint) DO NOTHING", self.block)
        self.assertIn("- name: dispatch-rca", self.block)

    def test_report_back_workflow_is_not_part_of_dispatch_contract(self):
        self.assertNotIn("aurora-report-back", self.block)


if __name__ == "__main__":
    unittest.main()

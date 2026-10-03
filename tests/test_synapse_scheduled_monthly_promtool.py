"""promtool test of SynapseScheduledWorkflowRunStalledMonthly and of the processor_fees
exclusion in SynapseScheduledWorkflowStalled (pocharlies-synapse-core VMRule).

Runs those two rules, extracted from manifests/rules.yaml, against
tests/promtool/synapse-scheduled-monthly.test.yaml (harness: tests/promtool_rules.py).
"""

import unittest

from promtool_rules import ROOT, run_promtool, vmrule_groups

CASES = ROOT / "tests" / "promtool" / "synapse-scheduled-monthly.test.yaml"
ALERTS = {"SynapseScheduledWorkflowRunStalledMonthly", "SynapseScheduledWorkflowStalled"}


class SynapseScheduledMonthlyPromtoolTest(unittest.TestCase):
    def test_promtool_cases(self):
        rules = [r for g in vmrule_groups("pocharlies-synapse-core") for r in g["rules"] if r.get("alert") in ALERTS]
        self.assertEqual({r["alert"] for r in rules}, ALERTS)
        run_promtool(self, [{"name": "synapse-scheduled", "rules": rules}], "synapse-scheduled.rules.yaml", CASES)


if __name__ == "__main__":
    unittest.main()

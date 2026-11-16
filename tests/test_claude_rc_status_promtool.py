"""promtool test of ClaudeRcStatusMemoryHeadroomLow (SC-5718, pocharlies-paseo-rc-status VMRule).

Runs that rule, extracted from manifests/rules.yaml, against
tests/promtool/claude-rc-status.test.yaml (harness: tests/promtool_rules.py).
"""

import unittest

from promtool_rules import ROOT, run_promtool, vmrule_groups

CASES = ROOT / "tests" / "promtool" / "claude-rc-status.test.yaml"
ALERTS = {"ClaudeRcStatusMemoryHeadroomLow"}


class ClaudeRcStatusPromtoolTest(unittest.TestCase):
    def test_promtool_cases(self):
        rules = [r for g in vmrule_groups("pocharlies-paseo-rc-status") for r in g["rules"] if r.get("alert") in ALERTS]
        self.assertEqual({r["alert"] for r in rules}, ALERTS)
        run_promtool(self, [{"name": "claude-rc-status", "rules": rules}], "claude-rc-status.rules.yaml", CASES)


if __name__ == "__main__":
    unittest.main()

"""promtool test of the company alerts (SC-1872): CompaniaBuzonAtascado, CompaniaSinTurnos and
CompaniaSupervisorSinMetricas (pocharlies-compania VMRule).

Runs those rules, extracted from manifests/rules.yaml, against tests/promtool/compania.test.yaml
(harness: tests/promtool_rules.py).
"""

import unittest

from promtool_rules import ROOT, run_promtool, vmrule_groups

CASES = ROOT / "tests" / "promtool" / "compania.test.yaml"
ALERTS = {"CompaniaBuzonAtascado", "CompaniaSinTurnos", "CompaniaSupervisorSinMetricas"}


class CompaniaPromtoolTest(unittest.TestCase):
    def test_promtool_cases(self):
        rules = [r for g in vmrule_groups("pocharlies-compania") for r in g["rules"] if r.get("alert") in ALERTS]
        self.assertEqual({r["alert"] for r in rules}, ALERTS)
        run_promtool(self, [{"name": "compania", "rules": rules}], "compania.rules.yaml", CASES)


if __name__ == "__main__":
    unittest.main()

"""promtool test of the company alerts of the pocharlies-compania VMRule listed in ALERTS (SC-1872, SC-5531).

Runs those rules, extracted from manifests/rules.yaml, against tests/promtool/compania.test.yaml
(harness: tests/promtool_rules.py).
"""

import unittest

from promtool_rules import ROOT, run_promtool, vmrule_groups

CASES = ROOT / "tests" / "promtool" / "compania.test.yaml"
ALERTS = {"CompaniaSupervisorSinMetricas", "CompaniaSynapseSinPublicar", "CompaniaPreguntasSinEntregar", "ClaudeKeySinCuentas"}


class CompaniaPromtoolTest(unittest.TestCase):
    def test_promtool_cases(self):
        rules = [r for g in vmrule_groups("pocharlies-compania") for r in g["rules"] if r.get("alert") in ALERTS]
        self.assertEqual({r["alert"] for r in rules}, ALERTS)
        run_promtool(self, [{"name": "compania", "rules": rules}], "compania.rules.yaml", CASES)


if __name__ == "__main__":
    unittest.main()

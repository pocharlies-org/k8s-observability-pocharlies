"""promtool test of the pocharlies-claude-cuentas VMRule (SC-5262): el hombre muerto del monitor.

Runs the live group from manifests/claude-cuentas-rules.yaml against
tests/promtool/claude-cuentas.test.yaml (harness: tests/promtool_rules.py).
"""

import unittest

from promtool_rules import ROOT, run_promtool, vmrule_groups

CASES = ROOT / "tests" / "promtool" / "claude-cuentas.test.yaml"
RULES_FILE = ROOT / "manifests" / "claude-cuentas-rules.yaml"


class ClaudeCuentasPromtoolTest(unittest.TestCase):
    def test_promtool_cases(self):
        run_promtool(self, vmrule_groups("pocharlies-claude-cuentas", RULES_FILE),
                     "claude-cuentas.rules.yaml", CASES)


if __name__ == "__main__":
    unittest.main()

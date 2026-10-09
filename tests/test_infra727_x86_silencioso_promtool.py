"""promtool test of the X86Silencioso VMRule (INFRA-727).

Runs the live pocharlies-x86-silencioso group from manifests/rules.yaml against
tests/promtool/x86-silencioso.test.yaml (harness: tests/promtool_rules.py).
"""

import unittest

from promtool_rules import ROOT, run_promtool, vmrule_groups

CASES = ROOT / "tests" / "promtool" / "x86-silencioso.test.yaml"


class X86SilenciosoPromtoolTest(unittest.TestCase):
    def test_promtool_cases(self):
        run_promtool(self, vmrule_groups("pocharlies-x86-silencioso"), "x86-silencioso.rules.yaml", CASES)


if __name__ == "__main__":
    unittest.main()

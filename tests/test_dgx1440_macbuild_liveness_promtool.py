"""promtool test of the pocharlies-mac-build-liveness VMRule (DGX-1440).

Runs the live group from manifests/mac-build-liveness-rules.yaml against
tests/promtool/mac-build-liveness.test.yaml (harness: tests/promtool_rules.py).
"""

import unittest

from promtool_rules import ROOT, run_promtool, vmrule_groups

CASES = ROOT / "tests" / "promtool" / "mac-build-liveness.test.yaml"
RULES_FILE = ROOT / "manifests" / "mac-build-liveness-rules.yaml"


class MacBuildLivenessPromtoolTest(unittest.TestCase):
    def test_promtool_cases(self):
        run_promtool(self, vmrule_groups("pocharlies-mac-build-liveness", RULES_FILE),
                     "mac-build-liveness.rules.yaml", CASES)


if __name__ == "__main__":
    unittest.main()

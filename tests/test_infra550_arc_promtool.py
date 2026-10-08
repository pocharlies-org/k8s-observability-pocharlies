"""promtool test de las reglas de cola CI (INFRA-550).

Runs the live pocharlies.arc-ci group from manifests/arc-rules.yaml against
tests/promtool/arc-rules.test.yaml (harness: tests/promtool_rules.py).
"""

import unittest

from promtool_rules import ROOT, run_promtool, vmrule_groups

CASES = ROOT / "tests" / "promtool" / "arc-rules.test.yaml"
RULES = ROOT / "manifests" / "arc-rules.yaml"


class ArcRulesPromtoolTest(unittest.TestCase):
    def test_promtool_cases(self):
        run_promtool(self, vmrule_groups("pocharlies-arc-ci", RULES),
                     "arc-rules.generated.yaml", CASES)


if __name__ == "__main__":
    unittest.main()

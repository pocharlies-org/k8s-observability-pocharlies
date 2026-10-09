"""promtool test de las alertas de Frigate (INFRA-712).

Runs the live pocharlies.frigate group from manifests/frigate-rules.yaml against
tests/promtool/frigate-rules.test.yaml (harness: tests/promtool_rules.py).
"""

import unittest

from promtool_rules import ROOT, run_promtool, vmrule_groups

CASES = ROOT / "tests" / "promtool" / "frigate-rules.test.yaml"
RULES = ROOT / "manifests" / "frigate-rules.yaml"


class FrigateRulesPromtoolTest(unittest.TestCase):
    def test_promtool_cases(self):
        run_promtool(self, vmrule_groups("pocharlies-frigate", RULES),
                     "frigate-rules.generated.yaml", CASES)


if __name__ == "__main__":
    unittest.main()

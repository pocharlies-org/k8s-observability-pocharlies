"""promtool test of the pocharlies.node-saturation VMRule (SC-6015).

Runs the live pocharlies.node-saturation group from manifests/rules.yaml against
tests/promtool/node-saturation.test.yaml (harness: tests/promtool_rules.py).
"""

import unittest

from promtool_rules import ROOT, run_promtool, vmrule_groups

CASES = ROOT / "tests" / "promtool" / "node-saturation.test.yaml"


class NodeSaturationPromtoolTest(unittest.TestCase):
    def test_promtool_cases(self):
        run_promtool(self, vmrule_groups("pocharlies-node-saturation"), "node-saturation.rules.yaml", CASES)


if __name__ == "__main__":
    unittest.main()

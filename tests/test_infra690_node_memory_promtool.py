"""promtool test of the NodeMemoryHighUtilization VMRule (INFRA-690: dgx3 joins the Sparks).

Runs the live pocharlies.node-memory group from manifests/rules.yaml against
tests/promtool/node-memory.test.yaml (harness: tests/promtool_rules.py).
"""

import unittest

from promtool_rules import ROOT, run_promtool, vmrule_groups

CASES = ROOT / "tests" / "promtool" / "node-memory.test.yaml"


class NodeMemoryPromtoolTest(unittest.TestCase):
    def test_promtool_cases(self):
        run_promtool(self, vmrule_groups("pocharlies-node-memory"), "node-memory.rules.yaml", CASES)


if __name__ == "__main__":
    unittest.main()

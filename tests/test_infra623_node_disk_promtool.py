"""promtool test of the NodeRootDiskLowOrFilling VMRule (INFRA-623).

Runs the live pocharlies.node-disk group from manifests/rules.yaml against
tests/promtool/node-disk.test.yaml (harness: tests/promtool_rules.py).
"""

import unittest

from promtool_rules import ROOT, run_promtool, vmrule_groups

CASES = ROOT / "tests" / "promtool" / "node-disk.test.yaml"


class NodeDiskPromtoolTest(unittest.TestCase):
    def test_promtool_cases(self):
        run_promtool(self, vmrule_groups("pocharlies-node-disk"), "node-disk.rules.yaml", CASES)


if __name__ == "__main__":
    unittest.main()

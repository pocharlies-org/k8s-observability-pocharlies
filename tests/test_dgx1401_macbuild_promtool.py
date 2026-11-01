"""promtool test of the pocharlies-mac-build-disk VMRule (DGX-1401).

Runs the live group from manifests/mac-build-disk-rules.yaml against
tests/promtool/mac-build-disk.test.yaml (harness: tests/promtool_rules.py).
"""

import unittest

from promtool_rules import ROOT, run_promtool, vmrule_groups

CASES = ROOT / "tests" / "promtool" / "mac-build-disk.test.yaml"
RULES_FILE = ROOT / "manifests" / "mac-build-disk-rules.yaml"


class MacBuildDiskPromtoolTest(unittest.TestCase):
    def test_promtool_cases(self):
        run_promtool(self, vmrule_groups("pocharlies-mac-build-disk", RULES_FILE),
                     "mac-build-disk.rules.yaml", CASES)


if __name__ == "__main__":
    unittest.main()

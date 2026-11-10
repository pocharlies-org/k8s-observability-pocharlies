"""promtool test of the LonghornVolumeAttachStuck VMRule (INFRA-1265, causa de SC-5058).

Runs the live pocharlies.longhorn-storage group from manifests/longhorn-rules.yaml
against tests/promtool/longhorn.test.yaml (harness: tests/promtool_rules.py).
"""

import unittest

from promtool_rules import ROOT, run_promtool, vmrule_groups

CASES = ROOT / "tests" / "promtool" / "longhorn.test.yaml"
MANIFEST = ROOT / "manifests" / "longhorn-rules.yaml"


class LonghornPromtoolTest(unittest.TestCase):
    def test_promtool_cases(self):
        run_promtool(self, vmrule_groups("pocharlies-longhorn", MANIFEST),
                     "longhorn.rules.yaml", CASES)


if __name__ == "__main__":
    unittest.main()

"""promtool test of the SparkGpuClockOverCap VMRule (INFRA-1186).

Runs the live pocharlies.gb10-clock-cap group from manifests/gb10-clock-cap-rules.yaml
against tests/promtool/gb10-clock-cap.test.yaml (harness: tests/promtool_rules.py).
"""

import unittest

from promtool_rules import ROOT, run_promtool, vmrule_groups

CASES = ROOT / "tests" / "promtool" / "gb10-clock-cap.test.yaml"
MANIFEST = ROOT / "manifests" / "gb10-clock-cap-rules.yaml"


class Gb10ClockCapPromtoolTest(unittest.TestCase):
    def test_promtool_cases(self):
        run_promtool(self, vmrule_groups("pocharlies-gb10-clock-cap", MANIFEST),
                     "gb10-clock-cap.rules.yaml", CASES)


if __name__ == "__main__":
    unittest.main()

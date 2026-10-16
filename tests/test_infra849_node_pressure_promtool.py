"""promtool test of the NodeDiskPressure VMRule (INFRA-849).

Runs the live pocharlies.node-disk group from manifests/rules.yaml against
tests/promtool/node-pressure.test.yaml (harness: tests/promtool_rules.py).
Sin series de node-exporter en los casos: prueba que la presión de disco avisa
aunque el exporter del nodo que se llena esté caído.
"""

import unittest

from promtool_rules import ROOT, run_promtool, vmrule_groups

CASES = ROOT / "tests" / "promtool" / "node-pressure.test.yaml"


class NodePressurePromtoolTest(unittest.TestCase):
    def test_promtool_cases(self):
        run_promtool(self, vmrule_groups("pocharlies-node-disk"), "node-pressure.rules.yaml", CASES)


if __name__ == "__main__":
    unittest.main()

"""promtool test de la VMRule HomeControlPlaneTCPFailing (SC-5606).

Ejecuta el grupo vivo `home.control-plane-partition` de manifests/rules.yaml
contra tests/promtool/home-control-plane-partition.test.yaml (harness:
tests/promtool_rules.py). Cubre la condición de partición que la regla de Keep
no puede expresar (motor por-alerta): casa no alcanza el API pero OVH sí.
"""

import unittest

from promtool_rules import ROOT, run_promtool, vmrule_groups

CASES = ROOT / "tests" / "promtool" / "home-control-plane-partition.test.yaml"


class HomeControlPlanePartitionPromtoolTest(unittest.TestCase):
    def test_promtool_cases(self):
        run_promtool(self, vmrule_groups("home-control-plane-partition"),
                     "home-control-plane-partition.rules.yaml", CASES)


if __name__ == "__main__":
    unittest.main()

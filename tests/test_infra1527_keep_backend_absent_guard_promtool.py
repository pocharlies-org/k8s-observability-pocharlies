"""promtool test de la guarda de KeepBackendAbsent (INFRA-1527, HUB-20314).

La regla solo arde con el scrape de kube-state-metrics sano (`and on()
max(up{job="kube-state-metrics"}) == 1`): con KSM ciego, absent() sobre la serie
del deployment era un falso positivo en cada flap del scrape (6 incidentes
keep-hub-degraded en 2 semanas con el hub sano). Casos:
tests/promtool/keep-backend-absent-guard.test.yaml (harness: tests/promtool_rules.py).
"""

import unittest

from promtool_rules import ROOT, run_promtool, vmrule_groups

CASES = ROOT / "tests" / "promtool" / "keep-backend-absent-guard.test.yaml"


class KeepBackendAbsentGuardPromtoolTest(unittest.TestCase):
    def test_promtool_cases(self):
        run_promtool(self, vmrule_groups("keep-hub-health"),
                     "keep-hub-health.rules.yaml", CASES)


if __name__ == "__main__":
    unittest.main()

"""promtool test de la guarda de KeepBackendAbsent (INFRA-1527, HUB-20314).

La regla solo arde con KSM exportando de verdad el colector de deployments
(`and on() count(kube_deployment_status_replicas_available) > 0`, idioma de
SC-6808; antes `up==1`, insuficiente: HUB-21237, 2 h 35 min de falso crítico con
KSM up==1 y el colector cegado por el metricDenylist — INFRA-1617). Con KSM
ciego, absent() sobre la serie del deployment era un falso positivo en cada flap
del scrape (6 incidentes keep-hub-degraded en 2 semanas con el hub sano). Casos:
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

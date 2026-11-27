"""promtool test del grupo pocharlies.backup-freshness (SC-6740, causa b1c1a679ed).

Fija la doble puerta de los dos absent(kube_cronjob_*): `unless on()` sobre el uptime
de vmalert (SC-6654; RecoveryKitStale no la llevaba) y `and on()
(max(up{job="kube-state-metrics"}) == 1)` (patrón KeepBackendAbsent, INFRA-1527).
Con el scrape de KSM caido (hueco de sensor, SC-6673) la ausencia de la serie no es
evidencia; con KSM vivo y la serie fuera la critica de backup dispara igual.
Corre el grupo tal cual lo sirve manifests/rules.yaml.
"""

import unittest

from promtool_rules import ROOT, run_promtool, vmrule_groups

CASES = ROOT / "tests" / "promtool" / "backup-freshness-ksm-guard.test.yaml"


class Sc6740BackupFreshnessKsmGuardPromtoolTest(unittest.TestCase):
    def test_promtool_cases(self):
        run_promtool(self, vmrule_groups("pocharlies-k8s-cronjobs"),
                     "backup-freshness.rules.yaml", CASES)


if __name__ == "__main__":
    unittest.main()

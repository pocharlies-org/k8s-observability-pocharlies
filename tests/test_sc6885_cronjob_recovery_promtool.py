"""promtool test de la supresion por recuperacion de K8sCronJobFailed (SC-6885).

La recuperacion se lee de kube_cronjob_status_last_successful_time (status del
CronJob, no lo garbage-colecta kube-state-metrics), no de la supervivencia del
objeto Job de exito (SC-6877: borrar el Job de repro reabria la alerta y Keep
abría un incidente fantasma con la misma keep-causa).
"""

import unittest

from promtool_rules import ROOT, run_promtool, vmrule_groups

CASES = ROOT / "tests" / "promtool" / "cronjob-recovery-ksm.test.yaml"


class CronjobRecoveryKsmPromtoolTest(unittest.TestCase):
    def test_promtool_cases(self):
        run_promtool(self, vmrule_groups("pocharlies-k8s-cronjobs"), "cronjob-recovery-ksm.rules.yaml", CASES)


if __name__ == "__main__":
    unittest.main()

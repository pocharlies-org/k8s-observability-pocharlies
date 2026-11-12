"""promtool test de la ventana de K8sCronJobFailed (DGX-1581).

El fallo del ultimo Job del CronJob sigue firing pasado el arranque del Job (la
ventana de 4 h sobre kube_job_status_start_time se retiro); un succeeded mas
reciente lo apaga (el `unless` sigue mandando).
"""

import unittest

from promtool_rules import ROOT, run_promtool, vmrule_groups

CASES = ROOT / "tests" / "promtool" / "cronjob-window.test.yaml"


class CronjobWindowPromtoolTest(unittest.TestCase):
    def test_promtool_cases(self):
        run_promtool(self, vmrule_groups("pocharlies-k8s-cronjobs"), "cronjob-window.rules.yaml", CASES)


if __name__ == "__main__":
    unittest.main()

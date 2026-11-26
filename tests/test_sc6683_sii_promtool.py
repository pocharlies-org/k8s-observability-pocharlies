"""promtool test del grupo pocharlies.sii-cronjobs (SC-6683, incidente SII-21053).

Fija la puerta `unless on()` de los dos absent() (SC-6654): con el backend de
metricas ciego (vmalert sin escribir en vmsingle) la ausencia de la serie
kube_cronjob_* no abre critica fiscal; con el backend vivo y la serie perdida
sigue disparando. Corre el grupo tal cual lo sirve manifests/rules.yaml.
"""

import unittest

from promtool_rules import ROOT, run_promtool, vmrule_groups

CASES = ROOT / "tests" / "promtool" / "sii-cronjobs.test.yaml"


class Sc6683SiiPromtoolTest(unittest.TestCase):
    def test_promtool_cases(self):
        run_promtool(self, vmrule_groups("pocharlies-sii-monthly-report"),
                     "sii-cronjobs.rules.yaml", CASES)


if __name__ == "__main__":
    unittest.main()

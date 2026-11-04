"""promtool test de la alerta de autenticación de la puerta del brain (INFRA-1153).

Corre el grupo pocharlies.brain-door vivo de manifests/rules.yaml contra
tests/promtool/brain-door-auth.test.yaml (harness: tests/promtool_rules.py).
Cubre las dos verificaciones del criterio: clave mala (403/401 nuevo con scrape
vivo) dispara; reinicio del vmagent (renacimiento tras hueco con contador plano)
no dispara, por la guarda de pipeline SC-2938.
"""

import unittest

from promtool_rules import ROOT, run_promtool, vmrule_groups

CASES = ROOT / "tests" / "promtool" / "brain-door-auth.test.yaml"


class BrainDoorAuthPromtoolTest(unittest.TestCase):
    def test_promtool_cases(self):
        run_promtool(self, vmrule_groups("pocharlies-brain-door"), "brain-door.rules.yaml", CASES)


if __name__ == "__main__":
    unittest.main()

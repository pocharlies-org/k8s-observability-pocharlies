"""promtool test de la supresión de LlmResidentScaledToZero (SC-6457).

El unless contra gpu_arbiter_resident_held nunca casó: la métrica la emite el backend
de control-nexus y llega con namespace="control-nexus" y exported_namespace="llm",
mientras kube_deployment_spec_replicas vive con namespace="llm" (SC-5765). Los casos
de tests/promtool/llm-resident-held.test.yaml fijan las tres cosas: el par de voz
sostenido no salta (con las etiquetas reales del 23-11), el fail-closed sin métrica
sigue saltando, y un deployment no sostenido a 0 salta aunque otro esté sostenido.

Runs the rule, extracted from manifests/rules.yaml, via tests/promtool_rules.py.
"""

import unittest

from promtool_rules import ROOT, run_promtool, vmrule_groups

CASES = ROOT / "tests" / "promtool" / "llm-resident-held.test.yaml"
ALERTS = {"LlmResidentScaledToZero"}


class LlmResidentHeldPromtoolTest(unittest.TestCase):
    def test_promtool_cases(self):
        rules = [
            r
            for g in vmrule_groups("pocharlies-service-visibility")
            for r in g["rules"]
            if r.get("alert") in ALERTS
        ]
        self.assertEqual({r["alert"] for r in rules}, ALERTS)
        run_promtool(
            self,
            [{"name": "llm-resident-held", "rules": rules}],
            "llm-resident-held.rules.yaml",
            CASES,
        )


if __name__ == "__main__":
    unittest.main()

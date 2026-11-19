"""promtool test de ArgoCDAppStuckOutOfSync (INFRA-1477, VMRule pocharlies-argocd).

Ejecuta la regla, extraída de manifests/argocd-rules.yaml (la expresión exacta
que despliega ArgoCD), contra tests/promtool/argocd-stuck.test.yaml
(harness: tests/promtool_rules.py). Cubre los cuatro casos que definen la
regla: se dispara a las 24 h justas, NO con sync manual (autosync_enabled=false,
eso es terreno del PAUSA de SC-5453), NO con un OutOfSync de deploy que se
resuelve antes, y NO con la app Synced.
"""

import unittest

from promtool_rules import ROOT, run_promtool, vmrule_groups

CASES = ROOT / "tests" / "promtool" / "argocd-stuck.test.yaml"
ALERTS = {"ArgoCDAppStuckOutOfSync"}


class ArgocdStuckPromtoolTest(unittest.TestCase):
    def test_promtool_cases(self):
        rules = [
            r
            for g in vmrule_groups("pocharlies-argocd", ROOT / "manifests" / "argocd-rules.yaml")
            for r in g["rules"]
            if r.get("alert") in ALERTS
        ]
        self.assertEqual({r["alert"] for r in rules}, ALERTS)
        run_promtool(self, [{"name": "argocd", "rules": rules}], "argocd.rules.yaml", CASES)


if __name__ == "__main__":
    unittest.main()

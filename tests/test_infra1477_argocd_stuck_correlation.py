"""Contract de la regla de correlación `argocd-app-stuck-outofsync` (INFRA-1477).

La alerta `ArgoCDAppStuckOutOfSync` de manifests/argocd-rules.yaml llega a Keep
por el catch-all `receiver: keep` de Alertmanager como `warning`, y sin regla de
correlación queda registrada y CALLA (Keep solo notifica INCIDENTES, INFRA-912).
`argocd-app-stuck-outofsync` (prefijo ATASCADO) la convierte en incidente, una
app = un incidente.

No es la CorrelationContract de keep_correlation porque esa exige agrupar por
`alertname`: la familia ArgoCD agrupa por `app` (una app = un incidente, patrón
argocd-app-degraded/argocd-app-sync-paused de SC-5453). Lo que sí comparte: los
nombres se leen de la VMRule viva, y se verifica que cada alerta de la familia
ArgoCD casa con UNA sola regla — Keep no tiene prioridad entre reglas y una
segunda coincidencia abriría dos incidentes por alerta. En particular vigila
la exclusión añadida a `argocd-app-degraded`: sin ella, la alerta nueva abriría
también un incidente ARGO con un título que miente.

Hermetic: no kubectl, no network.
"""

from pathlib import Path
import unittest

import yaml

import keep_correlation
from keep_correlation import RULES, matches, vmrule_alerts

REPO = Path(__file__).resolve().parents[1]
ARGOCD_RULES = REPO / "manifests" / "argocd-rules.yaml"


class ArgocdStuckCorrelationTests(unittest.TestCase):
    RULE = "argocd-app-stuck-outofsync"

    @classmethod
    def setUpClass(cls):
        cls.rules = keep_correlation.coverage.compose(yaml.safe_load(RULES.read_text()))
        cls.by_name = {r["ruleName"]: r for r in cls.rules}
        cls.alerts = vmrule_alerts(ARGOCD_RULES, "pocharlies-argocd")

    def test_the_vmrule_has_the_one_alert(self):
        self.assertEqual(set(self.alerts), {"ArgoCDAppStuckOutOfSync"})

    def test_each_alert_matches_the_new_rule_and_no_other(self):
        for name, labels in self.alerts.items():
            self.assertEqual(matches(self.rules, name, labels["severity"]), [self.RULE], name)

    def test_the_family_alerts_keep_their_single_rule(self):
        # Regresión de la exclusión: las tres alertas de las notificaciones de
        # ArgoCD (k8s-gitops argocd/values.yaml) siguen casando cada una con su
        # única regla tras añadir la nuestra.
        for name, rule in {
            "ArgoCDSyncFailed": "argocd-app-degraded",
            "ArgoCDAppDegraded": "argocd-app-degraded",
            "ArgoCDAppSyncPaused": "argocd-app-sync-paused",
        }.items():
            self.assertEqual(matches(self.rules, name, "warning"), [rule], name)

    def test_lifecycle_prefix_and_grouping(self):
        rule = self.by_name[self.RULE]
        self.assertEqual(rule["createOn"], "any")
        self.assertEqual(rule["resolveOn"], "all_resolved")
        self.assertEqual(rule["timeUnit"], "minutes")
        self.assertEqual(rule["groupingCriteria"], ["app"])
        self.assertEqual(rule["incidentPrefix"], "ATASCADO")
        prefixes = [r["incidentPrefix"] for r in self.rules]
        self.assertEqual(prefixes.count("ATASCADO"), 1, "incidentPrefix propio")
        self.assertIn("{{ app }}", rule["incidentNameTemplate"])


if __name__ == "__main__":
    unittest.main()

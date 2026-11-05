"""Contract for the mac-build liveness alert (DGX-1440).

`MacBuildUnreachableOrBridgeDown` (manifests/mac-build-liveness-rules.yaml) es
`critical` y llega a Keep por el catch-all de Alertmanager; el incidente lo abre la
regla `mac-build-disk` de keep/rules/correlation-rules.yaml — misma familia mac-build
(celQuery `name.startsWith("MacBuild")`, prefijo MBD) que las de disco, mismo
destinatario. Sin regla no habría incidente (Keep solo notifica INCIDENTES); sin la
exclusión de `critical-safety-net` (`startsWith("MacBuild")`, ya existente) serían dos
incidentes por la misma alerta. Las comprobaciones compartidas viven en
``keep_correlation.CorrelationContract``. Hermetic: no kubectl, no network.
"""

import unittest
from pathlib import Path

from keep_correlation import CorrelationContract


class MacBuildLivenessCorrelationTests(CorrelationContract, unittest.TestCase):
    # La casa la regla mac-build-disk existente (misma familia, prefijo MBD): por eso
    # RULE apunta ahí y no hay regla nueva — el celQuery `startsWith("MacBuild")` de
    # arriba ya la cubre, y tests/test_dgx1401_macbuild_correlation.py sigue vigilando
    # la de disco sobre su propio VMRule.
    RULE = "mac-build-disk"
    VMRULE = "pocharlies-mac-build-liveness"
    VMRULE_FILE = (Path(__file__).resolve().parents[1]
                   / "manifests" / "mac-build-liveness-rules.yaml")
    INCIDENT_NAME = "mac-build: {{ alertname }}"

    def test_severidad(self):
        # Critical: la ocurrencia del 03-11 dejó 15 h parados los builds y las pruebas
        # de ux (DGX-1432, revisión de DGX-799 bloqueada) con tailscaled muerto y los
        # runners de GitHub aún "online". La vía rápida de la Request exige página, no
        # el warning de 12 h de MacBuildUnreachable (ese es «el portátil duerme», uso
        # normal); al ser critical, la exclusión del safety-net por `MacBuild` hace
        # falta de verdad y test_safety_net_does_not_double_notify la comprueba.
        self.assertEqual(self.alerts["MacBuildUnreachableOrBridgeDown"], "critical")


if __name__ == "__main__":
    unittest.main()

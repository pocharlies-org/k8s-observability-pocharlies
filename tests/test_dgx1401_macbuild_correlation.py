"""Contract for the mac-build-disk correlation rule (DGX-1401).

The two alerts of ``manifests/mac-build-disk-rules.yaml`` (umbral del 90 % y ceguera
de la métrica) son `critical` y llegan a Keep por el catch-all de Alertmanager; sin
regla de correlación no habría incidente (Keep solo notifica INCIDENTES). Van además
EXCLUIDAS de `critical-safety-net` — patrón node-degraded: dos reglas para la misma
alerta serían dos incidentes. Las comprobaciones compartidas viven en
``keep_correlation.CorrelationContract``; la de "una sola regla" usa la severidad real
del VMRule (critical), así que la exclusión del safety-net se comprueba de verdad.

Hermetic: no kubectl, no network.
"""

from pathlib import Path
import unittest

from keep_correlation import CorrelationContract

REPO = Path(__file__).resolve().parents[1]


class MacBuildDiskCorrelationTests(CorrelationContract, unittest.TestCase):
    RULE = "mac-build-disk"
    VMRULE_FILE = REPO / "manifests" / "mac-build-disk-rules.yaml"
    VMRULE = "pocharlies-mac-build-disk"
    INCIDENT_NAME = "mac-build: {{ alertname }}"

    def test_severidades(self):
        # Las dos de disco no son warning al estilo frigate: el disco lleno corta los
        # builds de pruebas (INFRA-827) y el entorno de DGX-1392; y la ceguera del emisor
        # con el Mac despierto es el fallo que INFRA-849 dejó sin destinatario. Critical +
        # exclusión del safety-net. MacBuildUnreachable (SC-4378) es warning: un Mac
        # dormido de tarde es el uso normal de Dani; medio día sin responder es lo raro,
        # y al safety-net (sólo critical) no llega, así que no hace falta excluirlo.
        self.assertEqual(self.alerts["MacBuildDiskLowOrFilling"], "critical")
        self.assertEqual(self.alerts["MacBuildDiskMetricStale"], "critical")
        self.assertEqual(self.alerts["MacBuildUnreachable"], "warning")


if __name__ == "__main__":
    unittest.main()

"""Contract for the gmail-oauth-token correlation rule (SC-5955).

Las dos alertas de ``manifests/gmail-token-rules.yaml`` llegan como ``warning``
y, sin regla de correlación, Keep las registra y calla (SC-5911: el DLQ ya
crecía cuando saltó RabbitmqDlqGrowth — el detector era el backstop). La regla
``gmail-oauth-token`` las convierte en incidente notificado, y solo ella las
casa: los nombres no empiezan por ``Synapse`` para no caer en
``synapse-control-plane`` (servicios, no credenciales).

The checks every such rule shares live in ``keep_correlation.CorrelationContract``;
this file keeps only what is specific to the family.

Hermetic: no kubectl, no network.
"""

from pathlib import Path
import unittest

from keep_correlation import CorrelationContract

REPO = Path(__file__).resolve().parents[1]


class GmailTokenCorrelationTests(CorrelationContract, unittest.TestCase):
    RULE = "gmail-oauth-token"
    VMRULE_FILE = REPO / "manifests" / "gmail-token-rules.yaml"
    VMRULE = "pocharlies-gmail-token"
    INCIDENT_NAME = "OAuth de Gmail caído: {{ alertname }}"

    def test_the_vmrule_has_the_two_alerts_all_warning(self):
        # All warning: critical-safety-net no las toca (shared test). Subir una a
        # critical la duplicaría en el safety-net y fallaría ese test: es el punto.
        self.assertEqual(
            self.alerts,
            {"GmailTokenInvalid": "warning", "CorreoTokenInvalido": "warning"},
        )


if __name__ == "__main__":
    unittest.main()

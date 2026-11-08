"""Contract for the CI-queue correlation rule (INFRA-550, P4 of INFRA-400).

The alerts of ``manifests/arc-rules.yaml`` arrive as ``warning`` and, without
a correlation rule, Keep records them and stays silent (Keep only notifies
INCIDENTS): they never reached topic 1248. ``ci-queue-degraded`` turns them into
one incident. The names are read from the live VMRule, not copied, so a new
``CI*`` alert added later fails here until the rule covers it.

The checks every such rule shares live in ``keep_correlation.CorrelationContract``;
this file keeps only what is specific to the CI-queue family.

Hermetic: no kubectl, no network.
"""

from pathlib import Path
import unittest

from keep_correlation import CorrelationContract, matches

ARC_RULES = Path(__file__).resolve().parents[1] / "manifests" / "arc-rules.yaml"


class CiQueueCorrelationTests(CorrelationContract, unittest.TestCase):
    RULE = "ci-queue-degraded"
    VMRULE_FILE = ARC_RULES
    VMRULE = "pocharlies-arc-ci"
    INCIDENT_NAME = "Cola de CI: {{ alertname }}"

    def test_the_vmrule_has_the_seven_alerts(self):
        # INFRA-1056: dos alertas de pool autoalojado (CIQueueSelfHostedJobQueuedTooLong
        # y CIQueueNexusMacQueueStuck) se suman a las cinco de INFRA-550. Todas
        # con prefijo CIQueue* → las enruta ci-queue-degraded al tema 1248.
        self.assertEqual(len(self.alerts), 7, sorted(self.alerts))


if __name__ == "__main__":
    unittest.main()

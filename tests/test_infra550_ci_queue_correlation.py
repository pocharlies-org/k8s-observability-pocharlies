"""Contract for the CI-queue correlation rule (INFRA-550, P4 of INFRA-400).

The five alerts of ``manifests/arc-rules.yaml`` arrive as ``warning`` and, without
a correlation rule, Keep records them and stays silent (Keep only notifies
INCIDENTS): they never reached topic 1248. ``ci-queue-degraded`` turns them into
one incident. The names are read from the live VMRule, not copied, so a sixth
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

    def test_the_vmrule_has_the_five_alerts(self):
        self.assertEqual(len(self.alerts), 5, sorted(self.alerts))

    def test_trunk_ci_failed_keeps_its_own_rule(self):
        # `CI` prefix is trunk-ci-failed's; the new rule must not capture it.
        self.assertEqual(matches(self.rules, "TrunkCIFailed"), ["trunk-ci-failed"])


if __name__ == "__main__":
    unittest.main()

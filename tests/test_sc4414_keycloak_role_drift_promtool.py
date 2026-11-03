"""promtool test of KeycloakRoleDriftConsecutiveFailures (SC-4414).

Runs the live pocharlies.k8s-cronjobs group from manifests/rules.yaml against
tests/promtool/keycloak-role-drift.test.yaml (harness: tests/promtool_rules.py):
a single failed cycle of keycloak-role-drift stays silent (neither this alert
nor the excluded K8sCronJobFailed), two consecutive failures fire it, a newer
success clears it, and another CronJob in the namespace still reaches the
generic rule.
"""

import unittest

from promtool_rules import ROOT, run_promtool, vmrule_groups

CASES = ROOT / "tests" / "promtool" / "keycloak-role-drift.test.yaml"


class KeycloakRoleDriftPromtoolTest(unittest.TestCase):
    def test_promtool_cases(self):
        run_promtool(self, vmrule_groups("pocharlies-k8s-cronjobs"), "keycloak-role-drift.rules.yaml", CASES)


if __name__ == "__main__":
    unittest.main()

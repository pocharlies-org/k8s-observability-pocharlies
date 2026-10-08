"""Contract for the CI-queue correlation rule (INFRA-550, P4 of INFRA-400).

The five alerts of ``manifests/arc-rules.yaml`` arrive as ``warning`` and, without
a correlation rule, Keep records them and stays silent (Keep only notifies
INCIDENTS): they never reached topic 1248. ``ci-queue-degraded`` turns them into
one incident. The names are read from the live VMRule, not copied, so a sixth
``CI*`` alert added later fails here until the rule covers it.

Reuses the composition (chronic expansion) and the CEL evaluator of
``scripts/verify-notification-coverage.py``, like test_infra405_correlation_rules.
When ``celpy`` (the engine Keep runs, rulesengine.py) is installed the same
matrix is also evaluated with it; CI does not install it, so that part skips.

Hermetic: no kubectl, no network.
"""

from pathlib import Path
import importlib.util
import unittest

import yaml

REPO = Path(__file__).resolve().parents[1]
RULES = REPO / "keep" / "rules" / "correlation-rules.yaml"
ARC_RULES = REPO / "manifests" / "arc-rules.yaml"

_spec = importlib.util.spec_from_file_location(
    "verify_notification_coverage", REPO / "scripts" / "verify-notification-coverage.py"
)
coverage = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(coverage)

NEW = "ci-queue-degraded"


def arc_alerts():
    """alertname -> severity of every rule of the VMRule pocharlies-arc-ci."""
    docs = [d for d in yaml.safe_load_all(ARC_RULES.read_text()) if d]
    vmrule = next(d for d in docs if d["metadata"]["name"] == "pocharlies-arc-ci")
    return {
        r["alert"]: r["labels"]["severity"]
        for g in vmrule["spec"]["groups"]
        for r in g["rules"]
    }


def matches(rules, name, severity="warning"):
    return [r["ruleName"] for r in rules if coverage.cel_matches(r["celQuery"], name, severity)]


class CiQueueCorrelationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = yaml.safe_load(RULES.read_text())
        cls.rules = coverage.compose(cls.spec)
        cls.by_name = {r["ruleName"]: r for r in cls.rules}
        cls.alerts = arc_alerts()

    def test_the_vmrule_has_the_five_alerts(self):
        self.assertEqual(len(self.alerts), 5, sorted(self.alerts))

    def test_each_alert_matches_the_new_rule_and_no_other(self):
        # Keep has no priority between rules: a second match would open two
        # incidents for one alert.
        for name, severity in self.alerts.items():
            self.assertEqual(matches(self.rules, name, severity), [NEW], name)

    def test_trunk_ci_failed_keeps_its_own_rule(self):
        # `CI` prefix is trunk-ci-failed's; the new rule must not capture it.
        self.assertEqual(matches(self.rules, "TrunkCIFailed"), ["trunk-ci-failed"])

    def test_lifecycle_prefix_and_not_chronic(self):
        rule = self.by_name[NEW]
        self.assertEqual(rule["createOn"], "any")
        self.assertEqual(rule["resolveOn"], "all_resolved")
        self.assertEqual(rule["timeUnit"], "minutes")
        prefixes = [r["incidentPrefix"] for r in self.rules]
        self.assertEqual(prefixes.count(rule["incidentPrefix"]), 1, "incidentPrefix propio")
        self.assertIn("!(name in [", rule["celQuery"], "apply-job le aplica la exclusión de crónicas")
        self.assertFalse(set(self.alerts) & set(self.spec["chronic"]))

    def test_incident_name_is_a_stable_cause_key(self):
        # ops-watch hashes the name (keep-causa): no volatile numbers.
        self.assertEqual(self.by_name[NEW]["incidentNameTemplate"], "Cola de CI atascada")

    def test_safety_net_does_not_double_notify(self):
        net = self.by_name["critical-safety-net"]["celQuery"]
        for name in self.alerts:
            self.assertFalse(coverage.cel_matches(net, name, "warning"), name)

    def test_same_matrix_with_celpy_when_installed(self):
        try:
            import celpy
        except ImportError:
            self.skipTest("celpy not installed")
        env = celpy.Environment()
        for name, severity in self.alerts.items():
            act = {"name": celpy.celtypes.StringType(name),
                   "severity": celpy.celtypes.StringType(severity),
                   "labels": celpy.json_to_cel({"area": "infra", "severity": severity}),
                   "annotations": celpy.json_to_cel({}), "source": celpy.json_to_cel(["prometheus"])}
            hit = [r["ruleName"] for r in self.rules
                   if bool(env.program(env.compile(r["celQuery"])).evaluate(act))]
            self.assertEqual(hit, [NEW], name)


if __name__ == "__main__":
    unittest.main()

"""Contract for the Frigate correlation rule (INFRA-712, P2b of INFRA-701).

The four alerts of ``manifests/frigate-rules.yaml`` arrive as ``warning`` and, without
a correlation rule, Keep records them and stays silent (Keep only notifies
INCIDENTS): they never reached topic 1248. ``frigate-vigilancia`` turns them into
one incident per alert family. There is no Alertmanager route to add: the tree ends in a
catch-all to Keep and no warning blackhole exists any more (alertmanager-config.yaml).
The names are read from the live VMRule, not copied, so a fifth ``Frigate*`` alert added
later fails here until the rule covers it.

Same shape as test_infra550_ci_queue_correlation: composition and CEL evaluator of
``scripts/verify-notification-coverage.py``; when ``celpy`` (the engine Keep runs) is
installed the same matrix is also evaluated with it. Hermetic: no kubectl, no network.
"""

from pathlib import Path
import importlib.util
import unittest

import yaml

REPO = Path(__file__).resolve().parents[1]
RULES = REPO / "keep" / "rules" / "correlation-rules.yaml"
FRIGATE_RULES = REPO / "manifests" / "frigate-rules.yaml"

_spec = importlib.util.spec_from_file_location(
    "verify_notification_coverage", REPO / "scripts" / "verify-notification-coverage.py"
)
coverage = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(coverage)

NEW = "frigate-vigilancia"


def frigate_alerts():
    """alertname -> severity of every rule of the VMRule pocharlies-frigate."""
    docs = [d for d in yaml.safe_load_all(FRIGATE_RULES.read_text()) if d]
    vmrule = next(d for d in docs if d["metadata"]["name"] == "pocharlies-frigate")
    return {
        r["alert"]: r["labels"]["severity"]
        for g in vmrule["spec"]["groups"]
        for r in g["rules"]
    }


def matches(rules, name, severity="warning"):
    return [r["ruleName"] for r in rules if coverage.cel_matches(r["celQuery"], name, severity)]


class FrigateCorrelationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = yaml.safe_load(RULES.read_text())
        cls.rules = coverage.compose(cls.spec)
        cls.by_name = {r["ruleName"]: r for r in cls.rules}
        cls.alerts = frigate_alerts()

    def test_the_vmrule_has_the_four_alerts(self):
        self.assertEqual(
            sorted(self.alerts),
            ["FrigateAlmacenamientoLleno", "FrigateCaido", "FrigateCamaraSinFps", "FrigateDetectorLento"],
        )

    def test_each_alert_matches_the_new_rule_and_no_other(self):
        # Keep has no priority between rules: a second match would open two
        # incidents for one alert.
        for name, severity in self.alerts.items():
            self.assertEqual(matches(self.rules, name, severity), [NEW], name)

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
        # One incident per alert family: without alertname in the grouping, an open
        # incident (FrigateCaido) swallows the next alert without a notice.
        rule = self.by_name[NEW]
        self.assertEqual(rule["groupingCriteria"], ["alertname"])
        self.assertEqual(rule["incidentNameTemplate"], "Vigilancia: {{ alertname }}")
        names = {rule["incidentNameTemplate"].replace("{{ alertname }}", n) for n in self.alerts}
        self.assertEqual(len(names), len(self.alerts), names)
        self.assertFalse(any(ch.isdigit() for n in names for ch in n), names)

    def test_safety_net_does_not_double_notify(self):
        # All four are warning: the critical net does not pick them. Raising one to
        # critical would double-notify (and fails here, which is the point).
        net = self.by_name["critical-safety-net"]["celQuery"]
        for name, severity in self.alerts.items():
            self.assertEqual(severity, "warning", name)
            self.assertFalse(coverage.cel_matches(net, name, severity), name)

    def test_no_alertmanager_route_needed(self):
        # Everything reaches Keep through the catch-all; no blackhole to get in front of.
        cfg = yaml.safe_load((REPO / "manifests" / "alertmanager-config.yaml").read_text())
        route = cfg["spec"]["route"]
        self.assertEqual(route["receiver"], "keep")
        self.assertEqual(route["routes"][-1], {"receiver": "keep"})
        self.assertNotIn("blackhole", {r["name"] for r in cfg["spec"]["receivers"]})

    def test_same_matrix_with_celpy_when_installed(self):
        try:
            import celpy
        except ImportError:
            self.skipTest("celpy not installed")
        env = celpy.Environment()
        for name, severity in self.alerts.items():
            act = {"name": celpy.celtypes.StringType(name),
                   "severity": celpy.celtypes.StringType(severity),
                   "labels": celpy.json_to_cel({"severity": severity}),
                   "annotations": celpy.json_to_cel({}), "source": celpy.json_to_cel(["prometheus"])}
            hit = [r["ruleName"] for r in self.rules
                   if bool(env.program(env.compile(r["celQuery"])).evaluate(act))]
            self.assertEqual(hit, [NEW], name)


if __name__ == "__main__":
    unittest.main()

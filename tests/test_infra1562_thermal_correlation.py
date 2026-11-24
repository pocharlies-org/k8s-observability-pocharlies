"""Contract for the spark-thermal-halt correlation rule (INFRA-1562).

Gx10ThermalHaltImminent lives in ANOTHER repo (dgx-infra
k8s/monitoring/gx10-thermal/vmrule.yaml, INFRA-1332), so this suite cannot read the
alertname from the live VMRule like ``CorrelationContract`` does; the alertname is
pinned here as the coupling key and the vmrule carries the matching ACOPLE comment:
rename it there and this test must fail loudly until the celQuery follows.

Medido 24-11 (halt de dgx2 18:52Z): la alerta llegaba a Keep como alerta `warning` y
no casaba con NINGUNA regla -> 3 alertas desde el 12-11, 0 incidentes, 0 Telegram
(critical-safety-net solo coge critical/page). Keep notifica INCIDENTES, no alertas.

Hermetic: no kubectl, no network.
"""

from pathlib import Path
import importlib.util
import unittest

import yaml

REPO = Path(__file__).resolve().parents[1]

spec = importlib.util.spec_from_file_location(
    "verify_coverage", REPO / "scripts" / "verify-notification-coverage.py")
coverage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(coverage)

RULE = "spark-thermal-halt"
ALERT = "Gx10ThermalHaltImminent"


class SparkThermalHaltCorrelationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec_rules = yaml.safe_load(
            (REPO / "keep" / "rules" / "correlation-rules.yaml").read_text())
        cls.rules = coverage.compose(spec_rules)
        cls.by_name = {r["ruleName"]: r for r in cls.rules}

    def test_rule_exists(self):
        self.assertIn(RULE, self.by_name)

    def test_the_alert_matches_this_rule_and_no_other(self):
        # Keep has no priority between rules: a second match would open two
        # incidents for one halt.
        hit = [r["ruleName"] for r in self.rules
               if coverage.cel_matches(r["celQuery"], ALERT, "warning")]
        self.assertEqual(hit, [RULE])

    def test_lifecycle_and_prefix(self):
        rule = self.by_name[RULE]
        self.assertEqual(rule["createOn"], "any")
        self.assertEqual(rule["resolveOn"], "all_resolved")
        self.assertEqual(rule["timeUnit"], "minutes")
        prefixes = [r["incidentPrefix"] for r in self.rules]
        self.assertEqual(prefixes.count(rule["incidentPrefix"]), 1, "incidentPrefix propio")

    def test_grouped_by_node_with_a_stable_cause_name(self):
        # ops-watch derives keep-causa from a sha1 of the incident name: the name
        # must carry the (stable) node label and no volatile numbers, so each Spark
        # opens exactly ONE incident.
        rule = self.by_name[RULE]
        self.assertEqual(rule["groupingCriteria"], ["node"])
        name = rule["incidentNameTemplate"]
        self.assertIn("{{ node }}", name)
        self.assertFalse(any(ch.isdigit() for ch in name), name)

    def test_not_double_caught_by_safety_net(self):
        # INVARIANTE 1: excluded from the safety-net without own rule = silenced;
        # here the opposite: warning never reaches the safety-net (critical/page),
        # so the new rule must NOT require an exclusion entry.
        net = self.by_name["critical-safety-net"]["celQuery"]
        self.assertFalse(coverage.cel_matches(net, ALERT, "warning"))

    def test_same_matrix_with_celpy_when_installed(self):
        try:
            import celpy
        except ImportError:
            self.skipTest("celpy not installed")
        env = celpy.Environment()
        act = {"name": celpy.celtypes.StringType(ALERT),
               "severity": celpy.celtypes.StringType("warning"),
               "labels": celpy.json_to_cel({}),
               "annotations": celpy.json_to_cel({}),
               "source": celpy.json_to_cel(["prometheus"])}
        hit = [r["ruleName"] for r in self.rules
               if bool(env.program(env.compile(r["celQuery"])).evaluate(act))]
        self.assertEqual(hit, [RULE])


if __name__ == "__main__":
    unittest.main()

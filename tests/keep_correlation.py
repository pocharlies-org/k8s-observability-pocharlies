"""Shared contract of the Keep correlation rules that turn a VMRule into an incident.

Used by test_infra550_ci_queue_correlation and test_infra712_frigate_correlation (next to
``promtool_rules.py``, the harness of the promtool suites). A VMRule whose alerts arrive as
``warning`` and have no rule in ``keep/rules/correlation-rules.yaml`` is recorded by Keep and
stays silent (Keep only notifies INCIDENTS), so every such family gets a rule and the same
five checks; the alert names are read from the live VMRule, never copied, so a new alert of
the family fails until the rule covers it.

Reuses the composition (chronic expansion) and the CEL evaluator of
``scripts/verify-notification-coverage.py``, like test_infra405_correlation_rules. When
``celpy`` (the engine Keep runs, rulesengine.py) is installed the same matrix is also
evaluated with it; CI does not install it, so that part skips. Hermetic: no kubectl, no network.

A suite subclasses ``CorrelationContract`` together with ``unittest.TestCase`` and sets
``RULE`` (ruleName), ``VMRULE_FILE``, ``VMRULE`` (metadata.name) and ``INCIDENT_NAME``
(incidentNameTemplate).
"""

from pathlib import Path
import importlib.util

import yaml

REPO = Path(__file__).resolve().parents[1]
RULES = REPO / "keep" / "rules" / "correlation-rules.yaml"


def _load(script):
    spec = importlib.util.spec_from_file_location(script.stem.replace("-", "_"), script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


coverage = _load(REPO / "scripts" / "verify-notification-coverage.py")


def vmrule_alerts(vmrule_file, name):
    """alertname -> labels of every rule of the VMRule `name` in `vmrule_file`."""
    docs = [d for d in yaml.safe_load_all(Path(vmrule_file).read_text()) if d]
    vmrule = next(d for d in docs if d["metadata"]["name"] == name)
    return {r["alert"]: r["labels"] for g in vmrule["spec"]["groups"] for r in g["rules"]}


def matches(rules, name, severity="warning"):
    return [r["ruleName"] for r in rules if coverage.cel_matches(r["celQuery"], name, severity)]


class CorrelationContract:
    RULE = VMRULE_FILE = VMRULE = INCIDENT_NAME = None

    @classmethod
    def setUpClass(cls):
        cls.spec = yaml.safe_load(RULES.read_text())
        cls.rules = coverage.compose(cls.spec)
        cls.by_name = {r["ruleName"]: r for r in cls.rules}
        cls.labels = vmrule_alerts(cls.VMRULE_FILE, cls.VMRULE)
        cls.alerts = {name: labels["severity"] for name, labels in cls.labels.items()}

    def test_each_alert_matches_the_new_rule_and_no_other(self):
        # Keep has no priority between rules: a second match would open two
        # incidents for one alert.
        for name, severity in self.alerts.items():
            self.assertEqual(matches(self.rules, name, severity), [self.RULE], name)

    def test_lifecycle_prefix_and_not_chronic(self):
        rule = self.by_name[self.RULE]
        self.assertEqual(rule["createOn"], "any")
        self.assertEqual(rule["resolveOn"], "all_resolved")
        self.assertEqual(rule["timeUnit"], "minutes")
        prefixes = [r["incidentPrefix"] for r in self.rules]
        self.assertEqual(prefixes.count(rule["incidentPrefix"]), 1, "incidentPrefix propio")
        self.assertIn("!(name in [", rule["celQuery"], "apply-job le aplica la exclusión de crónicas")
        self.assertFalse(set(self.alerts) & set(self.spec["chronic"]))

    def test_incident_name_is_a_stable_cause_key(self):
        # One incident per alert family (cron-job-failed pattern): without alertname
        # in the grouping, an open incident swallows the next alert without a notice.
        rule = self.by_name[self.RULE]
        self.assertEqual(rule["groupingCriteria"], ["alertname"])
        self.assertEqual(rule["incidentNameTemplate"], self.INCIDENT_NAME)
        # ops-watch hashes the name (keep-causa): one distinct name per alert, no volatile numbers.
        names = {rule["incidentNameTemplate"].replace("{{ alertname }}", n) for n in self.alerts}
        self.assertEqual(len(names), len(self.alerts), names)
        self.assertFalse(any(ch.isdigit() for n in names for ch in n), names)

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
        for name, labels in self.labels.items():
            act = {"name": celpy.celtypes.StringType(name),
                   "severity": celpy.celtypes.StringType(labels["severity"]),
                   "labels": celpy.json_to_cel(labels),
                   "annotations": celpy.json_to_cel({}), "source": celpy.json_to_cel(["prometheus"])}
            hit = [r["ruleName"] for r in self.rules
                   if bool(env.program(env.compile(r["celQuery"])).evaluate(act))]
            self.assertEqual(hit, [self.RULE], name)

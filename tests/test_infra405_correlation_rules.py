"""Contract for the x86 correlation rules (INFRA-405, P2 of INFRA-394).

Pins the rules that turn the alert families pushed by ops-watch
(`empujar_a_keep` in x86-host-runtime-pocharlies) into incidents:

* ``x86-unit-failed``     — ``X86UnitFailed``, grouped by ``unit``, 1800 s, X86U
* ``trunk-ci-stale``      — ``TrunkCIStale``, grouped by ``repo``+``workflow``,
  1800 s, STALE (SC-2459: schedule muerto)

(INFRA-882: CI en rojo and update-watch no longer reach Keep.)

The rules live in ``keep/rules/correlation-rules.yaml`` and are applied by
``keep/rules/apply-job.yaml`` (not by the chart).  The incident NAME is part of
P4's cause key (``keep-causa:<rule_name>:<sha1(name)>`` in ops-watch), so the
template must carry the grouping label and no volatile numbers — a name that
drifted between two alerts of the same cause would open two IT Requests.

The tests reuse the composition and the CEL
evaluator from ``scripts/verify-notification-coverage.py`` rather than
reimplementing them: that file is the gate that keeps the rules honest, and
duplicating its logic here would let the two drift.

Hermetic: no kubectl, no network.
"""

from pathlib import Path
import importlib.util
import re
import unittest

import yaml

REPO = Path(__file__).resolve().parents[1]
RULES = REPO / "keep" / "rules" / "correlation-rules.yaml"

_spec = importlib.util.spec_from_file_location(
    "verify_notification_coverage", REPO / "scripts" / "verify-notification-coverage.py"
)
coverage = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(coverage)

# Family -> the contract from the architect's plan (nota-architect-plan.md, P2).
X86_RULES = {
    "x86-unit-failed": {
        "alert": "X86UnitFailed",
        "groupingCriteria": ["unit"],
        "timeframeInSeconds": 1800,
        "incidentPrefix": "X86U",
        "nameTemplate": "x86: {{ unit }} fallida",
    },
    "trunk-ci-stale": {
        # SC-2459: schedule muerto (CI muerto > CI rojo). Agrupa por repo Y workflow.
        "alert": "TrunkCIStale",
        "groupingCriteria": ["repo", "workflow"],
        "timeframeInSeconds": 1800,
        "incidentPrefix": "STALE",
        "nameTemplate": "Schedule muerto: {{ repo }}/{{ workflow }}",
    },
}


def load():
    spec = yaml.safe_load(RULES.read_text())
    return spec, {r["ruleName"]: r for r in coverage.compose(spec)}


class X86CorrelationRulesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec, cls.rules = load()

    def test_the_x86_rules_exist(self):
        for name in X86_RULES:
            self.assertIn(name, self.rules, f"falta la regla {name}")

    def test_grouping_timeframe_prefix_and_lifecycle(self):
        for name, want in X86_RULES.items():
            rule = self.rules[name]
            self.assertEqual(rule["groupingCriteria"], want["groupingCriteria"], name)
            self.assertEqual(rule["timeframeInSeconds"], want["timeframeInSeconds"], name)
            self.assertEqual(rule["incidentPrefix"], want["incidentPrefix"], name)
            self.assertEqual(rule["createOn"], "any", name)
            self.assertEqual(rule["resolveOn"], "all_resolved", name)
            self.assertEqual(rule["timeUnit"], "minutes", name)

    def test_cel_matches_its_family(self):
        for name, want in X86_RULES.items():
            cel = self.rules[name]["celQuery"]
            self.assertTrue(coverage.cel_matches(cel, want["alert"], "warning"), f"{name} no casa con {want['alert']}")

    def test_no_overlap_with_critical_safety_net(self):
        # The families arrive as `warning`, and the safety net only captures
        # `severity == "critical" || labels.severity == "page"`, so they must
        # NOT be added to its exclusion list (invariante 1: exclusions delegate,
        # and excluding something without a rule would silence it — here there
        # is no duplicate to exclude in the first place).
        net = self.rules["critical-safety-net"]["celQuery"]
        for name, want in X86_RULES.items():
            self.assertFalse(
                coverage.cel_matches(net, want["alert"], "warning"),
                f"{want['alert']} (warning) solaparía con critical-safety-net",
            )
            self.assertNotIn(want["alert"], net, f"{name}: no debe estar excluida del safety-net")

    def test_incident_name_template_is_stable_cause_key(self):
        # The name feeds P4's keep-causa: exactly the grouping label, no digits.
        for name, want in X86_RULES.items():
            template = self.rules[name]["incidentNameTemplate"]
            self.assertEqual(template, want["nameTemplate"], name)
            label = want["groupingCriteria"][0]
            self.assertIn(f"{{{{ {label} }}}}", template, name)
            # "x86" is the static host name; any OTHER digit would be a
            # volatile number riding in the cause key.
            self.assertIsNone(
                re.search(r"\d", template.replace("x86", "")),
                f"{name}: el nombre del incidente no puede llevar números volátiles",
            )


if __name__ == "__main__":
    unittest.main()


class OneIncidentPerAlertTests(unittest.TestCase):
    """INFRA-882: Keep no prioriza reglas; una alerta que casa con dos abre dos incidentes
    (SynapseWorkflowFailed abría SYNC y SYNW a la vez)."""

    def test_every_vmrule_alert_matches_at_most_one_rule(self):
        _, rules = load()
        for path in sorted((REPO / "manifests").glob("*.yaml")):
            for doc in yaml.safe_load_all(path.read_text()):
                if not doc or doc.get("kind") != "VMRule":
                    continue
                for rule in (r for g in doc["spec"]["groups"] for r in g["rules"] if "alert" in r):
                    sev = rule.get("labels", {}).get("severity", "warning")
                    hits = [n for n, r in rules.items() if coverage.cel_matches(r["celQuery"], rule["alert"], sev)]
                    self.assertLessEqual(len(hits), 1, f"{path.name}: {rule['alert']} casa con {hits}")

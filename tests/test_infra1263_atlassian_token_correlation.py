"""Contract for the Atlassian token-expiry correlation rule (INFRA-1263).

Pins the rule that turns the family pushed by ops-watch (`empujar_a_keep`,
source `tokens-atlassian` in x86-host-runtime-pocharlies) into an incident:

* ``atlassian-token-expiry`` — ``AtlassianTokenExpiring``, grouped by
  ``account``, 1800 s, ATLTK

Why it exists: the weekly rotation batch is structurally slower than a token
expiring in <7 days (SC-5115: the sonda-mcp token died in service with the
rotation task open 34 h before). The IT Request this incident opens schedules
the rotation with Dani BEFORE the expiry.

Same checks as ``test_infra405_correlation_rules`` (that file is the pattern
for ops-watch-pushed families): the incident NAME is part of P4's cause key
(``keep-causa:<rule_name>:<sha1(name)>`` in ops-watch), so the template must
carry the grouping label and no volatile numbers.

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

RULE = {
    "atlassian-token-expiry": {
        "alert": "AtlassianTokenExpiring",
        "groupingCriteria": ["account"],
        "timeframeInSeconds": 1800,
        "incidentPrefix": "ATLTK",
        "nameTemplate": "Token de Atlassian a punto de caducar: {{ account }}",
    },
}


def load():
    spec = yaml.safe_load(RULES.read_text())
    return spec, {r["ruleName"]: r for r in coverage.compose(spec)}


class AtlassianTokenCorrelationRulesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec, cls.rules = load()

    def test_the_rule_exists(self):
        for name in RULE:
            self.assertIn(name, self.rules, f"falta la regla {name}")

    def test_grouping_timeframe_prefix_and_lifecycle(self):
        for name, want in RULE.items():
            rule = self.rules[name]
            self.assertEqual(rule["groupingCriteria"], want["groupingCriteria"], name)
            self.assertEqual(rule["timeframeInSeconds"], want["timeframeInSeconds"], name)
            self.assertEqual(rule["incidentPrefix"], want["incidentPrefix"], name)
            self.assertEqual(rule["createOn"], "any", name)
            self.assertEqual(rule["resolveOn"], "all_resolved", name)
            self.assertEqual(rule["timeUnit"], "minutes", name)

    def test_cel_matches_its_family(self):
        for name, want in RULE.items():
            cel = self.rules[name]["celQuery"]
            self.assertTrue(coverage.cel_matches(cel, want["alert"], "warning"),
                            f"{name} no casa con {want['alert']}")

    def test_no_overlap_with_critical_safety_net(self):
        # La alerta llega como `warning` (empujar_a_keep): el safety-net solo
        # captura critical/page, así que no solapa ni hay que excluir nada
        # (INVARIANTE 1: no se excluye lo que no se duplica).
        net = self.rules["critical-safety-net"]["celQuery"]
        for name, want in RULE.items():
            self.assertFalse(
                coverage.cel_matches(net, want["alert"], "warning"),
                f"{want['alert']} (warning) solaparía con critical-safety-net",
            )
            self.assertNotIn(want["alert"], net, f"{name}: no debe estar excluida del safety-net")

    def test_incident_name_template_is_stable_cause_key(self):
        # El nombre alimenta la keep-causa de ops-watch: solo la etiqueta de
        # agrupación, sin números (una fecha en el nombre abriría dos Requests
        # por la misma cuenta al cambiar el día).
        for name, want in RULE.items():
            template = self.rules[name]["incidentNameTemplate"]
            self.assertEqual(template, want["nameTemplate"], name)
            self.assertIn(f"{{{{ {want['groupingCriteria'][0]} }}}}", template, name)
            self.assertIsNone(
                re.search(r"\d", template),
                f"{name}: el nombre del incidente no puede llevar números volátiles",
            )

    def test_no_double_incident_for_the_same_alert(self):
        # INFRA-882: Keep no prioriza reglas; una alerta que casa con dos abre
        # dos incidentes. `AtlassianTokenExpiring` solo puede casar con su regla.
        _, rules = load()
        hits = [n for n, r in rules.items()
                if coverage.cel_matches(r["celQuery"], "AtlassianTokenExpiring", "warning")]
        self.assertEqual(hits, ["atlassian-token-expiry"], hits)


if __name__ == "__main__":
    unittest.main()

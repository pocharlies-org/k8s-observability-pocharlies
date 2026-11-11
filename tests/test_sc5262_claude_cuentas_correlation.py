"""Contract for ClaudeCuentasRenovarFallo (SC-5262): el evento que empuja el monitor de cuentas.

libexec/claude-cuentas-monitor.py de x86-host-runtime-pocharlies emite `ClaudeCuentasRenovarFallo` por
`POST /alerts/event` cuando una renovación de login de Claude no se arregla sola (contrato
keep.claude-cuentas-renovar-fallo.v1). Llega como `warning` y sin regla quedaría registrado y callado (Keep solo
notifica INCIDENTES); la regla `claude-cuentas-renovar-fallo` lo hace incidente, y por tanto Request de IT vía
ops-watch. Esta regla se fusiona ANTES que el monitor. El hombre muerto (VMRule pocharlies-claude-cuentas, mismo
nombre) va en su propia PR, con su test sobre el VMRule real. Reutiliza la composición y el evaluador CEL de
scripts/verify-notification-coverage.py (``keep_correlation``) y, con celpy instalado (el CI lo instala), el
motor real de Keep. Hermetic: no kubectl, no network.
"""

import re
import unittest

import yaml

from keep_correlation import RULES, coverage, matches

RULE = "claude-cuentas-renovar-fallo"
# El cuerpo de `_alerta_fallo` del monitor: claves de causa en la raíz Y en labels, severidad duplicada. Si el
# contrato cambia, es una entrada .v2 allí y aquí.
EVENTOS_DEL_MONITOR = [
    {"name": "ClaudeCuentasRenovarFallo", "severity": "warning",
     "labels": {"cuenta": "info", "sitio": "pod", "dir": "/home/dibanez/.claude-company/info",
                "causa": "red", "severity": "warning"}},
    {"name": "ClaudeCuentasRenovarFallo", "severity": "warning",
     "labels": {"cuenta": "monitor-x86", "sitio": "x86", "dir": "", "causa": "pasada", "severity": "warning"}},
]


class ClaudeCuentasRenovarFalloTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = coverage.compose(yaml.safe_load(RULES.read_text()))
        cls.by_name = {r["ruleName"]: r for r in cls.rules}

    def test_el_evento_del_monitor_casa_con_la_regla_y_con_ninguna_otra(self):
        # Keep no prioriza reglas: una segunda coincidencia abriría dos incidentes por un evento.
        for e in EVENTOS_DEL_MONITOR:
            self.assertEqual(matches(self.rules, e["name"], e["severity"]), [RULE], e["labels"]["cuenta"])

    def test_lo_mismo_con_celpy(self):
        try:
            import celpy
        except ImportError:
            self.skipTest("celpy not installed")
        env = celpy.Environment()
        for e in EVENTOS_DEL_MONITOR:
            act = {"name": celpy.celtypes.StringType(e["name"]), "severity": celpy.celtypes.StringType(e["severity"]),
                   "labels": celpy.json_to_cel(e["labels"]), "annotations": celpy.json_to_cel({}),
                   "source": celpy.json_to_cel(["x86"])}
            hit = [r["ruleName"] for r in self.rules if bool(env.program(env.compile(r["celQuery"])).evaluate(act))]
            self.assertEqual(hit, [RULE], e["labels"]["cuenta"])

    def test_agrupa_por_cuenta_con_un_nombre_estable(self):
        # Una causa por home (o monitor-<sitio>, la pasada), como atlassian-token-expiry por `account`. El nombre es
        # la keep-causa de ops-watch: solo la etiqueta de agrupación, sin números volátiles.
        rule = self.by_name[RULE]
        self.assertEqual(rule["groupingCriteria"], ["cuenta"])
        self.assertEqual(rule["incidentNameTemplate"], "Login de Claude sin renovar: {{ cuenta }}")
        self.assertIsNone(re.search(r"\d", rule["incidentNameTemplate"]))
        for e in EVENTOS_DEL_MONITOR:                          # sin `cuenta`, Keep le daría huella «none»
            self.assertIn("cuenta", e["labels"])

    def test_ciclo_y_prefijo_propio(self):
        rule = self.by_name[RULE]
        self.assertEqual((rule["createOn"], rule["resolveOn"], rule["timeUnit"]), ("any", "all_resolved", "minutes"))
        self.assertEqual([r["incidentPrefix"] for r in self.rules].count(rule["incidentPrefix"]), 1)

    def test_no_toca_el_safety_net(self):
        net = self.by_name["critical-safety-net"]["celQuery"]
        self.assertFalse(coverage.cel_matches(net, "ClaudeCuentasRenovarFallo", "warning"))
        self.assertNotIn("ClaudeCuentas", net)

    def test_el_evento_viejo_de_renovar_sigue_sin_regla(self):
        # ClaudeCuentasRenovar era una orden al workflow, no un incidente; ya no lo emite nadie.
        self.assertEqual(matches(self.rules, "ClaudeCuentasRenovar", "warning"), [])


if __name__ == "__main__":
    unittest.main()

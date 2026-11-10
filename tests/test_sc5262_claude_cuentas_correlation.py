"""Contract for ClaudeCuentasRenovarFallo (SC-5262).

Dos emisores, un nombre: el evento Keep que emite libexec/claude-cuentas-monitor.py de
x86-host-runtime-pocharlies cuando una renovación de login no se arregla sola (contrato
keep.claude-cuentas-renovar-fallo.v1) y el hombre muerto de la VMRule
pocharlies-claude-cuentas (manifests/claude-cuentas-rules.yaml). Los dos llegan a Keep como
`warning` y sin regla quedarían registrados y callados (Keep solo notifica INCIDENTES); la
regla `claude-cuentas-renovar-fallo` los hace incidente — y por tanto Request de IT vía
ops-watch. Las comprobaciones compartidas viven en ``keep_correlation.CorrelationContract``;
aquí se cambia la de agrupación (por `cuenta`, no por `alertname`: una causa por home, como
atlassian-token-expiry) y se añade el evento tal como lo construye el monitor. Hermetic: no
kubectl, no network.
"""

import unittest
from pathlib import Path

from keep_correlation import CorrelationContract, matches

# El cuerpo de `_alerta_fallo` del monitor (x86-host-runtime-pocharlies): claves de causa en la raíz
# Y en labels, severidad duplicada. Si el contrato cambia, es una entrada .v2 allí y aquí.
EVENTO_DEL_MONITOR = {"name": "ClaudeCuentasRenovarFallo", "severity": "warning",
                      "labels": {"cuenta": "info", "sitio": "pod", "dir": "/home/dibanez/.claude-company/info",
                                 "causa": "red", "severity": "warning"}}


class ClaudeCuentasCorrelationTests(CorrelationContract, unittest.TestCase):
    RULE = "claude-cuentas-renovar-fallo"
    VMRULE = "pocharlies-claude-cuentas"
    VMRULE_FILE = (Path(__file__).resolve().parents[1] / "manifests" / "claude-cuentas-rules.yaml")
    INCIDENT_NAME = "Login de Claude sin renovar: {{ cuenta }}"

    def test_incident_name_is_a_stable_cause_key(self):
        # Agrupa por `cuenta`: el home que falla (o monitor-<sitio>, la pasada); dos homes rotos son
        # dos causas. Toda alerta de la familia trae `cuenta` (si faltara, Keep le daría huella «none»).
        rule = self.by_name[self.RULE]
        self.assertEqual(rule["groupingCriteria"], ["cuenta"])
        self.assertEqual(rule["incidentNameTemplate"], self.INCIDENT_NAME)
        for labels in self.labels.values():
            self.assertTrue(labels.get("cuenta", "").startswith("monitor-"), labels)
        self.assertIn("cuenta", EVENTO_DEL_MONITOR["labels"])
        self.assertFalse(any(ch.isdigit() for ch in rule["incidentNameTemplate"]))

    def test_severidad(self):
        # warning: un login que no se renueva hoy aún tiene horas de access token; no es una página.
        self.assertEqual(self.alerts["ClaudeCuentasRenovarFallo"], "warning")

    def test_el_evento_del_monitor_casa_con_la_regla_y_con_ninguna_otra(self):
        self.assertEqual(matches(self.rules, EVENTO_DEL_MONITOR["name"], EVENTO_DEL_MONITOR["severity"]), [self.RULE])

    def test_el_evento_viejo_de_renovar_sigue_sin_regla(self):
        # ClaudeCuentasRenovar era una orden al workflow, no un incidente; ya no lo emite nadie.
        self.assertEqual(matches(self.rules, "ClaudeCuentasRenovar", "warning"), [])


if __name__ == "__main__":
    unittest.main()

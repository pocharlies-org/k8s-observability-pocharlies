"""Contract for the claude-cuentas dead-man VMRule (SC-5262).

La VMRule pocharlies-claude-cuentas (manifests/claude-cuentas-rules.yaml) dispara `ClaudeCuentasRenovarFallo`
con `cuenta=monitor-x86|monitor-pod` cuando un sitio del monitor de cuentas pasa dos intervalos sin latido.
Llega a Keep por el catch-all de Alertmanager como `warning`; el incidente lo abre la regla
`claude-cuentas-renovar-fallo` de keep/rules/correlation-rules.yaml, la misma que el evento que empuja el
monitor (tests/test_sc5262_claude_cuentas_correlation.py). Las comprobaciones compartidas viven en
``keep_correlation.CorrelationContract``; aquí cambia la de agrupación (por `cuenta`, no por `alertname`: una
causa por sitio y por home). Hermetic: no kubectl, no network.
"""

import unittest
from pathlib import Path

import yaml

from keep_correlation import CorrelationContract


class ClaudeCuentasHombreMuertoCorrelationTests(CorrelationContract, unittest.TestCase):
    RULE = "claude-cuentas-renovar-fallo"
    VMRULE = "pocharlies-claude-cuentas"
    VMRULE_FILE = (Path(__file__).resolve().parents[1] / "manifests" / "claude-cuentas-rules.yaml")
    INCIDENT_NAME = "Login de Claude sin renovar: {{ cuenta }}"

    def test_incident_name_is_a_stable_cause_key(self):
        # Agrupa por `cuenta`; las dos reglas del VMRule la traen (si faltara, Keep le daría huella «none») y es la
        # misma que el monitor pone a un fallo de su pasada: VMRule y evento del mismo sitio son un incidente.
        rule = self.by_name[self.RULE]
        self.assertEqual(rule["groupingCriteria"], ["cuenta"])
        self.assertEqual(rule["incidentNameTemplate"], self.INCIDENT_NAME)
        docs = [d for d in yaml.safe_load_all(self.VMRULE_FILE.read_text()) if d]
        cuentas = [r["labels"]["cuenta"] for g in docs[0]["spec"]["groups"] for r in g["rules"]]
        self.assertEqual(sorted(cuentas), ["monitor-pod", "monitor-x86"])
        self.assertFalse(any(ch.isdigit() for ch in rule["incidentNameTemplate"]))

    def test_severidad(self):
        # warning: un login que no se renueva hoy aún tiene horas de access token; no es una página.
        self.assertEqual(self.alerts["ClaudeCuentasRenovarFallo"], "warning")


if __name__ == "__main__":
    unittest.main()

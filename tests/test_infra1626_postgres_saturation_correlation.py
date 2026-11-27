"""Contract INFRA-1626 (clase monitoring-degraded, SC-6837): la saturación del
postgres compartido abre su incidente propio y no monta «Monitorización degradada».

SC-6824 (MON-21241, 27-11): postgres-shared a 493/500 tumbó los arranques de
synapse-dispatcher y firecrawl-api → TargetDown + BlackboxProbeDown → incidente
«Monitorización degradada» que no era monitorización rota, mientras
PostgresSharedConnectionsCritical —la causa, firing 04:05→04:25Z— no tenía
regla propia. Dos piezas, ambas medidas aquí con el caso inyectado:

1. La regla `datastore-shared` cubre la familia de saturación entera
   (PostgresSharedConnections* + PostgresSharedBackendsWaiting): la causa abre
   su PGSH con su keep-causa, y ConnectionsCritical (critical) no duplica un
   «Crítico en databases» del safety-net (INVARIANTE 1: la exclusión delega).
2. Alertmanager inhibe TargetDown/BlackboxProbeDown mientras
   PostgresSharedConnectionsCritical firea (patrón INFRA-1529): los daños
   colaterales no llegan a Keep y no montan un MON falso. Sin saturación, un
   TargetDown sigue abriendo monitoring-degraded (no se pierde cobertura).

El test simula la cadena completa —inhibición de Alertmanager sobre el set de
alertas disparadas, luego el matching por regla de correlación sobre las
sobrevivientes— con los datos de SC-6824 inyectados. Reutiliza el evaluador CEL
de `scripts/verify-notification-coverage.py` como test_infra405; la inhibición
reproduce la semántica de inhibit_rules de Alertmanager sin `equal` (cualquier
instancia de la fuente inhibe a todos los targets que casen).

Hermetic: no kubectl, no network.
"""

from pathlib import Path
import importlib.util
import re
import unittest

import yaml

REPO = Path(__file__).resolve().parents[1]
RULES = REPO / "keep" / "rules" / "correlation-rules.yaml"
AMCONFIG = REPO / "manifests" / "alertmanager-config.yaml"

_spec = importlib.util.spec_from_file_location(
    "verify_notification_coverage", REPO / "scripts" / "verify-notification-coverage.py"
)
coverage = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(coverage)


def parse_matcher(matcher):
    """`alertname = "X"` / `alertname =~ "A|B"` -> (label, regex) con full-match."""
    m = re.match(r'^(\w+)\s*(=~|=)\s*"(.*)"$', matcher.strip())
    if not m:
        raise AssertionError(f"matcher no soportado por el test: {matcher!r}")
    label, op, value = m.groups()
    pattern = value if op == "=~" else re.escape(value)
    return label, re.compile(f"^(?:{pattern})$")


def inhibit(firing, inhibit_rules):
    """Alertmanager: un target se inhibe si alguna regla tiene su fuente disparada."""
    survivors = []
    for alert in firing:
        drop = False
        for rule in inhibit_rules:
            sources = [parse_matcher(s) for s in rule["source_matchers"]]
            targets = [parse_matcher(t) for t in rule["target_matchers"]]
            source_firing = any(
                all(rx.match(str(a.get(label, ""))) for label, rx in sources)
                for a in firing
            )
            if source_firing and all(rx.match(str(alert.get(label, ""))) for label, rx in targets):
                drop = True
                break
        if not drop:
            survivors.append(alert)
    return survivors


def incident_rules(alerts, rules):
    """Reglas de correlación que abren incidente con este set de alertas."""
    return sorted(
        {
            r["ruleName"]
            for alert in alerts
            for r in rules
            if coverage.cel_matches(r["celQuery"], alert["alertname"], alert.get("severity", "warning"))
        }
    )


# El set de SC-6824: la causa y sus daños colaterales, disparados a la vez.
SC6824 = [
    {"alertname": "PostgresSharedConnectionsCritical", "severity": "critical", "namespace": "databases"},
    {"alertname": "TargetDown", "severity": "critical", "instance": "synapse-dispatcher:8000"},
    {"alertname": "BlackboxProbeDown", "severity": "warning", "instance": "https://firecrawl/api"},
]


class PostgresSaturationCorrelationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = coverage.compose(yaml.safe_load(RULES.read_text()))
        cls.by_name = {r["ruleName"]: r for r in cls.rules}
        am = yaml.safe_load(AMCONFIG.read_text())
        cls.inhibit_rules = am["spec"]["inhibit_rules"]

    # ---- criterio 1: SC-6824 reproducido -------------------------------
    def test_sc6824_saturacion_abre_incidente_propio_no_monitorizacion(self):
        survivors = inhibit(SC6824, self.inhibit_rules)
        opened = incident_rules(survivors, self.rules)
        self.assertIn("datastore-shared", opened, "la saturación no abre su incidente propio")
        self.assertNotIn("monitoring-degraded", opened, "los daños colaterales siguen montando «Monitorización degradada»")

    def test_la_inhibicion_es_por_la_saturacion_y_no_por_el_titulo(self):
        # Sin la fuente de saturación, los mismos targets NO se inhiben: la
        # exclusión es co-ocurrencia con la causa, no un recorte de la regla.
        collateral_only = [a for a in SC6824 if a["alertname"] != "PostgresSharedConnectionsCritical"]
        self.assertEqual(inhibit(collateral_only, self.inhibit_rules), collateral_only)

    # ---- criterio 2: no se pierde cobertura ----------------------------
    def test_target_down_sin_saturacion_sigue_abriendo_monitoring_degraded(self):
        for alert in (
            {"alertname": "TargetDown", "severity": "critical"},
            {"alertname": "BlackboxProbeDown", "severity": "warning"},
        ):
            survivors = inhibit([alert], self.inhibit_rules)
            self.assertEqual(survivors, [alert], alert["alertname"])
            self.assertIn(
                "monitoring-degraded",
                incident_rules(survivors, self.rules),
                f"{alert['alertname']} sin saturación debe seguir abriendo monitoring-degraded",
            )

    def test_la_inhibicion_solo_toca_los_danos_colaterales(self):
        # Con la saturación fireando, una alerta de otro dominio (p. ej. la app
        # muriendo por su cuenta) sigue llegando: sólo se inhiben los dos
        # nombres de target que montaban el MON falso.
        others = [
            {"alertname": "KubePodCrashLooping", "severity": "warning"},
            {"alertname": "TooManyScrapeErrors", "severity": "warning"},
        ]
        firing = [SC6824[0]] + others
        self.assertEqual(inhibit(firing, self.inhibit_rules), [SC6824[0]] + others)

    # ---- la regla propia ------------------------------------------------
    def test_familia_de_saturacion_casa_exactamente_con_datastore_shared(self):
        # Keep no tiene prioridades entre reglas: una segunda coincidencia
        # abriría dos incidentes por la misma causa (ConnectionsCritical es
        # critical y sin la exclusión montaba además un CRIT del safety-net).
        for name, sev in (
            ("PostgresSharedConnectionsCritical", "critical"),
            ("PostgresSharedConnectionsHigh", "warning"),
            ("PostgresSharedBackendsWaiting", "warning"),
        ):
            self.assertEqual(incident_rules([{"alertname": name, "severity": sev}], self.rules),
                             ["datastore-shared"], name)

    def test_resto_de_postgres_shared_sigue_en_el_safety_net(self):
        # INVARIANTE 1: sólo se excluye del safety-net lo que tiene regla. Las
        # demás PostgresShared* (Backup*, InstancesNotReady) no la tienen y la
        # red las sigue recogiendo.
        for name in ("PostgresSharedBackupFailed", "PostgresSharedInstancesNotReady"):
            self.assertEqual(incident_rules([{"alertname": name, "severity": "critical"}], self.rules),
                             ["critical-safety-net"], name)

    def test_lifecycle_y_prefijo(self):
        rule = self.by_name["datastore-shared"]
        self.assertEqual(rule["createOn"], "any")
        self.assertEqual(rule["resolveOn"], "all_resolved")
        self.assertEqual(rule["incidentPrefix"], "PGSH")
        self.assertEqual(rule["incidentNameTemplate"], "Postgres compartido saturado")
        prefixes = [r["incidentPrefix"] for r in self.rules if r.get("incidentPrefix")]
        self.assertEqual(prefixes.count("PGSH"), 1)


if __name__ == "__main__":
    unittest.main()

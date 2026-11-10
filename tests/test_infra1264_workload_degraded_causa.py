"""Contract de `workload-degraded` (INFRA-1264, patrón INFRA-1187).

La regla agrupaba por `[namespace]`: la `keep-causa` de ops-watch
(`keep-causa:<rule_name>:<sha1(nombre sin número + conjunto de alertnames)>`)
era la misma para dos causas distintas del mismo ns (medido en SC-5033: el
dgx3 NotReady del 08-11 —reloj tras reboot— y la causa del 07-11, no
reconstruible, compartían `workload-degraded:89454cf858`) y el detector de
recurrencia del supervisor («misma keep-causa 2 veces en 7 días») no medía
nada. Ahora agrupa por `[namespace, workload]`.

Pines:

* `groupingCriteria == [namespace, workload]` y el nombre del incidente lleva
  las dos etiquetas de agrupación y ningún número: es la clave de causa.
* Las 5 familias llevan `workload` por SU sitio: las tres del chart por
  `defaultRules.rules.<X>.spec.labels` (victoria-metrics/values.yaml),
  KubernetesDaemonSetUnavailable en su VMRule (manifests/rules.yaml) y
  KubePodCrashLooping reemplazada en pocharlies-pod-workload
  (manifests/pod-workload-rules.yaml). A la alerta a la que le falte CUALQUIER
  criterio Keep le da huella «none» (rulesengine._calc_rule_fingerprint) y la
  causa vuelve a ser genérica: por eso se comprueba aquí, hermeticamente.
* `celQuery` y `sqlQuery` listan las mismas familias.

Hermetic: sin kubectl ni red.
"""

import re
import unittest

import yaml

from keep_correlation import RULES, coverage

FAMILIES = {
    "KubePodCrashLooping",
    "KubeDeploymentRolloutStuck",
    "KubeDaemonSetRolloutStuck",
    "KubernetesDaemonSetUnavailable",
    "KubePersistentVolumeFillingUp",
}

VALUES = RULES.parents[2] / "victoria-metrics" / "values.yaml"
MANIFEST_RULES = RULES.parents[2] / "manifests" / "rules.yaml"
POD_WORKLOAD = RULES.parents[2] / "manifests" / "pod-workload-rules.yaml"

# Familia del chart -> etiqueta de la serie que identifica su workload (plantilla
# de vmalert, no de Helm). El PVC es el identificador de la causa, como el PDB
# de deployment-degraded (INFRA-1187).
CHART_WORKLOAD_LABELS = {
    "KubeDeploymentRolloutStuck": "{{ $labels.deployment }}",
    "KubeDaemonSetRolloutStuck": "{{ $labels.daemonset }}",
    "KubePersistentVolumeFillingUp": "{{ $labels.persistentvolumeclaim }}",
}


def load():
    spec = yaml.safe_load(RULES.read_text())
    return {r["ruleName"]: r for r in coverage.compose(spec)}


class WorkloadDegradedCausaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = load()
        cls.rule = cls.rules["workload-degraded"]
        cls.values = yaml.safe_load(VALUES.read_text())
        # `defaultRules` es top-level en values.yaml (value del chart, no del subchart).
        cls.chart_rules = cls.values["defaultRules"]["rules"]

    def test_grouping_is_namespace_and_workload(self):
        self.assertEqual(self.rule["groupingCriteria"], ["namespace", "workload"])

    def test_incident_name_template_is_stable_cause_key(self):
        # El nombre alimenta el sha1 de la keep-causa: las dos etiquetas de
        # agrupación, ningún número volátil.
        template = self.rule["incidentNameTemplate"]
        self.assertEqual(template, "Workloads degradados en {{ namespace }} · {{ workload }}")
        for label in self.rule["groupingCriteria"]:
            self.assertIn(f"{{{{ {label} }}}}", template)
        self.assertIsNone(re.search(r"\d", template), "el nombre no puede llevar números")

    def test_cel_and_sql_list_the_same_families(self):
        cel_names = set(re.findall(r'"([^"]+)"', self.rule["celQuery"]))
        sql_names = set(self.rule["sqlQuery"]["params"].values())
        self.assertEqual(cel_names, FAMILIES)
        self.assertEqual(sql_names, FAMILIES)

    def test_chart_families_carry_workload_via_default_rules(self):
        for family, template in CHART_WORKLOAD_LABELS.items():
            with self.subTest(family=family):
                spec = self.chart_rules[family]["spec"]
                self.assertEqual(spec["labels"]["workload"], template)

    def test_daemonset_unavailable_carries_workload_in_its_vmrule(self):
        docs = [d for d in yaml.safe_load_all(MANIFEST_RULES.read_text()) if d]
        alerts = {
            r["alert"]: r
            for d in docs
            for g in d.get("spec", {}).get("groups", [])
            for r in g.get("rules", [])
            if "alert" in r
        }
        self.assertEqual(
            alerts["KubernetesDaemonSetUnavailable"]["labels"]["workload"],
            "{{ $labels.daemonset }}",
        )

    def test_crashlooping_is_replaced_with_workload(self):
        # La copia del chart agrega por pod y no sabe quién es el owner: se
        # desactiva y su reemplazo (con el join de pocharlies-pod-workload) es
        # el que lleva `workload`. Si alguien reactiva la del chart sin quitar
        # el reemplazo, las dos familias duplican incidentes; si apaga las dos,
        # el crashloop vuelve a callar (la lección de las huérfanas del 04-08).
        self.assertIs(self.chart_rules["KubePodCrashLooping"]["create"], False)
        docs = [d for d in yaml.safe_load_all(POD_WORKLOAD.read_text()) if d]
        alerts = {
            r["alert"]
            for d in docs
            for g in d.get("spec", {}).get("groups", [])
            for r in g.get("rules", [])
            if "alert" in r
        }
        self.assertIn("KubePodCrashLooping", alerts)


if __name__ == "__main__":
    unittest.main()

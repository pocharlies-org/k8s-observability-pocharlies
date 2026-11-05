"""Contract de `deployment-degraded` (INFRA-1187).

La regla agrupa por `[namespace, workload]` para que la `keep-causa` de
ops-watch (`keep-causa:<rule_name>:<sha1(nombre sin número + conjunto de
alertnames)>`) identifique el workload concreto: con `[namespace]`, tres fallos
ajenos del ns llm (rollout de stt-turbo, vaivén de ollaya-cpu, sidecar de
nginx) cayeron en la misma causa `aaab90c902` (SC-2641/SC-4666).

Pines:

* `groupingCriteria == [namespace, workload]` y el nombre del incidente lleva
  las dos etiquetas de agrupación y ningún número: es la clave de causa.
* No se agrupa por `[namespace, deployment, statefulset]`: Keep da huella
  «none» a la alerta a la que le falte CUALQUIER criterio
  (rulesengine._calc_rule_fingerprint) y ninguna alerta trae las dos etiquetas
  — acabarían todas en el mismo cubo «none». Por eso `workload` es una etiqueta
  que ponen las VMRules en TODAS las alertas de la regla (manifests/rules.yaml,
  victoria-metrics/values.yaml y manifests/pod-workload-rules.yaml).
* `celQuery` y `sqlQuery` listan las mismas familias (los dos motores de Keep
  ven el mismo conjunto).

Hermetic: sin kubectl ni red.
"""

import importlib.util
from pathlib import Path
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

# Las 7 familias de la regla. Añadir una aquí exige darle `workload` en su
# VMRule (o en la copia del chart vía defaultRules.rules.<X>.spec.labels), o
# Keep la mete en el cubo «none» y la causa vuelve a ser genérica.
FAMILIES = {
    "KubernetesDeploymentUnavailable",
    "KubeDeploymentReplicasMismatch",
    "KubePodNotReady",
    "KubeContainerWaiting",
    "KubeStatefulSetReplicasMismatch",
    "KubernetesStatefulSetUnavailable",
    "KubePdbNotEnoughHealthyPods",
}


def load():
    spec = yaml.safe_load(RULES.read_text())
    return {r["ruleName"]: r for r in coverage.compose(spec)}


class DeploymentDegradedCausaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = load()
        cls.rule = cls.rules["deployment-degraded"]

    def test_grouping_is_namespace_and_workload(self):
        self.assertEqual(self.rule["groupingCriteria"], ["namespace", "workload"])

    def test_incident_name_template_is_stable_cause_key(self):
        # El nombre alimenta el sha1 de la keep-causa: las dos etiquetas de
        # agrupación, ningún número volátil.
        template = self.rule["incidentNameTemplate"]
        self.assertEqual(template, "Deployment degradado en {{ namespace }} · {{ workload }}")
        for label in self.rule["groupingCriteria"]:
            self.assertIn(f"{{{{ {label} }}}}", template)
        self.assertIsNone(re.search(r"\d", template), "el nombre no puede llevar números")

    def test_cel_and_sql_list_the_same_families(self):
        cel_names = set(re.findall(r'"([^"]+)"', self.rule["celQuery"]))
        sql_names = set(self.rule["sqlQuery"]["params"].values())
        self.assertEqual(cel_names, FAMILIES)
        self.assertEqual(sql_names, FAMILIES)

    def test_los_sintomas_de_un_workload_comparten_clave(self):
        # Los 4 síntomas del deployment se colapsan porque los 4 llevan el
        # MISMO workload: los dos de deployment por plantilla en su VMRule y
        # los dos de pod por el join de pocharlies-pod-workload. Aquí se fija
        # que las familias de pod siguen dentro de la regla (si alguien las
        # saca, el propósito original de la regla se rompe sin ruido).
        cel_names = set(re.findall(r'"([^"]+)"', self.rule["celQuery"]))
        self.assertTrue(
            {"KubePodNotReady", "KubeContainerWaiting"} <= cel_names,
            "los síntomas de pod deben seguir en deployment-degraded (colapsan con su workload)",
        )


if __name__ == "__main__":
    unittest.main()

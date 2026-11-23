"""DGX-1789: al resolverse un incidente de Keep, su sesión de arreglo de Paseo se archiva.

Pins:

1. `alertas-cierre` se dispara con `type: incident` / `events: [updated]` (la resolución de Keep 0.52.1
   sale como `updated`, no como evento propio).
2. El step SIEMPRE devuelve una fila (LEFT JOIN sobre `(VALUES (1))`): con 0 filas `results.0.0`
   renderiza vacío y el `if` de la action corta el POST. El `if` no puede ir en el step.
3. El body lleva `tipo: cierre` y el fingerprint con el que se lanzó la sesión (la clave del
   lanzador es `keep-<fingerprint>`); la conexión `synapse_keep` guarda el token, no el `with:`.
4. La query no lleva el literal `keep.` (INFRA-406: el iohandler de Keep 0.52.1 lo toma por
   llamada de plantilla y revienta).
"""

import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def workflow(wid):
    values = yaml.safe_load((ROOT / "keep" / "values.yaml").read_text())
    return next(w for w in values["backend"]["provision"]["workflows"] if w["id"] == wid)


class CierreTest(unittest.TestCase):
    def setUp(self):
        self.wf = workflow("alertas-cierre")
        self.datos, self.avisar = self.wf["actions"]

    def test_trigger_incidente_actualizado(self):
        self.assertEqual(self.wf["triggers"], [{"type": "incident", "events": ["updated"]}])

    def test_step_siempre_devuelve_fila(self):
        query = self.datos["provider"]["with"]["query"]
        self.assertIn("FROM (VALUES (1)) AS siempre(x)", query)
        self.assertIn("LEFT JOIN", query)
        self.assertNotIn("if", self.datos)

    def test_if_sobre_el_fingerprint(self):
        self.assertEqual(self.avisar["if"], "'{{ steps.datos-cierre.results.0.0 }}' != ''")

    def test_body_tipo_cierre(self):
        self.assertEqual(self.avisar["provider"]["config"], "{{ providers.synapse_keep }}")
        self.assertEqual(
            self.avisar["provider"]["with"],
            {"body": {"incidente": "{{ incident.id }}", "tipo": "cierre",
                      "fingerprint": "{{ steps.datos-cierre.results.0.0 }}"}},
        )

    def test_query_sin_literal_keep_punto(self):
        query = self.datos["provider"]["with"]["query"]
        self.assertIsNone(re.search(r"keep\.", query))


if __name__ == "__main__":
    unittest.main()
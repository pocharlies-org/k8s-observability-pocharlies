"""DGX-1789: al resolverse un incidente de Keep, su sesión de arreglo de Paseo se archiva.

Pins:

1. `alertas-cierre` se dispara con `type: incident` / `events: [updated]` (la resolución de Keep 0.52.1
   sale como `updated`, no como evento propio).
2. El step SIEMPRE devuelve una fila (LEFT JOIN sobre `(VALUES (1))`): con 0 filas `results.0.0`
   renderiza vacío y el `if` de la action corta el POST. El `if` no puede ir en el step.
3. El body lleva `tipo: cierre` y la lista de fingerprints con los que se lanzaron las sesiones (la clave
   del lanzador es `keep-<fingerprint>`); la conexión `synapse_keep` guarda el token, no el `with:`.
4. La query no lleva el literal `keep.` (INFRA-406: el iohandler de Keep 0.52.1 lo toma por
   llamada de plantilla y revienta).
5. Un incidente fusionado cambia de id, pierde sus alertas y no emite evento (`merge_incidents_to_id`), así
   que el cierre se calcula al resolverse el superviviente, recorriendo su árbol `merged_into_incident_id`
   en la BBDD de Keep; la clave es el mismo token del claim, `substr(md5(id::text),1,16)`.
"""

import re
import unittest

import yaml

try:  # pytest desde la raíz del repo, o unittest desde tests/
    from tests.keep_values import VALUES, find_workflows
except ImportError:
    from keep_values import VALUES, find_workflows


def workflow(wid):
    values = yaml.safe_load(VALUES.read_text())
    return next(w for w in find_workflows(values) if w["id"] == wid)


class CierreTest(unittest.TestCase):
    def setUp(self):
        self.wf = workflow("alertas-cierre")
        (self.datos,) = self.wf["steps"]
        (self.avisar,) = self.wf["actions"]
        self.query = self.datos["provider"]["with"]["query"]

    def test_trigger_incidente_actualizado(self):
        self.assertEqual(self.wf["triggers"], [{"type": "incident", "events": ["updated"]}])

    def test_step_siempre_devuelve_fila(self):
        self.assertIn("FROM (VALUES (1)) AS siempre(x)", self.query)
        self.assertIn("LEFT JOIN", self.query)
        self.assertNotIn("if", self.datos)

    def test_if_sobre_el_fingerprint(self):
        self.assertEqual(self.avisar["if"], "'{{ steps.datos-cierre.results.0.0 }}' != ''")

    def test_body_tipo_cierre(self):
        self.assertEqual(self.avisar["provider"]["config"], "{{ providers.synapse_keep }}")
        self.assertEqual(
            self.avisar["provider"]["with"],
            {"body": {"incidente": "{{ incident.id }}", "tipo": "cierre",
                      "fingerprints": "{{ steps.datos-cierre.results.0.0 }}"}},
        )

    def test_query_sin_literal_keep_punto(self):
        self.assertIsNone(re.search(r"keep\.", self.query))

    def test_fusion_recorre_el_arbol_en_la_bbdd_de_keep(self):
        # El absorbido pierde sus alertas y no emite evento: hay que ir al árbol
        # `merged_into_incident_id` al resolver el superviviente, y la clave es el
        # token del claim (misma fórmula: si cambia una, cambian las dos).
        self.assertEqual(self.datos["provider"]["config"], "{{ providers.keep_db }}")
        self.assertIn("WITH RECURSIVE arbol AS (", self.query)
        self.assertIn("SELECT i.id FROM incident i JOIN arbol a ON i.merged_into_incident_id = a.id", self.query)
        self.assertIn("substr(md5(id::text), 1, 16)", self.query)
        self.assertIn("string_agg(DISTINCT", self.query)

    def test_estado_normalizado_porque_el_enum_renderiza_su_repr(self):
        # Medido en el pod (23-11): `{{ incident.status }}` llega como
        # `IncidentStatus.RESOLVED`, no `resolved`; sin normalizar, el ON nunca
        # casa y el cierre no sale.
        self.assertIn("lower(replace('{{ incident.status }}', 'IncidentStatus.', '')) = 'resolved'", self.query)


if __name__ == "__main__":
    unittest.main()
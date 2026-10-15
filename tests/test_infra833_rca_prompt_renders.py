"""INFRA-833: la evidencia que entra al prompt de `llm-rca` no puede dejar un
`{{`/`}}` que chevron interprete.

Keep renderiza el prompt con `IOHandler.render_recursively` (medido en el pod
keep-backend, keep 0.52.1, 2026-10-15): re-renderiza con chevron MIENTRAS el
resultado siga llevando `{{`. La evidencia sustituida se vuelve plantilla en la
segunda pasada. Medido: incidente Aurora 408f3d00 (fingerprint
322d42d10e0325ad), paso 4 con `{{` en la posición 567 y `}}` en la 604 del
tool_output; el `left(..., 600)` de `rca-datos` cortaba entre las dos y
`chevron.tokenizer.ChevronError: unclosed tag` tumbó 32 pasadas seguidas del
workflow aurora-report-back (2026-10-10, 12:11Z-14:51Z).

Este test corre el SQL REAL de `rca-datos` (extraído de keep/values.yaml)
contra un Postgres desechable con ese fixture y renderiza el prompt REAL de
`llm-rca` con el mismo bucle de Keep. Sin el arreglo, la segunda pasada lanza
ChevronError (el test de control
`test_bucle_de_render_falla_con_llaves_sin_cerrar` pinya ese comportamiento).

DSN: `AURORA_TEST_PG_DSN` (CI: un service container `postgres:16`). Sin él los
tests se saltan en local y FALLAN con `CI=true`.
"""

import html
import os
import unittest

try:
    from keep_values import step
except ImportError:  # invocado como `python -m unittest tests.test_...` desde la raíz
    from tests.keep_values import step

try:
    import psycopg
except ImportError:  # pragma: no cover - exercised only without the driver
    psycopg = None

try:
    import chevron
    from chevron.tokenizer import ChevronError
except ImportError:  # pragma: no cover - exercised only without chevron
    chevron = None
    ChevronError = Exception

DSN = os.environ.get("AURORA_TEST_PG_DSN")
IN_CI = os.environ.get("CI", "").lower() == "true"

DDL = """
CREATE SCHEMA IF NOT EXISTS keep_bridge;
CREATE TABLE organizations (id serial PRIMARY KEY, created_at timestamptz DEFAULT now());
CREATE TABLE incidents (
  id serial PRIMARY KEY,
  alert_metadata jsonb,
  alert_title text,
  severity text,
  aurora_summary text,
  aurora_status text,
  analyzed_at timestamptz);
CREATE TABLE execution_steps (
  incident_id int,
  step_index int,
  tool_name text,
  tool_input jsonb,
  tool_output text,
  status text);
CREATE TABLE keep_bridge.reported (
  fingerprint text PRIMARY KEY,
  reported_at timestamptz DEFAULT now());
CREATE TABLE keep_bridge.aurora_dispatches (
  fingerprint text PRIMARY KEY,
  keep_incident_id text NOT NULL,
  dispatched_at timestamptz NOT NULL DEFAULT now(),
  aurora_incident_id uuid);
"""

FINGERPRINT = "322d42d10e0325ad"


def rca_datos_sql() -> str:
    return step("aurora-report-back", "rca-datos")["provider"]["with"]["query"]


def llm_rca_prompt() -> str:
    return step("aurora-report-back", "llm-rca")["provider"]["with"]["prompt"]


def link_datos_sql() -> str:
    return step("aurora-link", "link-datos")["provider"]["with"]["query"]


def poisoned_tool_output() -> str:
    """Como el paso 4 del incidente 408f3d00: `{{` en la posición 567 y `}}` en
    la 604 (1-based). El left(..., 600) corta entre las dos."""
    return "x" * 566 + "{{" + "y" * 35 + "}}" + "z" * 200


def render_like_keep(template: str, context: dict, max_iterations: int = 10) -> str:
    """Espejo de IOHandler.render_recursively (keep 0.52.1): chevron en bucle
    mientras el resultado siga llevando `{{`."""
    current = template
    for _ in range(max_iterations):
        rendered = html.unescape(chevron.render(current, context))
        if rendered == current or "{{" not in rendered or "providers." in rendered:
            return rendered
        current = rendered
    return current


@unittest.skipUnless(DSN or IN_CI, "AURORA_TEST_PG_DSN not set (mandatory when CI=true)")
class RcaPromptRenderTests(unittest.TestCase):
    def setUp(self):
        if not DSN or psycopg is None or chevron is None:
            self.fail("CI=true requires AURORA_TEST_PG_DSN, psycopg and chevron")
        self.conn = psycopg.connect(DSN, autocommit=True)
        self.addCleanup(self.conn.close)
        for t in ("keep_bridge.reported", "keep_bridge.aurora_dispatches",
                  "execution_steps", "incidents", "organizations"):
            self.conn.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
        self.conn.execute("DROP SCHEMA IF EXISTS keep_bridge CASCADE")
        self.conn.execute(DDL)
        self.conn.execute("INSERT INTO organizations DEFAULT VALUES")

    def run_script(self, sql: str):
        """Script multistatement en UNA sesión (como el provider de Keep);
        devuelve las filas del ÚLTIMO juego de resultados."""
        cur = self.conn.execute(sql)
        rows = None
        while True:
            if cur.description:
                rows = cur.fetchall()
            if not cur.nextset():
                break
        return rows

    def seed_poisoned_incident(self):
        self.conn.execute(
            "INSERT INTO incidents (alert_metadata, alert_title, severity,"
            " aurora_summary, aurora_status, analyzed_at) VALUES "
            "(%s::jsonb, %s, 'error', %s, 'complete', now())",
            ('{"fingerprint": "%s"}' % FINGERPRINT,
             "CI-11187 - CI en rojo: llm-status-ios {{cortado",
             "resumen con {{ sin cerrar aquí y }} mucho después " + "w" * 900))
        incident_id = self.conn.execute(
            "SELECT id FROM incidents WHERE alert_metadata->>'fingerprint' = %s",
            (FINGERPRINT,)).fetchone()[0]
        self.conn.execute(
            "INSERT INTO execution_steps (incident_id, step_index, tool_name,"
            " tool_input, tool_output, status) VALUES "
            "(%s, 4, 'terminal_exec', '{\"command\": \"kubectl logs ci-runner\"}',"
            " %s, 'success')",
            (incident_id, poisoned_tool_output()))

    def test_rca_datos_neutraliza_las_llaves(self):
        self.seed_poisoned_incident()
        row = self.run_script(rca_datos_sql())[0]
        fp, titulo, severidad, respaldo, evidencia = row[0], row[1], row[2], row[3], row[4]
        self.assertEqual(fp, FINGERPRINT)
        for name, value in (("título", titulo), ("respaldo", respaldo),
                            ("evidencia", evidencia)):
            self.assertNotIn("{{", value, f"{name} lleva {{{{ sin neutralizar")
            self.assertNotIn("}}", value, f"{name} lleva }}}} sin neutralizar")
        # La neutralización es inofensiva: el texto sobrevive con las llaves
        # separadas (leíbles para el modelo, inertes para chevron).
        self.assertIn("{ {", evidencia)

    def test_prompt_llm_rca_renderiza(self):
        self.seed_poisoned_incident()
        row = self.run_script(rca_datos_sql())[0]
        context = {"steps": {"rca-datos": {"results": [list(row)]}}}
        rendered = render_like_keep(llm_rca_prompt(), context)
        self.assertNotIn("{{", rendered)
        self.assertIn("kubectl logs ci-runner", rendered)
        self.assertIn("{ {", rendered)  # la evidencia recortada llegó al prompt

    def test_bucle_de_render_falla_con_llaves_sin_cerrar(self):
        # Control: el bucle de Keep falla EXACTAMENTE como se midió si la
        # evidencia llega con `{{` sin cerrar. Sin este fallo reproduciéndose,
        # el test de arriba no valdría nada.
        context = {"steps": {"rca-datos": {"results": [["fp", "título", "error",
                                                        "respaldo", "x" * 566 + "{{"]]}}}
        with self.assertRaises(ChevronError):
            render_like_keep(llm_rca_prompt(), context)

    def test_link_datos_titulo_neutralizado(self):
        self.conn.execute(
            "INSERT INTO incidents (alert_metadata, alert_title, aurora_status,"
            " analyzed_at) VALUES (%s::jsonb, 'título con {{ sin cerrar }}',"
            " 'complete', now())", ('{"fingerprint": "%s"}' % FINGERPRINT,))
        self.conn.execute(
            "INSERT INTO keep_bridge.aurora_dispatches (fingerprint, keep_incident_id)"
            " VALUES (%s, '11111111-1111-1111-1111-111111111111')", (FINGERPRINT,))
        row = self.run_script(link_datos_sql())[0]
        self.assertNotIn("{{", row[3])
        self.assertNotIn("}}", row[3])


if __name__ == "__main__":
    unittest.main()

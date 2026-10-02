"""Behaviour of the Aurora claim (INFRA-406, contract v1.3) on a real Postgres.

``test_keep_aurora_dispatch_contract.py`` pins the YAML text; this file runs
the SQL of ``claim-dispatch`` (extracted from ``keep/values.yaml``, templates
substituted) and the expand/contract migration (extracted from
``docs/keep-aurora-contract.md``) against a throwaway database.

DSN: ``AURORA_TEST_PG_DSN`` (CI: a ``postgres:16`` service container). Without
it the tests are skipped locally and FAIL when ``CI=true``.
"""

import os
import re
import unittest
import uuid
from pathlib import Path

import yaml

try:
    import psycopg
except ImportError:  # pragma: no cover - exercised only without the driver
    psycopg = None

ROOT = Path(__file__).resolve().parents[1]
DSN = os.environ.get("AURORA_TEST_PG_DSN")
IN_CI = os.environ.get("CI", "").lower() == "true"

# A v1.2 database as it lives today: PK on the alert fingerprint.
OLD_DDL = """
CREATE SCHEMA IF NOT EXISTS keep_bridge;
CREATE TABLE keep_bridge.aurora_dispatches (
  fingerprint text PRIMARY KEY,
  keep_incident_id uuid NOT NULL,
  dispatched_at timestamptz NOT NULL DEFAULT now(),
  aurora_incident_id uuid,
  linked_at timestamptz);
CREATE TABLE public.incidents (
  id serial PRIMARY KEY, alert_metadata jsonb, source_type text, aurora_status text);
"""


def _find_workflows(node):
    if isinstance(node, dict):
        if isinstance(node.get("workflows"), list):
            return node["workflows"]
        for v in node.values():
            found = _find_workflows(v)
            if found:
                return found
    elif isinstance(node, list):
        for v in node:
            found = _find_workflows(v)
            if found:
                return found
    return None


def claim_sql() -> str:
    values = yaml.safe_load((ROOT / "keep/values.yaml").read_text())
    wf = next(w for w in _find_workflows(values) if w.get("id") == "aurora-investigate")
    step = next(s for s in wf["steps"] if s["name"] == "claim-dispatch")
    return step["provider"]["with"]["query"]


def render(sql: str, incident_id: str, alert_fp, severity="critical") -> str:
    sql = re.sub(r"\{\{#fn\.default\}\}|\{\{/fn\.default\}\}", "", sql)
    ctx = {
        "incident.id": incident_id,
        "incident.alerts.0.fingerprint": alert_fp or "",
        "incident.severity": severity,
    }
    sql = re.sub(r"\{\{ (incident\.[\w.]+) \}\}", lambda m: ctx[m.group(1)], sql)
    assert "{{" not in sql, "unrendered template left in claim SQL"
    return sql


def _contract() -> str:
    return (ROOT / "docs/keep-aurora-contract.md").read_text()


def migration_block(name: str) -> list:
    m = re.search(r"```sql\n-- migracion:" + re.escape(name) + r"\n(.*?)```", _contract(), re.S)
    assert m, f"migration block {name} missing in the contract"
    body = "\n".join(l for l in m.group(1).splitlines() if not l.lstrip().startswith("--"))
    return [s.strip() for s in body.split(";") if s.strip()]


def rca_coverage_ddl() -> str:
    m = re.search(
        r"(CREATE OR REPLACE FUNCTION keep_bridge\.aurora_rca_coverage\(\).*?\$\$;)", _contract(), re.S
    )
    assert m, "aurora_rca_coverage() DDL missing in the contract"
    return m.group(1)


@unittest.skipUnless(DSN or IN_CI, "AURORA_TEST_PG_DSN not set (mandatory when CI=true)")
class ClaimBehaviourTests(unittest.TestCase):
    def setUp(self):
        if not DSN or psycopg is None:
            self.fail("CI=true requires AURORA_TEST_PG_DSN and the psycopg driver")
        self.conn = psycopg.connect(DSN, autocommit=True)
        self.addCleanup(self.conn.close)
        self.conn.execute("DROP SCHEMA IF EXISTS keep_bridge CASCADE")
        self.conn.execute("DROP TABLE IF EXISTS public.incidents")

    def run_script(self, sql: str):
        """Run a multi-statement script in ONE session (like Keep's provider)
        and return the rows of its LAST result set."""
        cur = self.conn.execute(sql)
        rows = None
        while True:
            if cur.description:
                rows = cur.fetchall()
            if not cur.nextset():
                break
        return rows

    def claim(self, incident_id, alert_fp, severity="critical"):
        rows = self.run_script(render(claim_sql(), incident_id, alert_fp, severity))
        return rows[0][0], rows[0][1]

    def dispatches(self):
        return self.conn.execute(
            "SELECT keep_incident_id::text, fingerprint, alert_fingerprint, previous_keep_incident_id::text "
            "FROM keep_bridge.aurora_dispatches ORDER BY dispatched_at, keep_incident_id"
        ).fetchall()

    def pk_def(self):
        return self.conn.execute(
            "SELECT pg_get_indexdef(indexrelid) FROM pg_index "
            "WHERE indrelid='keep_bridge.aurora_dispatches'::regclass AND indisprimary"
        ).fetchone()[0]

    def test_rearm_cooldown_and_idempotence(self):
        a, b, c = (str(uuid.uuid4()) for _ in range(3))
        fp = "deadbeefcafe0001"

        token, prev = self.claim(a, fp)  # 1. first incident opens
        expected = self.conn.execute("SELECT substr(md5(%s::text),1,16)", (a,)).fetchone()[0]
        self.assertEqual(token, expected)
        self.assertEqual(prev, "")

        self.assertEqual(self.claim(b, fp), ("", ""))  # 2. same alert, new incident, <6h: suppressed
        self.assertEqual(len(self.dispatches()), 1)

        self.conn.execute("UPDATE keep_bridge.aurora_dispatches SET dispatched_at = now() - interval '7 hours'")
        token_c, prev_c = self.claim(c, fp)  # 3. >6h: new row linked to the previous one
        self.assertNotEqual(token_c, "")
        self.assertEqual(prev_c, f"https://keep.e-dani.com/incidents/{a}")  # URL unchanged
        self.assertEqual(self.dispatches()[-1][3], a)

        self.assertEqual(self.claim(c, fp), ("", ""))  # 4. same keep_incident_id again
        self.assertEqual(len(self.dispatches()), 2)

    def test_lane_is_critical_and_warning_only(self):
        self.assertNotEqual(self.claim(str(uuid.uuid4()), "aa01", "warning")[0], "")
        self.assertEqual(self.claim(str(uuid.uuid4()), "aa02", "info")[0], "")
        self.assertEqual(len(self.dispatches()), 1)

    def test_incident_without_alert_fingerprint_is_dispatched(self):
        self.assertNotEqual(self.claim(str(uuid.uuid4()), None)[0], "")
        self.assertIsNone(self.dispatches()[0][2])
        # no fingerprint => no cooldown: a second one is dispatched too
        self.assertNotEqual(self.claim(str(uuid.uuid4()), None)[0], "")

    def test_migration_expand_then_contract_keeps_coverage(self):
        self.run_script(OLD_DDL)
        old_fp = "0123456789abcdef"
        for fp in (old_fp, "fedcba9876543210"):
            self.conn.execute(
                "INSERT INTO keep_bridge.aurora_dispatches (fingerprint, keep_incident_id, dispatched_at) "
                "SELECT %s, gen_random_uuid(), now() - interval '10 hours'",
                (fp,),
            )
        self.conn.execute(
            "INSERT INTO public.incidents (alert_metadata, source_type, aurora_status) "
            "VALUES (jsonb_build_object('fingerprint', %s::text), 'grafana', 'complete')",
            (old_fp,),
        )
        self.conn.execute(rca_coverage_ddl())
        before = self.conn.execute("SELECT * FROM keep_bridge.aurora_rca_coverage()").fetchone()
        self.assertEqual(before, (2, 1))

        self.assertEqual(self.conn.execute(migration_block("precheck")[0]).fetchall(), [])
        for stmt in migration_block("expand"):
            self.conn.execute(stmt)
        # the NEW claim already works on the expanded (not yet contracted) table
        self.assertNotEqual(self.claim(str(uuid.uuid4()), "feed0000feed0000")[0], "")
        for stmt in migration_block("expand"):  # idempotent: re-run at step 2
            self.conn.execute(stmt)
        self.assertEqual(
            self.conn.execute(
                "SELECT count(*) FROM keep_bridge.aurora_dispatches WHERE alert_fingerprint IS NULL"
            ).fetchone()[0],
            0,
        )

        for stmt in migration_block("contract"):
            self.conn.execute(stmt)
        self.assertIn("keep_incident_id", self.pk_def())
        self.assertEqual(self.conn.execute("SELECT * FROM keep_bridge.aurora_rca_coverage()").fetchone(), before)
        self.assertNotEqual(self.claim(str(uuid.uuid4()), "feed1111feed1111")[0], "")

        for stmt in migration_block("rollback-contract"):  # step 4 rollback
            self.conn.execute(stmt)
        self.assertIn("(fingerprint)", self.pk_def())
        self.conn.execute(
            "INSERT INTO keep_bridge.aurora_dispatches (fingerprint, keep_incident_id) "
            "VALUES ('aaaabbbbccccdddd', gen_random_uuid()) ON CONFLICT (fingerprint) DO NOTHING"
        )


if __name__ == "__main__":
    unittest.main()

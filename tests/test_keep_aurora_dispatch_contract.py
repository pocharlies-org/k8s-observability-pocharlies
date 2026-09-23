"""Contract for Keep's Aurora integration (INFRA-217).

Two workflows are pinned here, both as Helm values rather than Python:

* ``aurora-investigate`` — the critical-only dispatch lane: the SQL claim must
  reject non-critical incidents before writing the fingerprint, the webhook
  action must also require critical severity, and the payload must carry
  ``generatorURL`` (Aurora stores it as ``alert_metadata.alertUrl`` and renders
  it as "View Alert"; the ``keep_url`` annotation is discarded by tasks.py).

* ``aurora-link`` — the Keep->Aurora link via Keep's native "External incident"
  enrichment (INFRA-229).  Hard design constraint: the step is READ-ONLY
  (writing inside a step is what took down the alerting system in July — steps
  never commit); both writes are actions, and ``mark-linked`` must run AFTER
  ``link-incident``.  The mock action's ``fingerprint`` must receive the Keep
  incident uuid with dashes (``results.0.0``), never the 16-hex alert
  fingerprint: Keep indexes incident enrichments by ``cast(incident.id)``
  (measured in INFRA-231 / nota-sre-paso0.md).

Keep renders its ``if`` expressions at runtime, so these tests pin the YAML
text itself.
"""

from pathlib import Path
import re
import unittest


VALUES = Path(__file__).resolve().parents[1] / "keep" / "values.yaml"


def workflow_block(text: str, wf_id: str) -> str:
    """Return the YAML body of one workflow (everything after its ``- id:``
    line up to the next workflow at the same indentation)."""
    match = re.search(
        r"^      - id: " + re.escape(wf_id) + r"\n(?P<block>.*?)(?=^      - id: |\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if not match:
        raise AssertionError(f"{wf_id} workflow not found")
    return match.group("block")


def steps_section(block: str) -> str:
    """Return the ``steps:`` part of a workflow block (everything before its
    ``actions:`` key)."""
    match = re.search(
        r"^        steps:\n(?P<steps>.*?)(?=^        actions:|\Z)",
        block,
        re.MULTILINE | re.DOTALL,
    )
    if not match:
        raise AssertionError("steps section not found")
    return match.group("steps")


class KeepAuroraDispatchContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        text = VALUES.read_text()
        cls.block = workflow_block(text, "aurora-investigate")

    def test_warning_neither_claims_nor_dispatches(self):
        self.assertRegex(
            self.block,
            r"AS severity\s+-- Defensa antes del claim:[\s\S]*?"
            r"WHERE '\{\{ incident\.severity \}\}' = 'critical'",
        )
        self.assertIn(
            "if: \"'{{ incident.severity }}' == 'critical' and "
            "'{{ steps.claim-dispatch.results.0.0 }}' != ''\"",
            self.block,
        )

    def test_critical_claims_and_dispatches_when_fingerprint_is_new(self):
        self.assertIn(
            "NULLIF('{{ incident.severity }}', '') AS severity",
            self.block,
        )
        self.assertIn("ON CONFLICT (fingerprint) DO NOTHING", self.block)
        self.assertIn("- name: dispatch-rca", self.block)

    def test_report_back_workflow_is_not_part_of_dispatch_contract(self):
        self.assertNotIn("aurora-report-back", self.block)

    def test_dispatch_carries_generator_url_for_the_backlink(self):
        # Aurora keeps generatorURL as alert_metadata.alertUrl ("View Alert");
        # only new dispatches get it — old rows are never backfilled.
        self.assertIn(
            'generatorURL: "https://keep.e-dani.com/incidents/{{ incident.id }}"',
            self.block,
        )


class KeepAuroraLinkContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.block = workflow_block(VALUES.read_text(), "aurora-link")

    def test_link_step_is_read_only(self):
        # Hard design constraint: writes are actions (they commit via
        # _notify); steps never commit.
        steps = steps_section(self.block)
        self.assertNotRegex(steps, r"\b(INSERT|UPDATE|DELETE)\b")
        self.assertIn("FROM (VALUES (1)) AS siempre(x)", steps)
        self.assertIn("LEFT JOIN cand c ON true", steps)
        # RLS prologue identical to rca-datos: without it the `aurora` role
        # sees zero rows from `incidents` with no error.
        self.assertIn("set_config('myapp.current_org_id'", steps)

    def test_link_incident_keys_on_the_keep_incident_uuid_not_the_hex(self):
        # nota-sre-paso0.md: alertenrichment.alert_fingerprint for incidents
        # is the Keep incident uuid WITH DASHES (results.0.0).  Passing the
        # 16-hex alert fingerprint would write a row the incident GET never
        # finds (invisible badge) and would collide with the alert space.
        self.assertIn(
            'fingerprint: "{{ steps.link-datos.results.0.0 }}"',
            self.block,
        )
        self.assertNotIn(
            'fingerprint: "{{ steps.link-datos.results.0.2 }}"',
            self.block,
        )

    def test_enrich_uses_the_three_native_keys_without_a_provider_icon(self):
        for key in ("incident_id", "incident_url", "incident_title"):
            self.assertIn(f"- key: {key}", self.block)
        self.assertIn(
            'value: "https://aurora.e-dani.com/incidents/'
            '{{ steps.link-datos.results.0.1 }}"',
            self.block,
        )
        # The UI would ask for a provider icon that does not exist, so the
        # enrich list must not carry that key (prose comments may mention it).
        self.assertNotIn("- key: incident_provider", self.block)

    def test_mark_linked_runs_after_link_incident(self):
        self.assertLess(
            self.block.index("- name: link-incident"),
            self.block.index("- name: mark-linked"),
        )
        # mark-linked is an action (commits), guarded by the same non-empty row.
        actions = self.block[self.block.index("        actions:"):]
        self.assertIn(
            "if: \"'{{ steps.link-datos.results.0.0 }}' != ''\"",
            actions,
        )
        self.assertIn("AND aurora_incident_id IS NULL", actions)

    def test_report_back_workflow_is_untouched_by_the_link(self):
        # aurora-report-back (Telegram) must not gain any of the link machinery:
        # the link lives in its own interval workflow, not in the one that took
        # down alerting in July.
        text = VALUES.read_text()
        report_back = workflow_block(text, "aurora-report-back")
        for marker in ("aurora-link", "link-datos", "link-incident",
                       "mark-linked", "enrich_incident", "generatorURL",
                       "aurora_incident_id"):
            self.assertNotIn(marker, report_back)


if __name__ == "__main__":
    unittest.main()

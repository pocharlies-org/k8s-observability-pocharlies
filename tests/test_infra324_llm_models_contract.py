"""Contract: Aurora and Keep ask the resident LLM by name (INFRA-324).

Decision (owner, 2026-10-03, INFRA-325): the LLM roles of Aurora and the LLM
steps of Keep name ``qwen38-flash-next`` directly — the single resident of the
``llm-tp`` compute profile — instead of routing through the ``tooling`` alias.
The resident fallback lives in the LiteLLM config (k8s-litellm-pocharlies),
not in these values, and the key allowlists live only in LiteLLM's DB
(INFRA-431). These tests pin the YAML text itself, same pattern as
``test_keep_aurora_dispatch_contract.py``; they run in ``ci.yml`` without
Postgres.

Aurora cases (INFRA-325) are below, Keep cases (INFRA-327) after them:
every ``model:`` of the LLM steps in ``keep/values.yaml`` and both
``OPENAI_MODEL_NAME`` entries == ``qwen38-flash-next`` (the steps cannot
reference an env var — the litellm provider's ``with:`` takes literals — so
this test, not a comment, is what keeps them one truth), and the
``aurora-report-back`` workflow must not contain the ``hermes-rca`` action
(C5/SC-1432: no second RCA path).
"""

from pathlib import Path
import re
import unittest


REPO = Path(__file__).resolve().parents[1]
AURORA_VALUES = REPO / "aurora" / "values.yaml"
KEEP_VALUES = REPO / "keep" / "values.yaml"

EXPECTED_AURORA_MODEL = "bedrock/qwen38-flash-next"
AURORA_MODEL_KEYS = (
    "MAIN_MODEL",
    "SUMMARIZATION_MODEL",
    "ENRICHMENT_MODEL",
    "RCA_MODEL",
    "GUARDRAILS_LLM_MODEL",
)


class AuroraModelsContract(unittest.TestCase):
    def test_five_roles_name_the_resident(self):
        """The five *_MODEL of aurora/values.yaml are bedrock/qwen38-flash-next."""
        text = AURORA_VALUES.read_text(encoding="utf-8")
        for key in AURORA_MODEL_KEYS:
            match = re.search(
                r"^  " + key + r":\s*(\S+)", text, re.MULTILINE
            )
            self.assertIsNotNone(
                match, f"{key} missing from aurora/values.yaml"
            )
            self.assertEqual(
                match.group(1),
                EXPECTED_AURORA_MODEL,
                f"{key} must name the resident directly (INFRA-325)",
            )

    def test_no_residual_tooling_alias_in_model_fields(self):
        """No *_MODEL field still points at the retired `tooling` alias."""
        text = AURORA_VALUES.read_text(encoding="utf-8")
        for key in AURORA_MODEL_KEYS:
            match = re.search(
                r"^  " + key + r":\s*(\S+)", text, re.MULTILINE
            )
            if match:
                self.assertNotIn(
                    "tooling",
                    match.group(1),
                    f"{key} still routes through the `tooling` alias",
                )



def workflow_block(text: str, wf_id: str) -> str:
    """Return the YAML body of one workflow (same helper as
    test_keep_aurora_dispatch_contract.py)."""
    match = re.search(
        r"^      - id: " + re.escape(wf_id) + r"\n(?P<block>.*?)(?=^      - id: |\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if not match:
        raise AssertionError(f"{wf_id} workflow not found")
    return match.group("block")


EXPECTED_KEEP_MODEL = "qwen38-flash-next"


class KeepModelsContract(unittest.TestCase):
    def test_llm_steps_name_the_resident(self):
        """Every ``model:`` of the LLM steps in keep/values.yaml is
        qwen38-flash-next — the two steps of the contract are ``llm-rca``
        (aurora-report-back) and ``llm-summary`` (incident-summary, disabled
        but the literal changes too, architect's condition 1)."""
        models = re.findall(
            r"^\s+model:\s*(\S+)\s*$",
            KEEP_VALUES.read_text(encoding="utf-8"),
            re.MULTILINE,
        )
        self.assertEqual(
            len(models), 2, f"expected the two LLM steps, found {models}"
        )
        for model in models:
            self.assertEqual(
                model,
                EXPECTED_KEEP_MODEL,
                "LLM steps must name the resident directly (INFRA-327)",
            )

    def test_openai_model_name_is_one_truth(self):
        """backend.env and frontend.env both carry OPENAI_MODEL_NAME ==
        qwen38-flash-next (the two appearances of the architect's condition
        2, located by name, not by line number)."""
        values = re.findall(
            r"- name: OPENAI_MODEL_NAME\n"
            r"(?:\s*#.*\n)*"
            r"\s*value:\s*(\S+)",
            KEEP_VALUES.read_text(encoding="utf-8"),
        )
        self.assertEqual(
            len(values), 2,
            f"expected OPENAI_MODEL_NAME in backend and frontend, found {values}",
        )
        for value in values:
            self.assertEqual(
                value,
                EXPECTED_KEEP_MODEL,
                "OPENAI_MODEL_NAME must match the step models (INFRA-327)",
            )

    def test_no_residual_tooling_alias_in_keep(self):
        """No step ``model:`` nor ``OPENAI_MODEL_NAME`` still points at the
        retired ``tooling`` alias."""
        text = KEEP_VALUES.read_text(encoding="utf-8")
        for model in re.findall(r"^\s+model:\s*(\S+)\s*$", text, re.MULTILINE):
            self.assertNotIn("tooling", model, "step still uses the `tooling` alias")
        for value in re.findall(
            r"- name: OPENAI_MODEL_NAME\n(?:\s*#.*\n)*\s*value:\s*(\S+)", text
        ):
            self.assertNotIn("tooling", value, "OPENAI_MODEL_NAME still uses `tooling`")

    def test_aurora_report_back_has_no_hermes_rca(self):
        """C5 / SC-1432: the second RCA path (the ``hermes-rca`` action that
        POSTed to the sre-devops webhook) must not come back — the only RCA
        publisher of this workflow is the Telegram action."""
        block = workflow_block(KEEP_VALUES.read_text(encoding="utf-8"), "aurora-report-back")
        self.assertNotIn("hermes-rca", block)


if __name__ == "__main__":
    unittest.main()

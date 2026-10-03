"""Contract: Aurora and Keep ask the resident LLM by name (INFRA-324).

Decision (owner, 2026-10-03, INFRA-325): the LLM roles of Aurora and the LLM
steps of Keep name ``qwen38-flash-next`` directly — the single resident of the
``llm-tp`` compute profile — instead of routing through the ``tooling`` alias.
The resident fallback lives in the LiteLLM config (k8s-litellm-pocharlies),
not in these values, and the key allowlists live only in LiteLLM's DB
(INFRA-431). These tests pin the YAML text itself, same pattern as
``test_keep_aurora_dispatch_contract.py``; they run in ``ci.yml`` without
Postgres.

Aurora cases (INFRA-325) are below. The Keep cases (INFRA-327: every
``model:`` of the LLM steps in ``keep/values.yaml`` and both
``OPENAI_MODEL_NAME`` entries == ``qwen38-flash-next``, and the
``aurora-report-back`` workflow must not contain the ``hermes-rca`` action —
C5/SC-1432) are added by INFRA-327 on top of this file.
"""

from pathlib import Path
import re
import unittest


REPO = Path(__file__).resolve().parents[1]
AURORA_VALUES = REPO / "aurora" / "values.yaml"

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


if __name__ == "__main__":
    unittest.main()

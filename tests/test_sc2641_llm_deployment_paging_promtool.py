"""promtool test of the LLM paging coverage (SC-2641 / DEPL-15279).

Runs the live pocharlies-service-visibility group from manifests/rules.yaml against
tests/promtool/llm-deployment-paging.test.yaml (harness: tests/promtool_rules.py),
and pins the two invariants the DEPL incident broke:

  1. la genérica de 15 min excluye la identidad actual del perfil llm-tp
     (`qwen38-flash-next.*`), no los nombres muertos (`vllm-*`, `.*-bench`);
  2. la copia del chart `KubeDeploymentReplicasMismatch` está desactivada en
     victoria-metrics/values.yaml (el chart no puede excluir deployments y cada
     carga de modelo montaba el incidente DEPL con su warning).
"""

import unittest

import yaml

from promtool_rules import ROOT, run_promtool, vmrule_groups

CASES = ROOT / "tests" / "promtool" / "llm-deployment-paging.test.yaml"


class LlmDeploymentPagingPromtoolTest(unittest.TestCase):
    def test_promtool_cases(self):
        run_promtool(self, vmrule_groups("pocharlies-service-visibility"), "llm-deployment-paging.rules.yaml", CASES)

    def test_chart_replicas_mismatch_disabled(self):
        values = yaml.safe_load((ROOT / "victoria-metrics" / "values.yaml").read_text())
        rule = values["defaultRules"]["rules"]["KubeDeploymentReplicasMismatch"]
        self.assertFalse(rule["create"], "la copia del chart debe estar desactivada: cubre lo mismo "
                                          "KubernetesDeploymentUnavailable (crítica) y no sabe excluir el perfil llm-tp")


if __name__ == "__main__":
    unittest.main()

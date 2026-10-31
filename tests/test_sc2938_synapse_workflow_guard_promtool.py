"""promtool test de la guarda de pipeline de SynapseWorkflowFailed (SC-2938).

Corre el grupo keep.hub-health vivo de manifests/rules.yaml contra
tests/promtool/synapse-workflow-guard.test.yaml (harness: tests/promtool_rules.py).
"""

import unittest

from promtool_rules import ROOT, run_promtool, vmrule_groups

CASES = ROOT / "tests" / "promtool" / "synapse-workflow-guard.test.yaml"


class SynapseWorkflowGuardPromtoolTest(unittest.TestCase):
    def test_promtool_cases(self):
        run_promtool(self, vmrule_groups("keep-hub-health"), "synapse-workflow.rules.yaml", CASES)


if __name__ == "__main__":
    unittest.main()

"""promtool test de KeepIngestionSilent (SC-3738).

Cubre la agregación de réplicas del grupo keep.hub-health de manifests/rules.yaml:
con el increase sumado sobre las dos réplicas del VMAlertmanager (SC-3711), una sola
en silencio (rollout, estado heredado por gossip) no dispara y el silencio de todas
sí. Casos: tests/promtool/keep-ingestion-silent.test.yaml (harness: tests/promtool_rules.py).
"""

import unittest

from promtool_rules import ROOT, run_promtool, vmrule_groups

CASES = ROOT / "tests" / "promtool" / "keep-ingestion-silent.test.yaml"


class KeepIngestionSilentPromtoolTest(unittest.TestCase):
    def test_promtool_cases(self):
        run_promtool(self, vmrule_groups("keep-hub-health"),
                     "keep-hub-health.rules.yaml", CASES)


if __name__ == "__main__":
    unittest.main()

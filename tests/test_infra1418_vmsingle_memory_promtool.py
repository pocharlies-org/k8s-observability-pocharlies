"""promtool test of the pocharlies.vmsingle-memory pair (INFRA-1418).

Runs the live VMRule from manifests/rules.yaml against
tests/promtool/vmsingle-memory.test.yaml (harness: tests/promtool_rules.py).
Cubre el desdoblamiento del umbral 0.8/5m del operador (TooHighMemoryUsage,
desactivada en victoria-metrics/values.yaml): 0.75/24h es capacidad y 0.92/5m
es riesgo real de OOMKill. El caso de 0.80 fija que el ratio que disparaba
critical antes ya no lo hace.
"""

import unittest

from promtool_rules import ROOT, run_promtool, vmrule_groups

CASES = ROOT / "tests" / "promtool" / "vmsingle-memory.test.yaml"


class VmsingleMemoryPromtoolTest(unittest.TestCase):
    def test_promtool_cases(self):
        run_promtool(self, vmrule_groups("pocharlies-vmsingle-memory"), "vmsingle-memory.rules.yaml", CASES)


if __name__ == "__main__":
    unittest.main()

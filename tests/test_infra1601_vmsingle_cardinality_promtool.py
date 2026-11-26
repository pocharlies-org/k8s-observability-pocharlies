"""promtool test de la VMRule pocharlies-vmsingle-cardinality (INFRA-1601, SC-6644).

Runs the live pocharlies.vmsingle-cardinality group from
manifests/vmsingle-cardinality-rules.yaml against
tests/promtool/vmsingle-cardinality.test.yaml (harness: tests/promtool_rules.py).
Cubre el disparo de las tres reglas con series sintéticas calibradas al incidente
del 25-11 (la condición se cumple sostenida → WARNING antes de la crítica del
chart) y sus negativos: 2 GB/día de índice, índice menguante tras reinicio y
1M series/día no disparan.
"""

import unittest

from promtool_rules import ROOT, run_promtool, vmrule_groups

CASES = ROOT / "tests" / "promtool" / "vmsingle-cardinality.test.yaml"
MANIFEST = ROOT / "manifests" / "vmsingle-cardinality-rules.yaml"


class VmsingleCardinalityPromtoolTest(unittest.TestCase):
    def test_promtool_cases(self):
        run_promtool(self, vmrule_groups("pocharlies-vmsingle-cardinality", MANIFEST),
                     "vmsingle-cardinality.rules.yaml", CASES)


if __name__ == "__main__":
    unittest.main()

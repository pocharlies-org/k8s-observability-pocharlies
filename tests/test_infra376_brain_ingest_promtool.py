"""promtool test of the BrainIngestConsecutiveFailures VMRule (INFRA-376).

Runs the live pocharlies-brain-ingest group from manifests/rules.yaml against
tests/promtool/brain-ingest.test.yaml (harness: tests/promtool_rules.py).
"""

import unittest

from promtool_rules import ROOT, run_promtool, vmrule_groups

CASES = ROOT / "tests" / "promtool" / "brain-ingest.test.yaml"


class BrainIngestPromtoolTest(unittest.TestCase):
    def test_promtool_cases(self):
        run_promtool(self, vmrule_groups("pocharlies-brain-ingest"), "brain-ingest.rules.yaml", CASES)


if __name__ == "__main__":
    unittest.main()

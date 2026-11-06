"""promtool test of the ScrapePoolHasNoTargets VMRule (SC-4654).

Runs the live pocharlies.vmagent-scrape-pools group from manifests/rules.yaml
against tests/promtool/scrape-pools.test.yaml (harness: tests/promtool_rules.py).
"""

import unittest

from promtool_rules import ROOT, run_promtool, vmrule_groups

CASES = ROOT / "tests" / "promtool" / "scrape-pools.test.yaml"


class ScrapePoolsPromtoolTest(unittest.TestCase):
    def test_promtool_cases(self):
        run_promtool(self, vmrule_groups("pocharlies-vmagent-scrape-pools"),
                     "scrape-pools.rules.yaml", CASES)


if __name__ == "__main__":
    unittest.main()

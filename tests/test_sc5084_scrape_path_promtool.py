"""promtool test of the scrape-path VMRule (SC-5084).

Runs the live scrape-path group from manifests/scrape-path-rules.yaml against
tests/promtool/scrape-path.test.yaml (harness: tests/promtool_rules.py). The
pending-oscillation case is the regression for the false-positive storm: the
old `pending_data_bytes > 0` fired with a healthy data-plane.
"""

import unittest

from promtool_rules import ROOT, run_promtool, vmrule_groups

CASES = ROOT / "tests" / "promtool" / "scrape-path.test.yaml"
RULES_FILE = ROOT / "manifests" / "scrape-path-rules.yaml"


class ScrapePathPromtoolTest(unittest.TestCase):
    def test_promtool_cases(self):
        run_promtool(
            self,
            vmrule_groups("scrape-path", RULES_FILE),
            "scrape-path.rules.yaml",
            CASES,
        )


if __name__ == "__main__":
    unittest.main()

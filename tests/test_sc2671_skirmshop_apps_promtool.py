"""promtool test of the affiliate/skirmshop restart-spike and OOMKilled rules (SC-2671).

Runs the live affiliate-app.runtime and skirmshop-apps.runtime groups from
manifests/rules.yaml against tests/promtool/skirmshop-apps.test.yaml
(harness: tests/promtool_rules.py). Fixes the CRIT-15306 misattribution:
collections-tree-app restarts fired AffiliateAppRestartSpike because the
affiliate rules had no pod scope.
"""

import unittest

from promtool_rules import ROOT, run_promtool, vmrule_groups

CASES = ROOT / "tests" / "promtool" / "skirmshop-apps.test.yaml"


class SkirmshopAppsPromtoolTest(unittest.TestCase):
    def test_promtool_cases(self):
        groups = [g for g in vmrule_groups("affiliate-app-reliability")
                  if g["name"] in ("affiliate-app.runtime", "skirmshop-apps.runtime")]
        run_promtool(self, groups, "skirmshop-apps.rules.yaml", CASES)


if __name__ == "__main__":
    unittest.main()

"""promtool test of the pocharlies-gmail-token VMRule (SC-5955).

Runs the live pocharlies.gmail-token group from manifests/gmail-token-rules.yaml
against tests/promtool/gmail-token.test.yaml (harness: tests/promtool_rules.py).
"""

import unittest

from promtool_rules import ROOT, run_promtool, vmrule_groups

CASES = ROOT / "tests" / "promtool" / "gmail-token.test.yaml"
MANIFEST = ROOT / "manifests" / "gmail-token-rules.yaml"


class GmailTokenPromtoolTest(unittest.TestCase):
    def test_promtool_cases(self):
        run_promtool(self, vmrule_groups("pocharlies-gmail-token", MANIFEST),
                     "gmail-token.rules.yaml", CASES)


if __name__ == "__main__":
    unittest.main()

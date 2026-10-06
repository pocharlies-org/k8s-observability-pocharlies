"""promtool test of the AtlassianMcpToolDown VMRule (SC-1835, H5 de SC-1728).

Runs the live pocharlies.atlassian-mcp group from manifests/atlassian-mcp-rules.yaml
against tests/promtool/atlassian-mcp.test.yaml (harness: tests/promtool_rules.py).
"""

import unittest

from promtool_rules import ROOT, run_promtool, vmrule_groups

CASES = ROOT / "tests" / "promtool" / "atlassian-mcp.test.yaml"
MANIFEST = ROOT / "manifests" / "atlassian-mcp-rules.yaml"


class AtlassianMcpPromtoolTest(unittest.TestCase):
    def test_promtool_cases(self):
        run_promtool(self, vmrule_groups("pocharlies-atlassian-mcp", MANIFEST),
                     "atlassian-mcp.rules.yaml", CASES)


if __name__ == "__main__":
    unittest.main()

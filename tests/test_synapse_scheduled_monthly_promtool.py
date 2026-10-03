"""promtool test of SynapseScheduledWorkflowRunStalledMonthly and of the processor_fees
exclusion in SynapseScheduledWorkflowStalled (pocharlies-synapse-core VMRule).

Extracts those two rules from manifests/rules.yaml, so the test runs against the exact
expressions ArgoCD ships, and feeds them to tests/promtool/synapse-scheduled-monthly.test.yaml.
Same promtool contract as test_infra376_brain_ingest_promtool.py (PROMTOOL / REQUIRE_PROMTOOL).
"""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "manifests" / "rules.yaml"
CASES = ROOT / "tests" / "promtool" / "synapse-scheduled-monthly.test.yaml"
ALERTS = {"SynapseScheduledWorkflowRunStalledMonthly", "SynapseScheduledWorkflowStalled"}


def promtool():
    return os.environ.get("PROMTOOL") or shutil.which("promtool")


class SynapseScheduledMonthlyPromtoolTest(unittest.TestCase):
    def test_promtool_cases(self):
        binary = promtool()
        if not binary:
            if os.environ.get("REQUIRE_PROMTOOL"):
                self.fail("promtool not found and REQUIRE_PROMTOOL is set")
            self.skipTest("promtool not installed")
        docs = [d for d in yaml.safe_load_all(RULES.read_text()) if d]
        rule = next(d for d in docs if d.get("metadata", {}).get("name") == "pocharlies-synapse-core")
        rules = [r for g in rule["spec"]["groups"] for r in g["rules"] if r.get("alert") in ALERTS]
        self.assertEqual({r["alert"] for r in rules}, ALERTS)
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "synapse-scheduled.rules.yaml").write_text(
                yaml.safe_dump({"groups": [{"name": "synapse-scheduled", "rules": rules}]})
            )
            shutil.copy(CASES, tmp)
            out = subprocess.run([binary, "test", "rules", CASES.name], cwd=tmp, capture_output=True, text=True)
        print(out.stdout, out.stderr)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)


if __name__ == "__main__":
    unittest.main()

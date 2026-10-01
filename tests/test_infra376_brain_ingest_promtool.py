"""promtool test of the BrainIngestConsecutiveFailures VMRule (INFRA-376).

Extracts the live group from manifests/rules.yaml, so the test runs against the
exact expression ArgoCD ships, and feeds it to tests/promtool/*.test.yaml.
Needs `promtool` (PROMTOOL=<path>, or on PATH; CI installs it and sets
REQUIRE_PROMTOOL=1 so a missing binary fails instead of skipping).
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
CASES = ROOT / "tests" / "promtool" / "brain-ingest.test.yaml"


def promtool():
    return os.environ.get("PROMTOOL") or shutil.which("promtool")


class BrainIngestPromtoolTest(unittest.TestCase):
    def test_promtool_cases(self):
        binary = promtool()
        if not binary:
            if os.environ.get("REQUIRE_PROMTOOL"):
                self.fail("promtool not found and REQUIRE_PROMTOOL is set")
            self.skipTest("promtool not installed")
        docs = [d for d in yaml.safe_load_all(RULES.read_text()) if d]
        rule = next(d for d in docs if d.get("metadata", {}).get("name") == "pocharlies-brain-ingest")
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "brain-ingest.rules.yaml").write_text(yaml.safe_dump({"groups": rule["spec"]["groups"]}))
            shutil.copy(CASES, tmp)
            out = subprocess.run(
                [binary, "test", "rules", CASES.name],
                cwd=tmp, capture_output=True, text=True,
            )
        print(out.stdout, out.stderr)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)


if __name__ == "__main__":
    unittest.main()

"""Shared harness for the promtool rule tests.

Extracts rules from manifests/rules.yaml (the exact expressions ArgoCD ships) and runs
`promtool test rules` against a cases file under tests/promtool/. Needs `promtool`
(PROMTOOL=<path>, or on PATH; CI installs it and sets REQUIRE_PROMTOOL=1 so a missing
binary fails instead of skipping).
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


def vmrule_groups(name, rules_file=RULES):
    """spec.groups of the VMRule `name` in `rules_file` (default manifests/rules.yaml;
    las VMRule con fichero propio —patrón external-secrets-rules.yaml— lo pasan)."""
    docs = [d for d in yaml.safe_load_all(Path(rules_file).read_text()) if d]
    return next(d for d in docs if d.get("metadata", {}).get("name") == name)["spec"]["groups"]


def run_promtool(test: unittest.TestCase, groups, rules_file: str, cases: Path) -> None:
    """Write `groups` to `rules_file` next to a copy of `cases` and assert promtool passes."""
    binary = os.environ.get("PROMTOOL") or shutil.which("promtool")
    if not binary:
        if os.environ.get("REQUIRE_PROMTOOL"):
            test.fail("promtool not found and REQUIRE_PROMTOOL is set")
        test.skipTest("promtool not installed")
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, rules_file).write_text(yaml.safe_dump({"groups": groups}))
        shutil.copy(cases, tmp)
        out = subprocess.run([binary, "test", "rules", cases.name], cwd=tmp, capture_output=True, text=True)
    print(out.stdout, out.stderr)
    test.assertEqual(out.returncode, 0, out.stdout + out.stderr)

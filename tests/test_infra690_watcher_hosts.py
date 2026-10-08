"""dgx-cluster-health-watcher walks one host table (INFRA-690: dgx3 is the third Spark).

Runs the real health-check.sh from manifests/dgx-cluster-health-watcher.yaml with stub
ssh/kubectl/curl on PATH (jq is the real one: the ARC runner ships it). Checks that the
ssh checks cover dgx, dgx2 and dgx3, that dgx3 is NOT probed on the vLLM hostPort, and that an
unreachable dgx3 (not joined yet) is a warning line, never a red one.
"""

import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "manifests" / "dgx-cluster-health-watcher.yaml"

STUBS = {
    # ssh: log the call, fail (255) for the IPs in $SSH_DOWN, answer nvidia-smi/nvme, empty otherwise
    "ssh": r"""#!/bin/sh
echo "$*" >> "$STUB_LOG"
for ip in $SSH_DOWN; do case "$*" in *"@$ip "*) exit 255;; esac; done
case "$*" in
  *nvidia-smi*) echo "1024, 122880, 5, 40";;
  *nvme*) echo 3;;
esac
""",
    "kubectl": """#!/bin/sh
case "$*" in *"get pods -o json"*) echo '{"items":[]}';; esac
""",
    "curl": """#!/bin/sh
echo "$*" >> "$STUB_LOG"
case "$*" in
  *"-w"*) printf 200;;
  *"/v1/models"*) echo '{"data":[{"id":"m"}]}';;
esac
""",
}


def script_text():
    docs = [d for d in yaml.safe_load_all(MANIFEST.read_text()) if d]
    cm = next(d for d in docs if d.get("kind") == "ConfigMap" and d["metadata"]["name"] == "cluster-health-watcher-scripts")
    return cm["data"]["health-check.sh"]


def section(report, title):
    lines = report.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(title)) + 1
    end = next((i for i in range(start, len(lines)) if not lines[i].strip()), len(lines))
    return lines[start:end]


class WatcherHostsTest(unittest.TestCase):
    def run_watcher(self, ssh_down=""):
        if not shutil.which("jq"):
            self.skipTest("jq not installed")
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "bin").mkdir()
            for name, body in STUBS.items():
                path = tmp / "bin" / name
                path.write_text(body)
                path.chmod(path.stat().st_mode | stat.S_IEXEC)
            script = tmp / "health-check.sh"
            script.write_text(script_text())
            env = {**os.environ, "PATH": f"{tmp / 'bin'}:{os.environ['PATH']}", "STATE_DIR": str(tmp / "state"),
                   "POST_MODE": "never", "STUB_LOG": str(tmp / "calls.log"), "SSH_DOWN": ssh_down}
            self.assertEqual(subprocess.run(["bash", "-n", str(script)], capture_output=True).returncode, 0)
            out = subprocess.run(["bash", str(script)], env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(out.returncode, 0, out.stderr)
            return out.stdout, (tmp / "calls.log").read_text()

    def test_three_hosts_ssh_checks_and_two_hostport_probes(self):
        report, calls = self.run_watcher()
        self.assertEqual(section(report, "Xid / NVRM"), ["  ✅ dgx: 0 events", "  ✅ dgx2: 0 events", "  ✅ dgx3: 0 events"])
        self.assertEqual(
            section(report, "GPU snapshot"),
            [f"  DGX{n}: mem 1.0/120 GB · util 5% · 40°C" for n in (1, 2, 3)],
        )
        hostport = section(report, "Direct hostPort")
        self.assertEqual([line.split()[0] for line in hostport], ["DGX1", "DGX2"])
        self.assertNotIn("192.168.50.143:8200", calls)
        for target in ("dibanerz@192.168.50.140", "dibanez@192.168.50.141", "dibanez@192.168.50.143"):
            self.assertIn(target, calls)

    def test_dgx3_not_joined_yet_is_a_warning_not_red(self):
        report, _ = self.run_watcher(ssh_down="192.168.50.143")
        self.assertIn("  ⚠️ dgx3: ssh failed", section(report, "Xid / NVRM"))
        self.assertIn("  DGX3: read failed ⚠️", section(report, "GPU snapshot"))
        self.assertEqual([line for line in report.splitlines() if "dgx3" in line.lower() and ("🔴" in line or "❌" in line)], [])


if __name__ == "__main__":
    unittest.main()

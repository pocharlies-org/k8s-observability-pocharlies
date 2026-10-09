"""Contract: who drains Keep's event workflows (INFRA-378 / INFRA-751 / SC-1711).

Keep 0.52.1 runs without Redis here, so the workflows fired by an alert or an
incident (`notify-incident*`, `notify-alert-summary`, `aurora-investigate`)
travel through an in-memory queue of the process that receives the
Alertmanager webhook, and only that process's WorkflowScheduler drains it.

SC-1711 set `SCHEDULER=false` on keep-backend: every event workflow was queued
and lost. The last Telegram `workflowexecution` before the gap is
2026-10-04 01:24:47Z, the first after it 2026-10-09 15:10:39Z (INFRA-751
restored it), five days with nothing in topic 1248 and no check noticing.

The split pinned here:
- keep-backend: `SCHEDULER=true`, `WORKFLOWS_INTERVAL_ENABLED=false`
  (drains event workflows only);
- keepsvc-scheduler: `SCHEDULER=true`, `WORKFLOWS_INTERVAL_ENABLED=true`
  (the only runner of the `interval` workflows).
"""

from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
VALUES = ROOT / "keep" / "values.yaml"
SCHEDULER = ROOT / "keep" / "scheduler.yaml"


def env_of(entries):
    return {e["name"]: e.get("value") for e in entries}


def backend_env():
    return env_of(yaml.safe_load(VALUES.read_text())["backend"]["env"])


def scheduler_env():
    for doc in yaml.safe_load_all(SCHEDULER.read_text()):
        if doc and doc.get("kind") == "Deployment" and doc["metadata"]["name"] == "keepsvc-scheduler":
            containers = doc["spec"]["template"]["spec"]["containers"]
            return env_of(containers[0]["env"])
    raise AssertionError("Deployment keepsvc-scheduler not found in keep/scheduler.yaml")


class KeepSchedulerSplit(unittest.TestCase):
    def test_backend_drains_event_workflows(self):
        env = backend_env()
        # "true" explicit: the code default is true, but a missing entry is how
        # SC-1711 got undone without anyone reading the diff.
        self.assertEqual(
            env.get("SCHEDULER"), "true",
            "keep-backend must run the WorkflowScheduler: with SCHEDULER=false the "
            "in-memory queue of event workflows is never drained and every Telegram "
            "notification is lost (SC-1711 -> INFRA-751)",
        )

    def test_backend_does_not_run_interval_workflows(self):
        self.assertEqual(
            backend_env().get("WORKFLOWS_INTERVAL_ENABLED"), "false",
            "interval workflows belong to keepsvc-scheduler (SC-1600 load off the ingest path)",
        )

    def test_scheduler_pod_runs_interval_workflows(self):
        env = scheduler_env()
        self.assertEqual(env.get("SCHEDULER"), "true")
        self.assertEqual(env.get("WORKFLOWS_INTERVAL_ENABLED"), "true")


if __name__ == "__main__":
    unittest.main()

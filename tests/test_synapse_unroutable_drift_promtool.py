"""promtool tests of the two Synapse contract-break alerts (SKIRM-351 / C4,
gated by SC-4772 / SC-5206): SynapseUnroutableMessages fires (warning) only on
messages in the unroutable sink, and SynapseTopologyDrift fires (info) on a
command binding without a row in synapse.plugin_actions (gauge
synapse_topology_drift, emitted by the engine's topology_watch in SKIRM-350).
The drift leg was an OR term of the first alert until SC-5206: with an empty
synapse.plugin_actions (no baseline, SKIRM-207) it fired permanently and the
Keep rule synapse-control-plane opened a SYNC incident in every window.

Extracts the rules from the pocharlies-rabbitmq VMRule in manifests/rules.yaml
(the exact expression ArgoCD ships) and runs them against
tests/promtool/synapse-unroutable-drift.test.yaml (harness: tests/promtool_rules.py).
"""

import unittest

from promtool_rules import ROOT, run_promtool, vmrule_groups

CASES = ROOT / "tests" / "promtool" / "synapse-unroutable-drift.test.yaml"
ALERTS = {"SynapseUnroutableMessages", "SynapseTopologyDrift"}


class SynapseUnroutableDriftPromtoolTest(unittest.TestCase):
    def test_promtool_cases(self):
        rules = [
            r for g in vmrule_groups("pocharlies-rabbitmq") for r in g["rules"] if r.get("alert") in ALERTS
        ]
        self.assertEqual({r["alert"] for r in rules}, ALERTS)
        run_promtool(
            self,
            [{"name": "synapse-unroutable-drift", "rules": rules}],
            "synapse-unroutable-drift.rules.yaml",
            CASES,
        )


if __name__ == "__main__":
    unittest.main()

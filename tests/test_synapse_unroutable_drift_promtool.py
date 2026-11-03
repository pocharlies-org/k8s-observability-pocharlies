"""promtool test of SynapseUnroutableMessages (SKIRM-351 / C4): the alert fires
on either cause — messages in the unroutable sink (original behaviour) or a
command binding without a row in synapse.plugin_actions (OR term over the
gauge synapse_topology_drift, emitted by the engine's topology_watch in
SKIRM-350). Same alert name, same alertmanager routing.

Extracts the rule from the pocharlies-rabbitmq VMRule in manifests/rules.yaml
(the exact expression ArgoCD ships) and runs it against
tests/promtool/synapse-unroutable-drift.test.yaml (harness: tests/promtool_rules.py).
"""

import unittest

from promtool_rules import ROOT, run_promtool, vmrule_groups

CASES = ROOT / "tests" / "promtool" / "synapse-unroutable-drift.test.yaml"
ALERTS = {"SynapseUnroutableMessages"}


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

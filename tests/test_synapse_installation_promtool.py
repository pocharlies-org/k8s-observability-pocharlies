"""promtool test de las reglas de Synapse/RabbitMQ filtradas o agrupadas por
instalación (namespace): el motor, el dispatcher y los consumidores de `synapse2`
llevan los mismos nombres que los de producción, y no deben taparla.

Corre SynapseCoreAbsent y SynapseDispatcherNotPublishing (pocharlies-synapse-core)
y RabbitmqFunctionalQueueNoConsumer (pocharlies-rabbitmq), extraídas de
manifests/rules.yaml, contra tests/promtool/synapse-installation.test.yaml
(harness: tests/promtool_rules.py).
"""

import unittest

from promtool_rules import ROOT, run_promtool, vmrule_groups

CASES = ROOT / "tests" / "promtool" / "synapse-installation.test.yaml"
ALERTS = {"SynapseCoreAbsent", "SynapseDispatcherNotPublishing", "RabbitmqFunctionalQueueNoConsumer"}


class SynapseInstallationPromtoolTest(unittest.TestCase):
    def test_promtool_cases(self):
        rules = [
            r
            for vm in ("pocharlies-synapse-core", "pocharlies-rabbitmq")
            for g in vmrule_groups(vm)
            for r in g["rules"]
            if r.get("alert") in ALERTS
        ]
        self.assertEqual({r["alert"] for r in rules}, ALERTS)
        run_promtool(self, [{"name": "synapse-installation", "rules": rules}], "synapse-installation.rules.yaml", CASES)


if __name__ == "__main__":
    unittest.main()
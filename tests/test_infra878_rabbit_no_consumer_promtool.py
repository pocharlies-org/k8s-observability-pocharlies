"""promtool test de RabbitmqFunctionalQueueNoConsumer (INFRA-878).

Corre el grupo vivo del VMRule `pocharlies-rabbitmq` de manifests/rules.yaml contra
tests/promtool/rabbit-no-consumer.test.yaml (harness: tests/promtool_rules.py):
dispara por cola nueva sin consumidor, excluye `synapse.unroutable` (sin
consumidor por diseño) y NO excluye `adapter.telegram.ingress` (tiene
consumidor medido el 17-10; si muere, esta alerta es la única señal).
"""

import unittest

from promtool_rules import ROOT, run_promtool, vmrule_groups

CASES = ROOT / "tests" / "promtool" / "rabbit-no-consumer.test.yaml"


class RabbitNoConsumerPromtoolTest(unittest.TestCase):
    def test_promtool_cases(self):
        run_promtool(self, vmrule_groups("pocharlies-rabbitmq"), "rabbit-no-consumer.rules.yaml", CASES)


if __name__ == "__main__":
    unittest.main()

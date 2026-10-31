"""promtool test de la guarda de RabbitmqScrapeMissing / RabbitmqPeersMetricMissing (SC-2938).

Corre el grupo pocharlies.rabbitmq vivo de manifests/rules.yaml contra
tests/promtool/rabbit-scrape-guard.test.yaml (harness: tests/promtool_rules.py).
"""

import unittest

from promtool_rules import ROOT, run_promtool, vmrule_groups

CASES = ROOT / "tests" / "promtool" / "rabbit-scrape-guard.test.yaml"


class RabbitScrapeGuardPromtoolTest(unittest.TestCase):
    def test_promtool_cases(self):
        run_promtool(self, vmrule_groups("pocharlies-rabbitmq"), "rabbit-scrape.rules.yaml", CASES)


if __name__ == "__main__":
    unittest.main()

"""promtool test de la puerta KSM de LlmPoolCapabilityUnavailable (SC-6653).

El absent() no distingue «el slice desapareció» de «kube-state-metrics dejó de
reportar»: el 25-11 un gap de scrape de KSM (22:35-22:39Z, con vmsingle OOMKilled
a las 23:28Z) montó CRIT-21011 con los dos pools bge sanos. Las ramas absent()
llevan desde SC-6653 `and on() (up{job="kube-state-metrics"} == 1)`. Los casos de
tests/promtool/llm-pool.test.yaml fijan las dos mitades: con KSM vivo y el slice
fuera sigue saltando (el caso portante de 2026-08-19), y con KSM caído guarda
silencio.

Runs the rule, extracted from manifests/rules.yaml, via tests/promtool_rules.py.
"""

import unittest

from promtool_rules import ROOT, run_promtool, vmrule_groups

CASES = ROOT / "tests" / "promtool" / "llm-pool.test.yaml"
ALERTS = {"LlmPoolCapabilityUnavailable"}


class LlmPoolKsmGatePromtoolTest(unittest.TestCase):
    def test_promtool_cases(self):
        rules = [
            r
            for g in vmrule_groups("pocharlies-service-visibility")
            for r in g["rules"]
            if r.get("alert") in ALERTS
        ]
        self.assertEqual({r["alert"] for r in rules}, ALERTS)
        run_promtool(
            self,
            [{"name": "llm-pool", "rules": rules}],
            "llm-pool.rules.yaml",
            CASES,
        )


if __name__ == "__main__":
    unittest.main()

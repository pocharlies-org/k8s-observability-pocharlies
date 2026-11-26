"""promtool test del guard anti-parpadeo de LlmPoolCapabilityUnavailable (SC-6673).

CRIT-21045 (causa critical-safety-net:b1c1a679ed, Requests SC-5546/6460/6653/6660/6673/6693
en 7 días): la alerta ardió 25-11 22:45→26-11 00:10 UTC con `kube_endpointslice_endpoints
{ready="true"}` = 1 continuo en ambos pools. La causa no fue el pool: fue el scrape de
kube-state-metrics cortado por el timeout (up a 0, 41 veces en 18 h; duration clavada en
10 s), que deja la serie ausente y las patas absent() de la regla disparan un crítico
falso. El `unless on()` añadido a la expr supime solo el parpadeo (min==0 y max==1 en
10 min); con kube-state-metrics ciego del todo la alerta vuelve a saltar — se falla hacia
avisar, nunca hacia callar (patrón SC-6661 en FrigateCaido). La raíz vive aparte:
scrapeTimeout 25 s en victoria-metrics/values.yaml (patrón SC-6648 con cadvisor).

Runs the rule, extracted from manifests/rules.yaml, via tests/promtool_rules.py.
"""

import unittest

from promtool_rules import ROOT, run_promtool, vmrule_groups

CASES = ROOT / "tests" / "promtool" / "llm-pool-ksm-guard.test.yaml"
ALERTS = {"LlmPoolCapabilityUnavailable"}


class LlmPoolKsmGuardPromtoolTest(unittest.TestCase):
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
            [{"name": "llm-pool-ksm-guard", "rules": rules}],
            "llm-pool-ksm-guard.rules.yaml",
            CASES,
        )


if __name__ == "__main__":
    unittest.main()

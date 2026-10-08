"""Contract for the Frigate correlation rule (INFRA-712, P2b of INFRA-701).

The four alerts of ``manifests/frigate-rules.yaml`` arrive as ``warning`` and, without
a correlation rule, Keep records them and stays silent (Keep only notifies
INCIDENTS): they never reached topic 1248. ``frigate-vigilancia`` turns them into
one incident per alert family. There is no Alertmanager route to add: the tree ends in a
catch-all to Keep and no warning blackhole exists any more (alertmanager-config.yaml).
The names are read from the live VMRule, not copied, so a fifth ``Frigate*`` alert added
later fails here until the rule covers it.

The checks every such rule shares live in ``keep_correlation.CorrelationContract``;
this file keeps only what is specific to the Frigate family.

Hermetic: no kubectl, no network.
"""

from pathlib import Path
import unittest

import yaml

from keep_correlation import CorrelationContract

REPO = Path(__file__).resolve().parents[1]


class FrigateCorrelationTests(CorrelationContract, unittest.TestCase):
    RULE = "frigate-vigilancia"
    VMRULE_FILE = REPO / "manifests" / "frigate-rules.yaml"
    VMRULE = "pocharlies-frigate"
    INCIDENT_NAME = "Vigilancia: {{ alertname }}"

    def test_the_vmrule_has_the_four_alerts_all_warning(self):
        # All warning: critical-safety-net does not pick them (shared test). Raising one to
        # critical would double-notify and fails that test, which is the point.
        names = ["FrigateAlmacenamientoLleno", "FrigateCaido", "FrigateCamaraSinFps", "FrigateDetectorLento"]
        self.assertEqual(self.alerts, {name: "warning" for name in names})

    def test_no_alertmanager_route_needed(self):
        # Everything reaches Keep through the catch-all; no blackhole to get in front of.
        cfg = yaml.safe_load((REPO / "manifests" / "alertmanager-config.yaml").read_text())
        route = cfg["spec"]["route"]
        self.assertEqual(route["receiver"], "keep")
        self.assertEqual(route["routes"][-1], {"receiver": "keep"})
        self.assertNotIn("blackhole", {r["name"] for r in cfg["spec"]["receivers"]})


if __name__ == "__main__":
    unittest.main()

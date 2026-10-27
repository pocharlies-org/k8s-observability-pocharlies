"""promtool test of the Gmail watch-expiration alerts (INFRA-954):
SynapseGmailWatchExpired and SynapseGmailWatchRenewerStale (pocharlies-synapse VMRule).

The metric is pushed by the synapse-gmail-watch-renew CronJob to pushgateway
(manifests/pushgateway.yaml); without a destination these rules had no series
to evaluate. Runs those rules, extracted from manifests/rules.yaml, against
tests/promtool/gmail-watch.test.yaml (harness: tests/promtool_rules.py).
"""

import unittest

from promtool_rules import ROOT, run_promtool, vmrule_groups

CASES = ROOT / "tests" / "promtool" / "gmail-watch.test.yaml"
ALERTS = {"SynapseGmailWatchExpired", "SynapseGmailWatchRenewerStale"}


class Infra954GmailWatchPromtoolTest(unittest.TestCase):
    def test_promtool_cases(self):
        rules = [r for g in vmrule_groups("pocharlies-synapse") for r in g["rules"] if r.get("alert") in ALERTS]
        self.assertEqual({r["alert"] for r in rules}, ALERTS)
        run_promtool(self, [{"name": "gmail-watch", "rules": rules}], "gmail-watch.rules.yaml", CASES)


if __name__ == "__main__":
    unittest.main()

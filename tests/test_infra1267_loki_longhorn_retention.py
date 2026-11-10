"""Contract: longhorn-system logs are retained 14 days in Loki (INFRA-1267).

SC-5058: investigating a stuck Longhorn detach on 2026-11-10, the
longhorn-manager / instance-manager logs were already gone — the global
retention is 24 h (Dani's decision, INFRA-1175, and it stays 24 h) and the
kubelet on-disk rotation ate the incident window.

The exception lives in ``loki/values.yaml`` as a Loki runtime-config
per-stream rule: only ``{namespace="longhorn-system"}`` gets 336 h of
retention and query lookback. This test pins three things, because each one
alone is silently useless:

1. the per-stream rule exists with retention and max_query_lookback >= 336 h;
2. the global ``retention_period`` is still 24 h (the exception must not
   quietly become a global raise — that is Dani's call, not a side effect);
3. ``singleBinary.extraArgs`` carries ``-runtime-config.file=...`` — chart
   grafana/loki 7.0.0 mounts the ``loki-runtime`` ConfigMap but never adds
   the flag, so without it Loki ignores the runtime config entirely.
"""

from pathlib import Path
import re
import unittest

import yaml

REPO = Path(__file__).resolve().parents[1]
LOKI_VALUES = REPO / "loki" / "values.yaml"

NAMESPACE = "longhorn-system"
MIN_HOURS = 336  # 14 days


def _hours(value):
    m = re.fullmatch(r"(\d+)([smhd])", str(value))
    assert m, f"not a duration: {value!r}"
    return int(m.group(1)) * {"s": 1 / 3600, "m": 1 / 60, "h": 1, "d": 24}[m.group(2)]


class LonghornRetention(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.values = yaml.safe_load(LOKI_VALUES.read_text())

    def _longhorn_rule(self):
        rules = self.values["loki"]["runtimeConfig"]["limits"]["per_stream"]
        return [r for r in rules if NAMESPACE in r["selector"]]

    def test_per_stream_rule_retains_14_days(self):
        rules = self._longhorn_rule()
        self.assertEqual(len(rules), 1, f"expected exactly one rule for {NAMESPACE}")
        limits = rules[0]["limits"]
        self.assertGreaterEqual(_hours(limits["retention"]), MIN_HOURS)
        self.assertGreaterEqual(_hours(limits["max_query_lookback"]), MIN_HOURS)

    def test_global_retention_stays_24h(self):
        lc = self.values["loki"]["limits_config"]
        self.assertEqual(lc["retention_period"], "24h")
        self.assertEqual(lc["max_query_lookback"], "24h")

    def test_loki_loads_the_runtime_config(self):
        args = self.values["singleBinary"]["extraArgs"]
        self.assertIn(
            "-runtime-config.file=/etc/loki/runtime-config/runtime-config.yaml",
            args,
        )


if __name__ == "__main__":
    unittest.main()

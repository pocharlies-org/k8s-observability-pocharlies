"""Contract: longhorn-system logs are retained 14 days in Loki (INFRA-1267).

SC-5058: investigating a stuck Longhorn detach on 2026-11-10, the
longhorn-manager / instance-manager logs were already gone — the global
retention was 24 h (Dani's decision, INFRA-1175) and the kubelet on-disk
rotation ate the incident window.

The requirement is met by the GLOBAL retention, raised to 336 h on
2026-11-10 by INFRA-1260. It is NOT met by a per-stream runtime-config
rule: INFRA-1267 first tried that, but Loki's runtime-config only accepts
`overrides`, `configs` and `multi_kv_config` (pkg/loki/runtime_config.go,
strict decoding) — a `limits: per_stream:` key makes Loki abort at startup.
That crash took down loki-0 in production the same afternoon (SC-5253,
Keep incident DEPL-18987) and the block was removed in the same day.

So this test pins two things:

1. the retention requirement itself: global `retention_period` and
   `max_query_lookback` >= 336 h, which covers longhorn-system;
2. a guard: `loki.runtimeConfig`, if present, may only carry keys Loki's
   runtimeConfigValues struct actually knows — never reintroduce the
   invented `limits`/`per_stream` schema.
"""

from pathlib import Path
import re
import unittest

import yaml

REPO = Path(__file__).resolve().parents[1]
LOKI_VALUES = REPO / "loki" / "values.yaml"

MIN_HOURS = 336  # 14 days

# Top-level yaml tags of runtimeConfigValues in pkg/loki/runtime_config.go.
VALID_RUNTIME_CONFIG_KEYS = {"overrides", "configs", "multi_kv_config"}


def _hours(value):
    m = re.fullmatch(r"(\d+)([smhd])", str(value))
    assert m, f"not a duration: {value!r}"
    return int(m.group(1)) * {"s": 1 / 3600, "m": 1 / 60, "h": 1, "d": 24}[m.group(2)]


class LonghornRetention(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.values = yaml.safe_load(LOKI_VALUES.read_text())

    def test_retention_covers_14_days(self):
        lc = self.values["loki"]["limits_config"]
        self.assertGreaterEqual(_hours(lc["retention_period"]), MIN_HOURS)
        self.assertGreaterEqual(_hours(lc["max_query_lookback"]), MIN_HOURS)

    def test_runtime_config_only_uses_keys_loki_knows(self):
        rc = self.values["loki"].get("runtimeConfig") or {}
        unknown = set(rc) - VALID_RUNTIME_CONFIG_KEYS
        self.assertFalse(
            unknown,
            f"Loki's runtime-config does not know {sorted(unknown)}; strict "
            "decoding aborts Loki at startup (SC-5253). Only "
            f"{sorted(VALID_RUNTIME_CONFIG_KEYS)} are valid.",
        )


if __name__ == "__main__":
    unittest.main()

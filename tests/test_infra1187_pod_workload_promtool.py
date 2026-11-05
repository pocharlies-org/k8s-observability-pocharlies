"""promtool test de pocharlies.pod-workload (INFRA-1187).

KubePodNotReady/KubeContainerWaiting reemplazadas del chart con etiqueta
`workload` (join kube_pod_owner→kube_replicaset_owner) para que la regla
`deployment-degraded` de Keep agrupe por [namespace, workload]. Corre el grupo
de manifests/pod-workload-rules.yaml contra tests/promtool/pod-workload.test.yaml
(harness: tests/promtool_rules.py).
"""

import unittest

from promtool_rules import ROOT, run_promtool, vmrule_groups

CASES = ROOT / "tests" / "promtool" / "pod-workload.test.yaml"
RULES_FILE = ROOT / "manifests" / "pod-workload-rules.yaml"


class PodWorkloadPromtoolTest(unittest.TestCase):
    def test_promtool_cases(self):
        run_promtool(
            self, vmrule_groups("pocharlies-pod-workload", RULES_FILE), "pod-workload.rules.yaml", CASES
        )


if __name__ == "__main__":
    unittest.main()

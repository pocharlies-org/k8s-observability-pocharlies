#!/usr/bin/env python3
"""INFRA-1600 (SC-6644): el relabel global del vmagent cae cardinalidad sin callar nada.

El PVC de vmsingle se llena de indice (data/indexdb = 78,1 Gi de 80,4 Gi usados el 26-11,
con 2,3 Gi de datos), y el indice crece con las series REGISTRADAS. La correccion es dejar
de registrar las familias de alto coste sin consumidor (buckets de apiserver/etcd/prober y
cadvisor de bajo valor) en `victoria-metrics/values.yaml` ->
`vmagent.spec.globalScrapeMetricRelabelConfigs`.

El riesgo de un drop global es silenciar una alerta o un dashboard. Este test simula la
cadena de relabel con la semantica de Prometheus/VM (regex anclado, etiquetas ausentes =
cadena vacia, `replace` solo actua si hay coincidencia) contra las familias que SI tienen
consumidor vivo, y contra las medidas que se pretenden caer. Si alguien quita la excepcion
de `apiserver_request_sli_duration_seconds_bucket`, la cadena que alimenta
`KubeAPIErrorBudgetBurn` se queda muda y este test salta.

Los numeros de cada familia estan medidos el 26-11 con
`count by (__name__) ({__name__=~"(apiserver|etcd|prober)_.*_bucket"})` y
`count by (__name__) ({__name__=~"container_.*"})` contra vmsingle; la busqueda de
consumidores, sobre las VMRule/PrometheusRule desplegadas, los configmaps con label
`grafana_dashboard` de todos los namespaces, la BD interna de Grafana y los dashboards de
dgx-infra (detalle en la PR).
"""
from __future__ import annotations

import pathlib
import re
import unittest

import yaml

REPO = pathlib.Path(__file__).resolve().parents[1]
VALUES = REPO / "victoria-metrics" / "values.yaml"

# Families with a live consumer: must keep flowing to vmsingle.
MUST_KEEP = [
    # cadena recording rules -> alerta KubeAPIErrorBudgetBurn
    "apiserver_request_sli_duration_seconds_bucket",
    "apiserver_request_sli_duration_seconds_count",
    # alerta KubeClientCertificateExpiration
    "apiserver_client_certificate_expiration_seconds_bucket",
    # alerta KubeClientErrors y el dashboard kubernetes-system-api-server
    "apiserver_request_total",
    # buckets consumidos por dashboards/reglas del stack
    "kubelet_runtime_operations_duration_seconds_bucket",
    "coredns_dns_request_duration_seconds_bucket",
    "rest_client_request_duration_seconds_bucket",
    "storage_operation_duration_seconds_bucket",
    "vm_promscrape_scrape_duration_seconds_bucket",
    "vmalert_remotewrite_sent_rows_bucket",
    # buckets de inferencia que consume el panel Control Nexus (dgx-infra)
    "vllm:time_to_first_token_seconds_bucket",
    "litellm_llm_api_latency_metric_bucket",
    # cadvisor que si se consulta
    "container_memory_working_set_bytes",
    "container_cpu_usage_seconds_total",
    "container_network_receive_bytes_total",
    "container_oom_events_total",
    # metricas del plano de nodo
    "node_cpu_seconds_total",
    "node_filesystem_avail_bytes",
]

# Families measured 26-11 with zero consumers: these are the savings.
MUST_DROP = [
    "apiserver_request_duration_seconds_bucket",
    "apiserver_request_body_size_bytes_bucket",
    "apiserver_response_sizes_bucket",
    "apiserver_watch_list_duration_seconds_bucket",
    "apiserver_watch_cache_read_wait_seconds_bucket",
    "apiserver_watch_events_sizes_bucket",
    "apiserver_admission_webhook_admission_duration_seconds_bucket",
    "apiserver_flowcontrol_request_wait_duration_seconds_bucket",
    "apiserver_cel_evaluation_duration_seconds_bucket",
    "etcd_request_duration_seconds_bucket",
    "etcd_lease_object_counts_bucket",
    "prober_probe_duration_seconds_bucket",
    "container_memory_failures_total",
    "container_memory_failcnt",
    "container_blkio_device_usage_total",
    "container_fs_reads_total",
    "container_fs_writes_total",
    "container_fs_reads_bytes_total",
    "container_fs_writes_bytes_total",
    "container_fs_usage_bytes",
]


def load_rules():
    values = yaml.safe_load(VALUES.read_text())
    rules = values["vmagent"]["spec"].get("globalScrapeMetricRelabelConfigs")
    assert rules, "falta vmagent.spec.globalScrapeMetricRelabelConfigs en values.yaml"
    return rules


def relabel(name, rules):
    """Aplica la cadena de metric_relabel_configs a una serie y devuelve sus labels.

    None = la serie se cae (drop). Semantica: regex de Prometheus totalmente anclado,
    separator ';', etiquetas ausentes cuentan como cadena vacia.
    """
    labels = {"__name__": name, "job": "kubelet", "instance": "10.42.0.1:10250"}
    for rule in rules:
        action = rule.get("action", "replace")
        source = rule.get("sourceLabels") or rule.get("source_labels") or []
        separator = rule.get("separator", ";")
        regex = rule["regex"]
        if isinstance(regex, list):
            regex = "|".join(str(r) for r in regex)
        pattern = re.compile("^(?:%s)$" % regex)
        if action == "labeldrop":
            names = [k for k in (source or [regex]) if pattern.match(k)]
            for k in names:
                labels.pop(k, None)
            if not source:
                for k in [k for k in labels if re.fullmatch(regex, k)]:
                    labels.pop(k)
            continue
        value = separator.join(labels.get(k, "") for k in source)
        match = pattern.match(value)
        if action == "drop":
            if match:
                return None
        elif action == "keep":
            if not match:
                return None
        elif action == "replace":
            if not match:
                continue
            target = rule.get("targetLabel") or rule.get("target_label")
            replacement = rule.get("replacement", "")
            try:
                value_out = match.expand(str(replacement))
            except re.error:
                value_out = str(replacement)
            if target:
                labels[target] = value_out
        elif action == "labelmap":
            for k in list(labels):
                if pattern.match(k):
                    labels[match.expand(str(rule.get("replacement", "$1")))] = labels[k]
    return labels


class TestInfra1600CardinalityDrops(unittest.TestCase):
    def setUp(self):
        self.rules = load_rules()

    def test_consumed_families_survive(self):
        silenced = [n for n in MUST_KEEP if relabel(n, self.rules) is None]
        self.assertEqual(
            silenced, [],
            "el relabel de INFRA-1600 estaria callando series con consumidor: %s" % silenced,
        )

    def test_measured_high_cardinality_families_are_dropped(self):
        kept = [n for n in MUST_DROP if relabel(n, self.rules) is not None]
        self.assertEqual(
            kept, [],
            "estas familias de alta cardinalidad sin consumidor deberian caerse: %s" % kept,
        )

    def test_no_marker_label_reaches_storage(self):
        # Las excepciones se marcan con una etiqueta temporal; si llegara a
        # remote-write anadiria pares etiqueta-valor al indice, que es lo que se combate.
        leftovers = []
        for name in MUST_KEEP + MUST_DROP:
            labels = relabel(name, self.rules)
            if labels and any(k.startswith("infra1600") for k in labels):
                leftovers.append(name)
        self.assertEqual(leftovers, [], "el marcador infra1600_* no se limpia: %s" % leftovers)

    def test_drops_are_scoped_to_the_measured_classes(self):
        # Un drop global mal anclado se lleva por delante el resto del plano (nodos,
        # apps, inferencia). Ningun nombre fuera de las clases medidas debe caer.
        samples = [
            "node_exporter_build_info",
            "kube_pod_info",
            "kubelet_pod_start_duration_seconds_count",
            "vmagent_remotewrite_bytes_sent_total",
            "traefik_service_requests_total",
            "argo_workflow_count",
            "gha_runner_busy",
            "ci_queue_jobs_waiting",
            "frigate_cameras_fps",
            "container_network_transmit_bytes_total",
            "etcd_disk_wal_fsync_duration_seconds_sum",
            "apiserver_request_sli_duration_seconds_sum",
        ]
        self.assertEqual(
            [n for n in samples if relabel(n, self.rules) is None], [],
            "el relabel esta cayendo series fuera de las clases medidas",
        )

    def test_count_and_sum_of_dropped_histograms_are_kept(self):
        # Se caen los buckets (los que multiplican por `le`), no el total ni la suma:
        # los promedios suma/count si se consultan en los dashboards del plano de control.
        for name in [
            "apiserver_request_duration_seconds_count",
            "apiserver_request_duration_seconds_sum",
            "etcd_request_duration_seconds_sum",
            "prober_probe_duration_seconds_count",
            "apiserver_response_sizes_sum",
        ]:
            self.assertIsNotNone(relabel(name, self.rules), "%s no debe caerse" % name)


if __name__ == "__main__":
    unittest.main()

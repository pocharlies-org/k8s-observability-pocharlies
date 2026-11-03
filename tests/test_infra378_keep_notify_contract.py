"""Contract for the cron-job-failed grouping (INFRA-378, per-CronJob since
INFRA-1135) — and its INFRA-912 half.

Pins:

1. The `cron-job-failed` correlation rule groups by [namespace, owner_name] and
   its incident name carries the CronJob, because ops-watch derives the
   Request's `keep-causa` from the sha1 of the incident name: while the name
   only carried [namespace, alertname], every CronJob of a namespace shared one
   cause (measured: keep-causa cron-job-failed:9c99776a1c covered
   architecture-sync, memory-promotion and knowledge-pages; SC-4342). The
   alertname stays in the name so a BrainIngestConsecutiveFailures alert is
   still never absorbed silently into an old CRON incident (incident 9d403a3e
   suppressed every re-alert for 9 days): without owner_name its fingerprint is
   the "none" bucket (rulesengine._calc_rule_fingerprint), never a job's.

2. INFRA-912 (2026-10-17, Dani: «las alertas en Telegram son inútiles»): the
   Telegram notify lanes (`notify-incident`, `notify-incident-critical`,
   `notify-alert-summary`, `incident-summary`) are GONE from keep/values.yaml.
   Nothing in the Keep provisioning talks to Telegram any more; the incident is
   the notification and ops-watch turns it into a Request.
"""

from pathlib import Path
import hashlib
import re
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
VALUES = ROOT / "keep" / "values.yaml"
CORRELATION = ROOT / "keep" / "rules" / "correlation-rules.yaml"


def workflows():
    values = yaml.safe_load(VALUES.read_text())
    return {w["id"]: w for w in values["backend"]["provision"]["workflows"]}


def rule(name):
    rules = yaml.safe_load(CORRELATION.read_text())["rules"]
    for r in rules:
        if r["ruleName"] == name:
            return r
    raise AssertionError(f"rule {name} not found")


# Keep 0.52.1, keep/rulesengine/rulesengine.py (medido en la imagen desplegada):
#   _calc_rule_fingerprint → ",".join of the grouping criteria read TOP-LEVEL from
#     the event; if any is missing, the whole fingerprint collapses to "none".
#   _get_or_create_incident → the name is the template with each {{ var }} replaced
#     by the event's value, "N/A" when the event lacks it (get_value_from_event).
# ops-watch (x86-host-runtime, fuente_keep): causa = sha1(nombre sin el prefijo
# «CRON-<n> - »)[:10]. These two mirrors are what make the cause per-CronJob.
KEEP_NUM_RE = re.compile(r"^[A-Z][A-Z0-9]*-\d+\s*[-–]\s*")


def fingerprint(alert, criteria):
    values = [alert.get(c) for c in criteria]
    return "none" if any(v is None for v in values) else ",".join(values)


def incident_name(template, alert):
    return re.sub(r"\{\{\s*([^}]+?)\s*\}\}",
                  lambda m: str(alert.get(m.group(1).strip(), "N/A")), template)


def causa(name):
    return hashlib.sha1(KEEP_NUM_RE.sub("", name).encode()).hexdigest()[:10]


def cronjob_alert(ns, job):
    # owner_name llega top-level (medido en un alert K8sCronJobFailed de Keep:
    # kube_job_owner lo expone y el provider lo aplana).
    return {"alertname": "K8sCronJobFailed", "namespace": ns, "owner_name": job}


class CronJobFailedGroupingTest(unittest.TestCase):
    def test_groups_by_namespace_and_owner_name(self):
        # INFRA-1135: la clave de causa es por CronJob, no por namespace.
        self.assertEqual(rule("cron-job-failed")["groupingCriteria"], ["namespace", "owner_name"])

    def test_incident_name_carries_alertname_namespace_and_owner_name(self):
        template = rule("cron-job-failed")["incidentNameTemplate"]
        for var in ("{{ alertname }}", "{{ namespace }}", "{{ owner_name }}"):
            self.assertIn(var, template)
        # El nombre es la causa: sin números volátiles en la plantilla (el sufijo
        # del Job, job_name, NUNCA va aquí; owner_name es el CronJob, estable).
        self.assertFalse(any(ch.isdigit() for ch in template), template)

    def test_two_jobs_of_one_namespace_get_distinct_causas(self):
        # El criterio de éxito de INFRA-1135, con la fórmula real de Keep y de
        # ops-watch: dos CronJobs del mismo namespace que fallen en la misma
        # ventana no pueden compartir keep-causa.
        rule_ = rule("cron-job-failed")
        criteria = rule_["groupingCriteria"]
        a = cronjob_alert("skirmshop-brain-prod", "memory-promotion")
        b = cronjob_alert("skirmshop-brain-prod", "knowledge-pages")
        self.assertNotEqual(fingerprint(a, criteria), fingerprint(b, criteria))
        na, nb = (incident_name(rule_["incidentNameTemplate"], x) for x in (a, b))
        self.assertNotEqual(na, nb)
        self.assertNotEqual(causa(f"CRON-1 - {na}"), causa(f"CRON-2 - {nb}"))

    def test_brain_ingest_never_shares_a_jobs_fingerprint(self):
        # BrainIngestConsecutiveFailures no lleva owner_name: su huella es el
        # cubo «none» (comportamiento medido de Keep), nunca la de un CronJob ⇒
        # sigue abriendo su propio incidente (el motivo de INFRA-378).
        criteria = rule("cron-job-failed")["groupingCriteria"]
        brain = {"alertname": "BrainIngestConsecutiveFailures", "namespace": "skirmshop-brain-prod"}
        self.assertEqual(fingerprint(brain, criteria), "none")
        self.assertNotEqual(fingerprint(brain, criteria),
                            fingerprint(cronjob_alert("skirmshop-brain-prod", "memory-promotion"),
                                        criteria))

    def test_rule_still_covers_both_alerts(self):
        cel = rule("cron-job-failed")["celQuery"]
        self.assertIn("K8sCronJobFailed", cel)
        self.assertIn("BrainIngestConsecutiveFailures", cel)


class TelegramNotifyLanesRetiredTest(unittest.TestCase):
    """INFRA-912: los workflows de aviso por Telegram no deben volver."""

    def test_notify_workflows_are_gone(self):
        wf = workflows()
        for wf_id in ("notify-incident", "notify-incident-critical",
                      "notify-alert-summary", "incident-summary"):
            self.assertNotIn(wf_id, wf)

    def test_parsed_values_have_no_telegram_data(self):
        # Los comentarios históricos pueden nombrar Telegram; el DATO no.
        import json
        data = json.dumps(yaml.safe_load(VALUES.read_text()), ensure_ascii=False)
        self.assertNotIn("telegram", data.lower())
        self.assertNotIn("-1004409526898", data)


if __name__ == "__main__":
    unittest.main()

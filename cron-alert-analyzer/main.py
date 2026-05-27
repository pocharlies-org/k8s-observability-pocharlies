"""
cron-alert-analyzer — Alertmanager webhook receiver that grabs the failed pod's
logs (via k8s API), runs an LLM root-cause analysis (litellm → vllm-122b), and
posts a HTML report to the Telegram "Crons" topic with a deep-link to the
dashboard.

Pipeline:
  AlertmanagerConfig route (alertname=K8sCronJobFailed) → POST /alert →
    background: fetch pod logs → litellm chat → Telegram sendMessage
"""

import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from html import escape
from typing import Optional

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from kubernetes import client as k8s_client
from kubernetes import config as k8s_config

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
log = logging.getLogger("cron-alert-analyzer")

# --- env -----------------------------------------------------------------
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
TELEGRAM_THREAD_ID = os.environ["TELEGRAM_THREAD_ID"]
LITELLM_URL = os.environ.get("LITELLM_URL", "http://litellm.litellm.svc.cluster.local:4000")
LITELLM_MODEL = os.environ.get("LITELLM_MODEL", "vllm-122b")
LITELLM_API_KEY = os.environ["LITELLM_API_KEY"]
DASHBOARD_BASE = os.environ.get("DASHBOARD_BASE", "https://dgx.e-dani.com/crontab")
LOG_TAIL_LINES = int(os.environ.get("LOG_TAIL_LINES", "200"))
LLM_MAX_LOG_CHARS = int(os.environ.get("LLM_MAX_LOG_CHARS", "12000"))
LLM_TIMEOUT_S = float(os.environ.get("LLM_TIMEOUT_S", "120"))
ENABLE_FIX_BUTTON = os.environ.get("ENABLE_FIX_BUTTON", "true").lower() in {"1", "true", "yes", "on"}

# --- k8s clients ---------------------------------------------------------
try:
    k8s_config.load_incluster_config()
except k8s_config.ConfigException:
    k8s_config.load_kube_config()
CORE = k8s_client.CoreV1Api()
BATCH = k8s_client.BatchV1Api()

app = FastAPI(title="cron-alert-analyzer")


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.post("/alert")
async def alert(req: Request, background_tasks: BackgroundTasks):
    payload = await req.json()
    alerts = payload.get("alerts", []) or []
    # A grouped webhook can carry several failed Jobs of the SAME CronJob.
    # Collapse them by (namespace, owner_name) and keep only the most recent
    # failure (latest startsAt) so one CronJob → one report, not N.
    groups: dict[tuple[str, str], dict] = {}
    for a in alerts:
        if a.get("status") != "firing":
            continue
        labels = a.get("labels", {}) or {}
        if labels.get("alertname") != "K8sCronJobFailed":
            continue
        key = (labels.get("namespace", ""), labels.get("owner_name") or labels.get("cronjob", ""))
        cur = groups.get(key)
        if cur is None or a.get("startsAt", "") >= cur.get("startsAt", ""):
            groups[key] = a
    for a in groups.values():
        background_tasks.add_task(handle_alert, a)
    log.info("received webhook: %d alerts, %d cronjob(s) handled", len(alerts), len(groups))
    return {"received": len(alerts), "handled": len(groups)}


async def handle_alert(alert_data: dict):
    labels = alert_data.get("labels", {}) or {}
    annotations = alert_data.get("annotations", {}) or {}
    ns = labels.get("namespace", "")
    job_name = labels.get("job_name", "")
    cronjob = labels.get("owner_name") or labels.get("cronjob", "")
    started = alert_data.get("startsAt", "")

    if not (ns and job_name):
        log.warning("alert missing ns/job_name, skipping: %s", labels)
        return

    log.info("processing failure: ns=%s cronjob=%s job=%s", ns, cronjob, job_name)
    pod_name, container, logs_text, exit_code = read_logs_for_job(ns, job_name)
    deep_link = build_deep_link(ns, cronjob, job_name)
    analysis = await call_llm(ns, cronjob, job_name, pod_name, exit_code, logs_text, annotations)
    message = format_telegram_message(
        ns=ns,
        cronjob=cronjob,
        job_name=job_name,
        pod_name=pod_name,
        exit_code=exit_code,
        started=started,
        annotations=annotations,
        analysis=analysis,
        logs_tail=logs_tail_for_message(logs_text),
        deep_link=deep_link,
    )
    reply_markup = build_reply_markup(
        alert_id=short_alert_id(ns, cronjob, job_name),
        exit_code=exit_code,
        analysis=analysis,
    )
    await send_telegram(message, reply_markup=reply_markup)


def read_logs_for_job(ns: str, job_name: str) -> tuple[str, str, str, Optional[int]]:
    """Find the most recent (failed) pod for the Job and return (pod, container, logs, exit_code)."""
    pod_name = ""
    container = ""
    exit_code: Optional[int] = None
    try:
        pods = CORE.list_namespaced_pod(
            namespace=ns, label_selector=f"job-name={job_name}"
        ).items
    except Exception as exc:
        log.exception("list_pods failed for %s/%s: %s", ns, job_name, exc)
        return pod_name, container, f"(failed to list pods: {exc})", exit_code

    if not pods:
        return pod_name, container, f"(no pods found for job {ns}/{job_name})", exit_code

    # Prefer the newest pod that actually terminated non-zero. Jobs with
    # retries often have both failed and successful pods; choosing "latest"
    # made the alert look like an exit=0 failure.
    pods.sort(key=_pod_selection_key, reverse=True)
    pod = pods[0]
    pod_name = pod.metadata.name
    container, exit_code = _terminated_container(pod)
    if not container and pod.spec.containers:
        container = pod.spec.containers[0].name

    try:
        logs_text = CORE.read_namespaced_pod_log(
            name=pod_name,
            namespace=ns,
            container=container or None,
            tail_lines=LOG_TAIL_LINES,
            timestamps=True,
        ) or ""
    except Exception as exc:
        log.exception("read_pod_log failed for %s/%s: %s", ns, pod_name, exc)
        logs_text = f"(failed to read pod log: {exc})"
    return pod_name, container, logs_text, exit_code


def _pod_selection_key(pod) -> tuple[int, datetime]:
    _, exit_code = _terminated_container(pod)
    failed = exit_code is not None and exit_code != 0
    created = pod.metadata.creation_timestamp or datetime.min.replace(tzinfo=timezone.utc)
    return (1 if failed else 0, created)


def _terminated_container(pod) -> tuple[str, Optional[int]]:
    for c in (pod.status.container_statuses or []):
        if c.state and c.state.terminated:
            return c.name, c.state.terminated.exit_code
    return "", None


async def call_llm(
    ns: str, cronjob: str, job_name: str, pod: str, exit_code: Optional[int],
    logs: str, annotations: dict,
) -> str:
    snippet = logs[-LLM_MAX_LOG_CHARS:] if len(logs) > LLM_MAX_LOG_CHARS else logs
    status_hint = (
        "El contenedor seleccionado terminó con exit code 0. Si los logs no muestran excepción, "
        "trata esto como un falso positivo o una regla de monitorización mal calibrada."
        if exit_code == 0
        else "El contenedor seleccionado terminó con exit code distinto de 0 o desconocido."
    )
    user_prompt = f"""Un CronJob de Kubernetes ha disparado una alerta. Analiza los logs y devuelve un reporte accionable.

CronJob: {ns}/{cronjob or '(desconocido)'}
Job:     {job_name}
Pod:     {pod or '(desconocido)'}
Exit:    {exit_code if exit_code is not None else '(desconocido)'}
Señal de estado: {status_hint}
Anotaciones: {annotations.get('summary','')}  {annotations.get('description','')}

--- LOGS (últimas {LOG_TAIL_LINES} líneas, hasta {LLM_MAX_LOG_CHARS} caracteres) ---
{snippet}
--- FIN LOGS ---

Devuelve EN ESPAÑOL, con esta estructura y SIN markdown ni código fences:

CAUSA RAÍZ
<2-4 frases, qué falló exactamente y por qué>

EVIDENCIA EN LOGS
<cita 1-3 líneas concretas que demuestran la causa>

ACCIÓN RECOMENDADA
<1-3 viñetas con qué tocar/verificar/cambiar para resolverlo>

SEVERIDAD
<una palabra: bajo | medio | alto | crítico>

Sé conciso. Si Exit=0 y el log solo dice que no había trabajo pendiente, no inventes un fallo de negocio:
la causa raíz es la alerta/regla, y la acción recomendada es corregir el monitor."""

    sys_prompt = (
        "Eres un SRE senior especializado en Kubernetes. Analizas logs de CronJobs fallidos "
        "y produces diagnósticos concisos y accionables. No inventas. Si no hay evidencia "
        "suficiente, lo dices explícitamente."
    )

    body = {
        "model": LITELLM_MODEL,
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 800,
    }
    headers = {"Authorization": f"Bearer {LITELLM_API_KEY}"}

    try:
        async with httpx.AsyncClient(timeout=LLM_TIMEOUT_S) as cx:
            r = await cx.post(f"{LITELLM_URL}/v1/chat/completions", json=body, headers=headers)
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        log.exception("LLM call failed: %s", exc)
        return f"(análisis LLM no disponible: {exc})"


def build_deep_link(ns: str, cronjob: str, job_name: str) -> str:
    from urllib.parse import urlencode
    qs = urlencode({"ns": ns, "cronjob": cronjob, "job": job_name})
    return f"{DASHBOARD_BASE}?{qs}"


def logs_tail_for_message(logs_text: str, max_lines: int = 15, max_chars: int = 1500) -> str:
    lines = [ln for ln in (logs_text or "").splitlines() if ln.strip()]
    tail = lines[-max_lines:]
    out = "\n".join(tail)
    if len(out) > max_chars:
        out = out[-max_chars:]
        nl = out.find("\n")
        if nl > 0:
            out = out[nl + 1:]
    return out or "(sin logs)"


_HTML_TAG = re.compile(r"<[^>]+>")


def format_telegram_message(
    *, ns: str, cronjob: str, job_name: str, pod_name: str, exit_code: Optional[int],
    started: str, annotations: dict, analysis: str, logs_tail: str, deep_link: str,
) -> str:
    when = ""
    if started:
        try:
            dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
            when = dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        except ValueError:
            when = started

    summary = annotations.get("summary", "")
    clean_summary = extract_clean_summary(analysis, exit_code)
    icon = "✅" if exit_code == 0 else "❌"
    title = f"{icon} <b>CronJob alertado</b>: <code>{escape(ns)}/{escape(cronjob or job_name)}</code>"
    meta = [
        f"<b>Job:</b> <code>{escape(job_name)}</code>",
        f"<b>Pod:</b> <code>{escape(pod_name or '(desconocido)')}</code>",
        f"<b>Exit code:</b> <code>{exit_code if exit_code is not None else 'n/a'}</code>",
    ]
    if when:
        meta.append(f"<b>Cuándo:</b> {escape(when)}")
    if summary:
        meta.append(f"<i>{escape(summary)}</i>")

    analysis_block = escape(analysis or "(sin análisis)")
    logs_block = f"<pre>{escape(logs_tail)}</pre>" if logs_tail else ""

    link_block = f'<a href="{escape(deep_link)}">🔗 ver logs en dashboard</a>'

    parts = [
        title,
        f"<b>Resumen:</b> {escape(clean_summary)}",
        "",
        "<b>Datos</b>",
        "\n".join(meta),
        "",
        f"<b>Análisis ({escape(LITELLM_MODEL)})</b>",
        analysis_block,
    ]
    if logs_block:
        parts += ["", "<b>Logs (últimas líneas)</b>", logs_block]
    parts += ["", link_block]
    msg = "\n".join(parts)
    if len(msg) > 4000:
        keep = 4000 - len(link_block) - 200
        msg = msg[:keep] + "\n... <i>(truncado)</i>\n" + link_block
    return msg


def extract_clean_summary(analysis: str, exit_code: Optional[int]) -> str:
    if exit_code == 0:
        return "El Job terminó correctamente; si no hay errores en logs, la alerta es probablemente un falso positivo."

    lines = [ln.strip() for ln in (analysis or "").splitlines() if ln.strip()]
    skip = {"CAUSA RAÍZ", "CAUSA RAIZ", "EVIDENCIA EN LOGS", "ACCIÓN RECOMENDADA", "ACCION RECOMENDADA", "SEVERIDAD"}
    for line in lines:
        if line.upper().rstrip(":") in skip:
            continue
        return _HTML_TAG.sub("", line)[:220]
    return "El CronJob necesita revisión; no hay suficiente detalle en el análisis."


def short_alert_id(ns: str, cronjob: str, job_name: str) -> str:
    raw = f"{ns}/{cronjob or '-'}:{job_name}".encode()
    return hashlib.sha1(raw).hexdigest()[:10]


def build_reply_markup(
    *, alert_id: str, exit_code: Optional[int], analysis: str,
) -> dict[str, list[list[dict[str, str]]]]:
    keyboard: list[list[dict[str, str]]] = [
        [{"text": "🧠 Analizar más", "callback_data": f"alert:openclaw:{alert_id}"}],
    ]
    if ENABLE_FIX_BUTTON and should_offer_fix(exit_code, analysis):
        keyboard.append([{"text": "🛠 Arreglarlo", "callback_data": f"cron:fix:{alert_id}"}])
    keyboard.append([{"text": "🗑 Descartar", "callback_data": f"alert:discard:{alert_id}"}])
    return {"inline_keyboard": keyboard}


def should_offer_fix(exit_code: Optional[int], analysis: str) -> bool:
    text = (analysis or "").lower()
    if exit_code == 0 and any(
        phrase in text
        for phrase in ("falso positivo", "no open picklists", "sin trabajo pendiente", "no había trabajo")
    ):
        return False
    if any(phrase in text for phrase in ("no requiere acción", "no hace falta", "sin acción")):
        return False
    return exit_code not in (None, 0) or "acción recomendada" in text or "accion recomendada" in text


async def send_telegram(text: str, reply_markup: Optional[dict] = None) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "message_thread_id": TELEGRAM_THREAD_ID,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
        "text": text,
    }
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
    try:
        async with httpx.AsyncClient(timeout=30) as cx:
            r = await cx.post(url, data=data)
            if r.status_code != 200 or not r.json().get("ok"):
                log.error("telegram error: %s %s", r.status_code, r.text[:300])
            else:
                log.info("telegram message sent (thread=%s)", TELEGRAM_THREAD_ID)
    except Exception as exc:
        log.exception("send_telegram failed: %s", exc)

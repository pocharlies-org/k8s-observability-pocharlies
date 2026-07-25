#!/usr/bin/env python3
"""Simulador del árbol de rutas de Alertmanager + generador de la matriz de routing.

Replica la semántica de matching de `prometheus/alertmanager` (dispatch.Route.Match)
sobre el `VMAlertmanagerConfig` del clúster, para poder responder sin adivinar
"¿dónde acaba esta alerta?" — pregunta que el árbol anidado esconde.

Semántica replicada:
  - se recorren las rutas hijas en orden; una hija encaja si TODOS sus matchers encajan
  - al encajar una hija se recursa en ella; si `continue` != true se dejan de mirar hermanas
  - si NINGUNA hija encaja, la alerta se entrega al receiver de ESTA ruta

Esa última regla es la que convierte el árbol en un allowlist cuando la hija final es
`severity = warning -> blackhole`.

Uso:
  # qué pasa con las alertas disparadas ahora
  ./alert_routing.py live

  # regenerar docs/alert-routing-matrix.md a partir de todas las VMRules
  ./alert_routing.py matrix

Requiere: kubectl con contexto al clúster, PyYAML.
"""
from __future__ import annotations

import argparse
import collections
import datetime
import json
import pathlib
import re
import subprocess
import sys
import urllib.parse

import yaml

REPO = pathlib.Path(__file__).resolve().parent.parent
AM_NAMESPACE = "monitoring"
AM_CONFIG = "synapse-webhook"
AM_POD = "vmalertmanager-vm-victoria-metrics-k8s-stack-0"

# Normalización de severidad que aplica la mapping rule de Keep.
# `page` -> critical es deliberado: hoy esas alertas no despiertan a nadie pese al nombre.
SEV_NORM = {
    "critical": "critical",
    "page": "critical",
    "warning": "warning",
    "warn": "warning",
    "info": "info",
    "none": "info",
    "": "info",
}
KEEP_DEST = {
    "critical": "Keep → Telegram (sin tema) + Incident + Aurora",
    "warning": "Keep → Telegram tema 34494 + Incident + Aurora",
    "info": "Keep → sólo registro (sin notificación)",
}
# No deben notificar nunca, pero sí llegar a Keep: son la señal de que la ingesta vive.
HEARTBEAT_ALERTS = {"Watchdog", "InfoInhibitor"}

SUBSYSTEMS = (
    "Alertmanager", "Argo", "Blackbox", "Cnpg", "CronAlertAnalyzer", "DGX", "Dgx",
    "Harbor", "ImageStudio", "Instagram", "Keycloak", "Krea2", "Kubernetes", "Kube",
    "LabelGeneration", "Labels", "LibrePlay", "Loki", "Longhorn", "MCP", "Node", "OVH",
    "Postgres", "Rabbitmq", "ScrapePool", "Scrape", "Sii", "Synapse", "Target",
    "TooMany", "Tracking", "Request", "Velero",
)


# --------------------------------------------------------------------------- matching

def parse_matcher(m: str) -> tuple[str, str, str]:
    """'label =~ "a|b"' -> ('label', '=~', 'a|b')"""
    for op in ("=~", "!~", "!=", "="):
        idx = m.find(op)
        if idx == -1:
            continue
        if op == "=" and idx > 0 and m[idx - 1] in "!=~":
            continue  # no partir '!=' ni '=~' por su '='
        label = m[:idx].strip()
        value = m[idx + len(op):].strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        return label, op, value
    raise ValueError(f"matcher no parseable: {m!r}")


def matcher_hits(matcher: str, labels: dict[str, str]) -> bool:
    label, op, value = parse_matcher(matcher)
    actual = labels.get(label, "")
    if op == "=":
        return actual == value
    if op == "!=":
        return actual != value
    if op == "=~":
        return re.fullmatch(value, actual) is not None
    if op == "!~":
        return re.fullmatch(value, actual) is None
    raise ValueError(op)


def route_hits(route: dict, labels: dict[str, str]) -> bool:
    return all(matcher_hits(m, labels) for m in (route.get("matchers") or []))


def resolve(route: dict, labels: dict[str, str]) -> list[str]:
    """Receivers a los que Alertmanager entregaría esta alerta."""
    out: list[str] = []
    for child in route.get("routes") or []:
        if not route_hits(child, labels):
            continue
        out.extend(resolve(child, labels))
        if not child.get("continue"):
            break
    return out or [route["receiver"]]


def dest_label(receiver: str) -> str:
    if receiver == "blackhole":
        return "BLACKHOLE"
    for needle, label in (
        ("emergency-telegram", "telegram-emergencia"),
        ("labels-deep-monitor", "telegram-labels-deep"),
        ("cron-alert-analyzer", "cron-analyzer"),
        ("synapse-alertmanager", "synapse-webhook"),
    ):
        if needle in receiver:
            return label
    return receiver


def destination(root: dict, alertname: str, severity: str, namespace: str = "x") -> str:
    labels = {"alertname": alertname, "severity": severity, "namespace": namespace}
    return " + ".join(sorted({dest_label(r) for r in resolve(root, labels)}))


# ------------------------------------------------------------------------------ datos

def kubectl(*args: str) -> str:
    return subprocess.run(
        ["kubectl", *args], check=True, capture_output=True, text=True
    ).stdout


def load_route() -> dict:
    cr = yaml.safe_load(kubectl("-n", AM_NAMESPACE, "get", "vmalertmanagerconfig", AM_CONFIG, "-o", "yaml"))
    return cr["spec"]["route"]


def load_firing() -> list[dict]:
    raw = kubectl("-n", AM_NAMESPACE, "exec", AM_POD, "-c", "alertmanager", "--",
                  "wget", "-qO-", "http://127.0.0.1:9093/api/v2/alerts")
    return json.loads(raw)


def load_defined() -> list[tuple[str, str]]:
    """(alertname, severity) de todas las VMRules del clúster."""
    d = json.loads(kubectl("get", "vmrule", "-A", "-o", "json"))
    found = set()
    for item in d["items"]:
        for grp in item["spec"].get("groups", []):
            for rule in grp.get("rules", []):
                if "alert" in rule:
                    found.add((rule["alert"], (rule.get("labels") or {}).get("severity", "")))
    return sorted(found)


def subsystem(name: str) -> str:
    for prefix in SUBSYSTEMS:
        if name.startswith(prefix):
            return prefix
    return "otros"


# --------------------------------------------------------------------------- comandos

def cmd_live(_args) -> None:
    root, alerts = load_route(), load_firing()
    seen: dict[tuple[str, str, str], list] = {}
    for a in alerts:
        lb = a["labels"]
        key = (lb.get("alertname", ""), lb.get("severity", ""), lb.get("namespace", "-"))
        seen.setdefault(key, [0, destination(root, *key[:2], key[2])])
        seen[key][0] += 1

    width = max((len(k[0]) for k in seen), default=20)
    print(f"{'#':>3}  {'alertname':<{width}}  {'sev':<9}  {'namespace':<14}  destino")
    print("-" * (width + 45))
    for (name, sev, ns), (count, dst) in sorted(seen.items(), key=lambda kv: (kv[1][1], kv[0][0])):
        print(f"{count:>3}  {name:<{width}}  {sev:<9}  {ns:<14}  {dst}")

    dropped = [(k, v) for k, v in seen.items() if "BLACKHOLE" in v[1] and k[0] not in HEARTBEAT_ALERTS]
    print(f"\n{len(alerts)} instancias / {len(seen)} series")
    print(f"DESCARTADAS (excluyendo heartbeats): {sum(v[0] for _, v in dropped)} instancias / {len(dropped)} series")


def cmd_matrix(_args) -> None:
    root = load_route()
    defined = load_defined()
    firing = collections.Counter(a["labels"].get("alertname") for a in load_firing())
    today = datetime.date.today().isoformat()

    rows = [{
        "name": name,
        "sev": sev or "<none>",
        "norm": SEV_NORM[sev],
        "today": destination(root, name, sev),
        "firing": firing.get(name, 0),
    } for name, sev in defined]

    out: list[str] = []
    w = out.append
    w("# Matriz de routing de alertas — estado actual y destino en Keep")
    w("")
    w(f"Generado el {today} por `scripts/alert_routing.py matrix` desde el clúster")
    w(f"`x86-k3s`, simulando el matching de Alertmanager sobre")
    w(f"`VMAlertmanagerConfig {AM_NAMESPACE}/{AM_CONFIG}`.")
    w("")
    w("**No editar a mano.** Regenerar con el script tras cualquier cambio de rutas o reglas.")
    w("")
    w("**Semántica que hace falta entender:** Alertmanager entrega al receiver propio de")
    w("una ruta sólo cuando *ninguna hija encaja*. Como la última hija del árbol es")
    w("`severity = warning → blackhole`, el árbol funciona como **allowlist**: un warning")
    w("llega a algún sitio únicamente si su `alertname` aparece listado antes.")
    w("")

    w("## Resumen")
    w("")
    by_today = collections.Counter(r["today"] for r in rows)
    w("| destino hoy | series | % |")
    w("|---|---:|---:|")
    for d, n in by_today.most_common():
        name = "**BLACKHOLE (se descarta)**" if d == "BLACKHOLE" else d
        w(f"| {name} | {n} | {round(100 * n / len(rows))}% |")
    w(f"| **TOTAL** | **{len(rows)}** | 100% |")
    w("")

    w("### Taxonomía de severidad realmente emitida")
    w("")
    handled = {
        "critical": "sí — `severity = critical`",
        "warning": "sí — `severity = warning` → blackhole",
    }
    w("| valor | series | ¿lo contempla el árbol? |")
    w("|---|---:|---|")
    for s, n in collections.Counter(r["sev"] for r in rows).most_common():
        w(f"| `{s}` | {n} | {handled.get(s, '**no** — cae al receiver raíz')} |")
    w("")
    w("Seis valores distintos, de los que el árbol sólo contempla dos. `page` y `warn` no")
    w("son typos aislados: son la convención de subsistemas enteros (Labels/Valkey,")
    w("LibrePlay, Tracking) que nunca se alineó con el resto.")
    w("")

    w("## Hallazgos accionables")
    w("")
    bh = [r for r in rows if r["today"] == "BLACKHOLE"]
    bh_real = [r for r in bh if r["name"] not in HEARTBEAT_ALERTS]
    bh_firing = [r for r in bh_real if r["firing"]]
    w(f"1. **{len(bh)} series ({round(100 * len(bh) / len(rows))}%) no pueden notificar a nadie.**")
    w(f"   Descontando los heartbeats ({', '.join(sorted(HEARTBEAT_ALERTS))}), son {len(bh_real)}")
    w(f"   series ciegas; {len(bh_firing)} de ellas están disparadas ahora mismo")
    w(f"   ({sum(r['firing'] for r in bh_firing)} instancias activas).")
    w("   `Watchdog` e `InfoInhibitor` deben seguir sin notificar, pero **sí** tienen que")
    w("   llegar a Keep: son la señal de que la ingesta sigue viva.")
    w("")
    page = sorted(r["name"] for r in rows if r["sev"] == "page")
    w(f"2. **Las {len(page)} alertas `severity: page` no llegan a Telegram.** `page` es la")
    w("   convención más urgente del repo, y hoy salen sólo por el webhook de Synapse:")
    for name in page:
        w(f"   - `{name}`")
    w("")
    warn = sorted(r["name"] for r in rows if r["sev"] == "warn")
    w(f"3. **Las {len(warn)} alertas `severity: warn` esquivan el blackhole** y llegan a")
    w("   Synapse. Inconsistente, pero al menos visibles — y por eso hay que decidirlas una")
    w("   a una al normalizar `warn → warning`: normalizadas sin criterio pasan de visibles")
    w("   a candidatas al ruido de fondo.")
    for name in warn:
        w(f"   - `{name}`")
    w("")

    w("## Destino en Keep")
    w("")
    w("Normalización que aplica la mapping rule de Keep:")
    w("")
    w("| severidad emitida | → normalizada | destino |")
    w("|---|---|---|")
    for src in ("critical", "page", "warning", "warn", "info", "none"):
        w(f"| `{src}` | `{SEV_NORM[src]}` | {KEEP_DEST[SEV_NORM[src]]} |")
    w("")
    w("`page → critical` es un cambio de comportamiento deliberado: hoy esas alertas no")
    w("despiertan a nadie pese a llamarse `page`.")
    w("")

    w("## Matriz completa")
    w("")
    w("`firing` = instancias activas en el momento de generar. Agrupado por subsistema.")
    w("")
    groups: dict[str, list[dict]] = collections.defaultdict(list)
    for r in rows:
        groups[subsystem(r["name"])].append(r)
    for g in sorted(groups):
        items = sorted(groups[g], key=lambda r: r["name"])
        blind = sum(1 for r in items if r["today"] == "BLACKHOLE")
        suffix = f" — {blind} ciegas" if blind else ""
        w(f"### {g} ({len(items)}{suffix})")
        w("")
        w("| alertname | sev | destino hoy | firing |")
        w("|---|---|---|---:|")
        for r in items:
            d = "**BLACKHOLE**" if r["today"] == "BLACKHOLE" else r["today"]
            w(f"| `{r['name']}` | `{r['sev']}` | {d} | {r['firing'] or ''} |")
        w("")

    target = REPO / "docs" / "alert-routing-matrix.md"
    target.parent.mkdir(exist_ok=True)
    target.write_text("\n".join(out) + "\n")
    print(f"{target.relative_to(REPO)}: {len(rows)} series, {len(bh)} en blackhole ({len(bh_real)} ciegas reales)")


def cmd_chronic(args) -> None:
    """Mide qué alertas llevan disparadas tanto tiempo que no son incidentes.

    Alimenta la lista `chronic:` de keep/rules/correlation-rules.yaml. El umbral
    por defecto (20% de los últimos 7 días) es un juicio, no una constante
    sagrada: por debajo hay alertas que van y vienen, por encima hay cosas que
    llevan roto tanto que tratarlas como incidente vacía el concepto.
    """
    window_days = 7
    query = f'sum by (alertname) (count_over_time(ALERTS{{alertstate="firing"}}[{window_days}d]))'
    raw = kubectl(
        "-n", AM_NAMESPACE, "exec", AM_POD, "-c", "alertmanager", "--", "wget", "-qO-",
        "http://vmsingle-vm-victoria-metrics-k8s-stack.monitoring.svc.cluster.local:8428"
        f"/api/v1/query?query={urllib.parse.quote(query)}",
    )
    # vmagent scrapea cada 30s -> 2 muestras/min es el 100% de la ventana.
    samples_full = window_days * 24 * 60 * 2
    rows = []
    for item in json.loads(raw)["data"]["result"]:
        name = item["metric"].get("alertname")
        if not name or name in HEARTBEAT_ALERTS:
            continue
        rows.append((100 * float(item["value"][1]) / samples_full, name))

    rows.sort(reverse=True)
    print(f"% del tiempo disparada en los últimos {window_days}d (>100% = varias instancias)\n")
    for pct, name in rows:
        if pct < 1:
            continue
        mark = "  <- crónica" if pct >= args.threshold else ""
        print(f"  {name:<44} {pct:>6.0f}%{mark}")

    chronic = [n for pct, n in rows if pct >= args.threshold]
    print(f"\n{len(chronic)} por encima del {args.threshold}%. Para el YAML:\n")
    for name in sorted(chronic):
        pct = next(p for p, n in rows if n == name)
        print(f"  - {name:<38} # {pct:>4.0f}%")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("live", help="destino de las alertas disparadas ahora mismo").set_defaults(fn=cmd_live)
    sub.add_parser("matrix", help="regenerar docs/alert-routing-matrix.md").set_defaults(fn=cmd_matrix)
    chronic = sub.add_parser("chronic", help="medir alertas crónicas para la lista de deuda")
    chronic.add_argument("--threshold", type=float, default=20.0, help="%% mínimo (default 20)")
    chronic.set_defaults(fn=cmd_chronic)
    args = p.parse_args()
    try:
        args.fn(args)
    except subprocess.CalledProcessError as e:
        print(f"kubectl falló: {e.stderr.strip()}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

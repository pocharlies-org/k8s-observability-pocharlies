#!/usr/bin/env python3
"""Comprueba que el criterio de notificación de Keep no silencia nada que hoy suene.

El cutover a Keep cambia el criterio de "el árbol de rutas de Alertmanager decide"
a "una regla de correlación decide". Este script compara los dos y FALLA si alguna
serie que produce notificación con el árbol antiguo dejaría de producirla con las
reglas nuevas. Sirve de red para el acoplamiento manual entre la lista de
exclusión de `critical-safety-net` y las reglas de dominio: Keep no tiene
prioridades entre reglas, así que ese acoplamiento no se valida solo.

Uso:
    ./verify-notification-coverage.py                # contra el árbol vivo
    ./verify-notification-coverage.py ruta/al/viejo.yaml

Salida 0 = ninguna regresión. Salida 1 = hay series que se quedarían mudas.

Requiere: kubectl con contexto al clúster, PyYAML.
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from alert_routing import (  # noqa: E402
    SEV_NORM,
    load_defined,
    load_route,
    resolve,
)

REPO = pathlib.Path(__file__).resolve().parent.parent
RULES = REPO / "keep" / "rules" / "correlation-rules.yaml"

# Cómo mapea Keep la severidad al ingerir (keep/providers/prometheus_provider.py).
# Cualquier valor ausente cae a "info" — eso es lo que hace que `page` y `warn`
# no puedan usarse para decidir cobertura.
KEEP_SEVERITIES = {
    "critical": "critical", "error": "high", "high": "high",
    "warning": "warning", "medium": "warning", "info": "info", "low": "low",
}

# Series que a propósito NO notifican tras el cutover, con su motivo. Cada
# entrada aquí es una decisión consciente, no un descuido: si el script se queja
# de algo nuevo, o le das regla o lo añades aquí explicando por qué.
SILENCIO_DELIBERADO = {
    "Watchdog": "heartbeat de Alertmanager; se ingiere para detectar silencio",
    "InfoInhibitor": "alerta auxiliar de inhibición, nunca fue accionable",
    "CPUThrottlingHigh": "severity info: ruido de fondo conocido",
    "KubeQuotaAlmostFull": "severity info: informativa por diseño",
    "KubeQuotaFullyUsed": "severity info: informativa por diseño",
    "KubeletTooManyPods": "severity info: informativa por diseño",
    "RecordingRulesNoData": "severity info: informativa por diseño",
    "KubeJobFailed": "descartada hoy a propósito para no duplicar K8sCronJobFailed",
}


def cel_matches(cel: str, name: str, raw_severity: str) -> bool:
    """Evalúa los subconjuntos de CEL que usan estas reglas.

    Traducción a Python de: name in [...], name.startsWith("x"), severity == "x",
    labels.severity == "x", && || !(). NO es un motor CEL general — si una regla
    empieza a usar construcciones nuevas, este script hay que ampliarlo, y es
    mejor que se note aquí que en producción.
    """
    allowed = re.compile(
        r'^[\s()!]*$|^[\s]*name[\s]*(in|==|\.startsWith)|^[\s]*severity[\s]*==|'
        r'^[\s]*labels\.severity[\s]*=='
    )
    del allowed  # documenta la intención; la validación real es el except de abajo

    py = cel.replace("||", " or ").replace("&&", " and ").replace("!(", " not (")
    py = re.sub(r"name\.startsWith\(", "name.startswith(", py)
    py = re.sub(r"\blabels\.severity\b", "sev_raw", py)
    py = re.sub(r"(?<!_)\bseverity\b", "sev_norm", py)
    ctx = {
        "name": name,
        "sev_raw": raw_severity,
        "sev_norm": KEEP_SEVERITIES.get(raw_severity, "info"),
    }
    try:
        return bool(eval(py, {"__builtins__": {}}, ctx))
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(
            f"No se pudo evaluar el CEL:\n  {cel}\n  -> {exc}\n"
            "Amplía cel_matches() para la construcción nueva."
        )


def compose(spec: dict) -> list[dict]:
    """Réplica de la composición que hace keep/rules/apply-job.yaml.

    Expande `celQuery: chronic` y añade la exclusión de crónicas al resto. Está
    duplicada a propósito: el Job corre dentro de un contenedor con sólo su
    ConfigMap, así que no puede importar de aquí. Si cambias una, cambia la otra
    — y este script es el que se dará cuenta, porque evalúa el resultado.
    """
    chronic = spec.get("chronic") or []
    cel_list = ", ".join(json.dumps(n) for n in chronic)
    out = []
    for rule in spec["rules"]:
        rule = dict(rule)
        exempt = rule.pop("exemptFromChronic", False)
        if rule["celQuery"].strip() == "chronic":
            rule["celQuery"] = f"name in [{cel_list}]"
        elif chronic and not exempt:
            rule["celQuery"] = f'({rule["celQuery"].strip()}) && !(name in [{cel_list}])'
        out.append(rule)
    return out


def main() -> int:
    spec = yaml.safe_load(RULES.read_text())
    rules = compose(spec)
    old_route = (
        yaml.safe_load(pathlib.Path(sys.argv[1]).read_text())["spec"]["route"]
        if len(sys.argv) > 1
        else load_route()
    )

    regressions, gains = [], []
    for name, sev in load_defined():
        notifies_today = not all(
            r == "blackhole"
            for r in resolve(old_route, {"alertname": name, "severity": sev, "namespace": "x"})
        )
        covered = any(cel_matches(r["celQuery"], name, sev) for r in rules)
        if notifies_today and not covered and name not in SILENCIO_DELIBERADO:
            regressions.append((name, sev))
        if not notifies_today and covered:
            gains.append((name, sev))

    print(f"reglas de correlación: {len(rules)}")
    print(f"series que pasan a notificar y hoy están ciegas: {len(gains)}")

    if regressions:
        print(f"\n❌ REGRESIÓN: {len(regressions)} series notifican hoy y se quedarían mudas\n")
        for name, sev in sorted(regressions):
            print(f"   {name:<48} severity={sev}")
        print(
            "\nArréglalo de una de estas dos formas:\n"
            "  - dale una regla de dominio en keep/rules/correlation-rules.yaml, o\n"
            "  - si de verdad no debe notificar, añádela a SILENCIO_DELIBERADO\n"
            "    en este script con el motivo."
        )
        return 1

    print(f"\n✅ ninguna regresión ({len(SILENCIO_DELIBERADO)} silencios deliberados)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

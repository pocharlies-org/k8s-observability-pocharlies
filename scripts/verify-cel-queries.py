#!/usr/bin/env python3
"""Compila las celQuery de keep/rules/correlation-rules.yaml con cel-python.

El motor de Keep evalúa cada `celQuery` con celpy (rulesengine.py:97): una
expresión inválida —por ejemplo un comentario `#` dentro del bloque, como pasó
en INFRA-1031— sólo se descubre cuando el Job de apply llega a POST/PUT
/rules, y el Job revienta con un 500 sin decir cuál es la regla. Este script
hace la misma expansión que compose() en keep/rules/apply-job.yaml (la palabra
reservada `chronic` y el `&& !(name in [...])` de la invariante 2) y compila
después cada expresión resultante: lo que aquí no compila, en Keep tampoco.

Uso:  python3 scripts/verify-cel-queries.py [ruta-al.yaml]
Dep:  pip install cel-python pyyaml
"""
import json
import sys
from pathlib import Path

import yaml
from celpy import CELParseError, Environment

DEFAULT_SPEC = Path(__file__).resolve().parent.parent / "keep" / "rules" / "correlation-rules.yaml"


def compose(spec: dict) -> list[dict]:
    """Copia fiel de compose() en keep/rules/apply-job.yaml: lo que Keep recibe."""
    chronic = spec.get("chronic") or []
    cel_list = ", ".join(json.dumps(n) for n in chronic)
    out = []
    for rule in spec["rules"]:
        cel = rule["celQuery"].strip()
        if cel == "chronic":
            cel = f"name in [{cel_list}]"
        elif chronic and not rule.get("exemptFromChronic", False):
            cel = f"({cel}) && !(name in [{cel_list}])"
        out.append({"ruleName": rule["ruleName"], "celQuery": cel})
    return out


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SPEC
    spec = yaml.safe_load(path.read_text())
    env = Environment()
    fallos = []
    for rule in compose(spec):
        try:
            env.program(env.compile(rule["celQuery"]))
        except CELParseError as exc:
            fallos.append((rule["ruleName"], str(exc)))
    if fallos:
        for nombre, error in fallos:
            print(f"NO COMPILA  {nombre}\n{error}\n", file=sys.stderr)
        print(f"{len(fallos)} celQuery no compilan (de {len(spec['rules'])} reglas).", file=sys.stderr)
        return 1
    print(f"{len(spec['rules'])} celQuery compilan con cel-python (expansión chronic aplicada).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

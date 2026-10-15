"""Lectura compartida de los workflows de keep/values.yaml para los tests.

Los tests de comportamiento (claim de Aurora, render del prompt de RCA)
necesitan sacarse el SQL/prompt REAL del YAML: un literal copiado en el test
se queda verde aunque el YAML cambie. Aquí está la única lectura.
"""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
VALUES = ROOT / "keep" / "values.yaml"


def find_workflows(node):
    if isinstance(node, dict):
        if isinstance(node.get("workflows"), list):
            return node["workflows"]
        for v in node.values():
            found = find_workflows(v)
            if found:
                return found
    elif isinstance(node, list):
        for v in node:
            found = find_workflows(v)
            if found:
                return found
    return None


def step(workflow_id: str, step_name: str) -> dict:
    """El step `step_name` del workflow `workflow_id`, tal cual está en el YAML."""
    values = yaml.safe_load(VALUES.read_text())
    wf = next(w for w in find_workflows(values) if w.get("id") == workflow_id)
    return next(s for s in wf["steps"] if s["name"] == step_name)

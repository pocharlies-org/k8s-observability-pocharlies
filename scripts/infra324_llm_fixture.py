#!/usr/bin/env python3
"""Fixture INFRA-327 (épica INFRA-324, P3): prueba el step `llm-rca` con sus
prompts REALES antes de contar las 48 h (eso lo cierra INFRA-432).

Reconstruye el prompt exacto del step `llm-rca` del workflow
`aurora-report-back` (keep/values.yaml) para los últimos N incidentes de
Aurora con evidencia real — la misma SELECT y la misma desinfección
(`keep.` -> `Keep.`, `left(..., 600)`, strip de etiquetas HTML) — y llama a
LiteLLM con los parámetros nuevos del step (model, temperature 0.1,
max_tokens 1500). Sale 0 si >= 9 de N devuelven `content` no vacío.

Por qué existe: con max_tokens=500 el razonamiento del tier `low` (THINKING_
TIERS de LiteLLM) se comía el presupuesto y `choices[0].message.content`
salía null — 97 de 160 pasadas con RCA pendiente en 30 días (medido
2026-10-03 sobre workflowexecution). El provider de Keep (litellm_provider.
py _query) NO reenvía `reasoning_effort`, así que la única palanca del step
es subir `max_tokens`.

Dónde correr: donde haya DSN de la BBDD `aurora` de postgres-shared y una
key de LiteLLM con la allowlist del paso (la de Keep, `keep-hub`). En el pod
de keep-backend basta: lee KEEP_PROVIDERS (aurora_db) y OPENAI_API_KEY.

    kubectl -n monitoring cp scripts/infra324_llm_fixture.py deploy/keep-backend:/tmp/
    kubectl -n monitoring exec deploy/keep-backend -- python /tmp/infra324_llm_fixture.py

Con --model tooling se prueba el MISMO residente por el alias viejo (útil
mientras la allowlist de `qwen38-flash-next` en keep-hub no esté — INFRA-431).
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

# SELECT = la de rca-datos (keep/values.yaml) sin el NOT EXISTS de
# keep_bridge.reported (el fixture no marca nada) y con LIMIT N / 7 días.
ORG_SQL = ("SELECT set_config('myapp.current_org_id', "
           "(SELECT id::text FROM organizations ORDER BY created_at LIMIT 1), false)")

CANDIDATES_SQL = """
WITH cand AS (
  SELECT i.id,
         regexp_replace(coalesce(i.alert_title,'sin título'), '<[^>]*>', '', 'g') AS titulo,
         i.severity,
         i.analyzed_at
    FROM incidents i
   WHERE i.aurora_status = 'complete'
     AND i.alert_metadata->>'fingerprint' IS NOT NULL
     AND i.analyzed_at > now() - interval '7 days'
   ORDER BY i.analyzed_at DESC
   LIMIT :limit
)
SELECT c.id,
       regexp_replace(coalesce(c.titulo,''), 'keep\\.', 'Keep.', 'g'),
       coalesce(c.severity::text,''),
       regexp_replace(coalesce((SELECT string_agg(e.linea, E'\\n\\n' ORDER BY e.idx)
          FROM (SELECT es.step_index AS idx,
                       '$ ' || coalesce(es.tool_input->>'command', es.tool_name)
                         || CASE WHEN es.status <> 'success' THEN '   [FALLÓ]' ELSE '' END
                         || E'\\n'
                         || left(regexp_replace(es.tool_output, '<[^>]*>', '', 'g'), 600) AS linea
              FROM execution_steps es
             WHERE es.incident_id = c.id
               AND es.tool_output IS NOT NULL
               AND es.tool_output <> ''
               AND es.tool_name <> 'load_skill'
             ORDER BY (es.tool_input ? 'command') DESC, es.step_index
             LIMIT 18) e),
         ''), 'keep\\.', 'Keep.', 'g') AS evidencia
  FROM cand c
 ORDER BY c.analyzed_at DESC
"""

PROMPT = """Eres un SRE veterano. Abajo tienes una alerta de un clúster \
Kubernetes y la salida REAL de los comandos que un agente ejecutó para \
investigarla.

Escribe en español, en 4-6 frases, y en este orden: qué está pasando, qué \
lo causa según la evidencia, y qué mirar o tocar primero.

Cíñete a la evidencia. Si la evidencia no basta para determinar la causa, \
dilo en una frase y di qué comando concreto haría falta — no rellenes con \
generalidades. Si no hay evidencia ninguna, responde exactamente: "Sin \
investigación: el agente no ejecutó ningún comando."

ALERTA: {titulo}
SEVERIDAD: {severidad}

EVIDENCIA:
{evidencia}"""


def aurora_dsn():
    dsn = os.environ.get("AURORA_PG_DSN")
    if dsn:
        return dsn
    prov = json.loads(os.environ.get("KEEP_PROVIDERS", "{}")).get("aurora_db", {})
    auth = prov.get("authentication", {})
    if not auth:
        sys.exit("sin AURORA_PG_DSN ni KEEP_PROVIDERS.aurora_db")
    return "postgresql+psycopg2://{user}:{pw}@{host}:{port}/{db}".format(
        user=auth["username"], pw=auth["password"], host=auth["host"],
        port=auth.get("port", 5432), db=auth["database"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen38-flash-next")
    ap.add_argument("--max-tokens", type=int, default=1500)
    ap.add_argument("--limit", type=int, default=10)
    args = ap.parse_args()

    import sqlalchemy as sa
    url = os.environ.get("LITELLM_URL", "http://litellm.litellm.svc.cluster.local:4000") + "/chat/completions"
    key = os.environ.get("LITELLM_KEY") or os.environ.get("OPENAI_API_KEY")
    if not key:
        sys.exit("sin LITELLM_KEY/OPENAI_API_KEY")

    engine = sa.create_engine(aurora_dsn())
    with engine.connect() as conn:
        conn.execute(sa.text(ORG_SQL))
        rows = conn.execute(sa.text(CANDIDATES_SQL), {"limit": args.limit}).fetchall()

    ok = fail = 0
    for r in rows:
        prompt = PROMPT.format(titulo=r[1], severidad=r[2], evidencia=r[3])
        body = {"model": args.model, "temperature": 0.1, "max_tokens": args.max_tokens,
                "messages": [{"role": "user", "content": prompt}]}
        req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                     headers={"Authorization": f"Bearer {key}",
                                              "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                d = json.loads(resp.read())
            ch = d["choices"][0]
            content = ch["message"].get("content")
            usage = d.get("usage", {})
            good = bool(content) and content.strip() not in ("", "None")
            print(f"{'OK ' if good else 'VACIA'} incidente={r[0]} finish={ch.get('finish_reason')} "
                  f"content_len={len(content) if content else 0} "
                  f"reasoning_tokens={usage.get('completion_tokens_details', {}).get('reasoning_tokens')}")
            ok += good
            fail += not good
        except urllib.error.HTTPError as e:
            print(f"ERROR incidente={r[0]} HTTP {e.code} {e.read()[:200]!r}")
            fail += 1
    total = ok + fail
    print(f"\n{ok}/{total} con respuesta no vacía (modelo={args.model}, max_tokens={args.max_tokens})")
    sys.exit(0 if (total >= 10 and ok >= 9) else 1)


if __name__ == "__main__":
    main()

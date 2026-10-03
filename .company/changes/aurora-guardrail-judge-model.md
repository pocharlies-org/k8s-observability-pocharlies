# Cambio: modelo y presupuesto del juez de guardarraíles de Aurora

- **Superficie antes**: `GUARDRAILS_LLM_MODEL: bedrock/qwen38-flash-next` (juez con razonamiento, tier `low`) y espera
  fija de 10 s hardcodeada en `command_safety.py` → el juez caducaba bajo carga RCA y fallaba cerrado (279/329
  `on_prem_kubectl` en 7 días, spec INFRA-326). La key LiteLLM `aurora-rca` no tenía `qwen38-off` en su allowlist.
- **Superficie ahora**: `GUARDRAILS_LLM_MODEL: bedrock/qwen38-off` (el mismo residente del perfil `llm-tp`, razonamiento
  off) + `GUARDRAILS_LLM_TIMEOUT_SECONDS: "30"` (inerte hasta que la imagen incluya Arvo-AI/aurora#688; default 10).
  Allowlist de `aurora-rca` = existente + `qwen38-off` (BBDD de LiteLLM, `/key/update` con la lista completa leída antes
  con `/key/info`; `tooling` y `qwen38-flash-next` conservados). El juez sigue `GUARDRAILS_ENABLED=true`, fail-closed.
- **Quién se mueve y a qué**: nadie. Ningún consumidor pide el modelo del juez; la operación de key es aditiva.
  QA contrastará `blocked by safety guardrail` = 0 en la sonda (criterio C2).
- **Dónde se decidió**: INFRA-326 (spec del tech-lead: «guardrail: modelo/timeout por config; fallar cerrado se
  mantiene»), veredicto architect en `nota-architect-plan.md` de INFRA-324 (condición 7). La elección del modelo sin
  razonamiento para el juez va marcada `PARA SECURITY` en `50-entrega.md` de INFRA-326.

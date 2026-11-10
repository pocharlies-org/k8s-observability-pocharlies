# Fork documentado de aurora-server — `sha-40dfd6d-p688c`

Puente aprobado por el CTO el 2026-10-03 (INFRA-326); el 2026-11-04 el veredicto del architect
(INFRA-324, nota-architect-puente.md) fijó su estado real: **fork documentado**, no puente con
caducidad. Tres conjuntos de parches registrados — dos con PR aguas arriba y uno propio del fork
(sweep de `summarizing`) —; la retirada es por **merge aguas arriba** (cada PR fusionada retira su
conjunto), no por fecha. Registro en ARCHITECTURE.md §8.

## Qué es

`ghcr.io/pocharlies-org/aurora-server:sha-40dfd6d-p688c` = la base upstream
`ghcr.io/arvo-ai/aurora-server:1.2.20` (tag `aurora-oss-1.2.20` = commit `40dfd6dfcf95…`,
2026-09-08; pineada por **digest** `sha256:84d9586d75bf2d1cab59aefa362ffc50860b71c37fbcdd9366112c1dcc356617`
— el tag de upstream es mutable) **más los tres conjuntos de la tabla de abajo**. Espejo
`aurora-frontend:sha-40dfd6d-p688c` = el frontend upstream 1.2.20 (`aurora-frontend@sha256:e74e7a81d5dd813fcd28028de56abb00a6dc39980809a004d192b335ba2c11eb`,
copiado por digest sin rebuild — el chart compone el frontend del mismo tag global). El chart
(`aurora-oss 1.2.16`, repo de charts de Arvo vía gh-pages) no fija la imagen: la pineamos
nosotros en `aurora/values.yaml`.

Por qué 1.2.20: trae el time limit de la tarea de resumen (Arvo-AI/aurora#610, fusionada el
31-08: `time_limit=420` / `soft_time_limit=330` en `server/chat/background/summarization.py`),
que es lo que desatasca los incidentes varados en `summarizing` (153 medidos, INFRA-324). La
base anterior del fork (`sha-e35121a`, build manual del 20-08 sobre 1.2.18) no lo tenía.

Linaje de sufijos (regla del registro: cambio de contenido = sufijo nuevo, nunca reescritura
de tag): `-p688` = base manual `e35121a` (1.2.18 + tool-output) + #688, desplegado desde
2026-10-03. `-p688b` = base upstream 1.2.20 + los DOS conjuntos reaplicados. `-p688c` = `-p688b`
+ el sweep de `summarizing` (SC-2633, tercer conjunto: el cleaner de sesiones clavadas no veía
los incidentes cuyo resumen murió por time limit — AUR-18781, 07-11).

## Conjuntos de parches registrados (con su PR aguas arriba)

| conjunto | PR aguas arriba | estado (medido 04-11) | qué aporta |
|---|---|---|---|
| tool-output | [Arvo-AI/aurora#602](https://github.com/Arvo-AI/aurora/pull/602) «feat: make tool output limits configurable» | OPEN, sin actividad desde el 20-08 | los 3 commits de la rama de la PR (`d46f89e`, `ffc1b24`, `e35121a`): knobs `TOOL_OUTPUT_PASS_THROUGH_CHARS`, `TOOL_OUTPUT_MAX_SUMMARIZATION_INPUT_CHARS`, `TOOL_CONTEXT_SUMMARIZATION_THRESHOLD_TOKENS`, usados en `aurora/values.yaml`. Sin ellos el upstream fija `PASS_THROUGH_CHARS = 40_000` y esos knobs quedan inertes. |
| timeout del juez | [Arvo-AI/aurora#688](https://github.com/Arvo-AI/aurora/pull/688) | OPEN, última actividad 03-10 | `GUARDRAILS_LLM_TIMEOUT_SECONDS` (default 10, fail-closed intacto): sin el parche los 30 s desplegados en `aurora/values.yaml` son inertes y el juez caducaba a los 10 s hardcodeados de `command_safety.py` (279/329 `on_prem_kubectl` en 7 días; sonda INFRA-432: bloqueos a 10.0 s exactos; 33 % aún con algún bloqueo con el juez actual — spec INFRA-324). |
| sweep `summarizing` | propia del fork ([pocharlies-org/aurora@93efd635](https://github.com/pocharlies-org/aurora/commit/93efd635), SC-2633; sin PR aguas arriba) | desplegada desde `-p688c` | rama 5 del cleaner `cleanup_stale_background_chats`: incidentes en `aurora_status='summarizing'` +15 min sin tarea viva → re-encola el resumen (presupuesto 5/pasada, 2 reintentos por incidente) y si no, `error` terminal. Sin ella se repite AUR-18781 (07-11): el hard limit de 420 s mata la tarea de resumen con SIGKILL (el handler de `SoftTimeLimitExceeded` no llega a correr cuando el LLM residente tarda más que el límite) y el incidente queda clavado para siempre — `without_rca` sube y `AuroraRcaCoverageLow` dispara. |

Por qué un fork y no esperar: los dos conjuntos siguen sin mergear aguas arriba, y un bump
limpio a 1.2.20 dejaría los knobs `TOOL_OUTPUT_*` inertes y el juez del juez a 10 s. La
etiqueta del artefacto tiene que decir la verdad (veredicto INFRA-324). El empuje aguas
arriba se hizo, una vez, con la evidencia medida:
https://github.com/Arvo-AI/aurora/pull/688#issuecomment-5970039183 y el comentario
equivalente en #602.

## Por qué `files/*.py` y no `patch` en el Dockerfile

La imagen base no tiene `patch` ni `git` (es `python:3.12-slim`). Los ficheros de `files/`
son los de la base 1.2.20 con los dos conjuntos aplicados, y se `COPY`an tal cual. Sin pasos
`RUN`: la capa es idéntica por arquitectura y el build multi-arch no necesita ejecutar nada.

Ficheros envasados (los 4 del conjunto tool-output son byte a byte los de la rama de #602:
verificado el 2026-11-04 que los ficheros que tocan los dos parches **no tienen drift entre
1.2.18 y 1.2.20**, y los dos del #688 tampoco entre `e35121a` y 1.2.20 — aplicar los parches
sobre 1.2.20 reproduce exactamente estos ficheros):

| fichero | destino en la imagen | conjunto |
|---|---|---|
| `files/config.py` | `/app/utils/security/config.py` | timeout del juez (#688) |
| `files/command_safety.py` | `/app/utils/security/command_safety.py` | timeout del juez (#688) |
| `files/tool_output_cap.py` | `/app/chat/backend/agent/utils/tool_output_cap.py` | tool-output (#602) |
| `files/tool_context_capture.py` | `/app/chat/backend/agent/utils/tool_context_capture.py` | tool-output (#602) |
| `files/datadog_tool.py` | `/app/chat/backend/agent/tools/datadog_tool.py` | tool-output (#602) |
| `files/hpa_vpa_recommendations.py` | `/app/services/actions/hpa_vpa_recommendations.py` | tool-output (#602) |
| `files/task.py` | `/app/chat/background/task.py` | sweep `summarizing` (SC-2633) |

Los parches tocan además ficheros de test (`server/tests/…`) y de compose/helm; no se
envasan: no corren en la imagen y el chart y los values los cubrimos nosotros.

## Auditoría (hashes SHA-256, 2026-11-04)

| fichero | sha256 |
|---|---|
| `Arvo-AI-aurora-PR688.diff` (diff íntegro de #688, rama base = main de upstream) | `a6fbc9b67765f9944025193362e98d4e2fc9f5cf8b360e6b6158670d67a10116` |
| `files/config.py` (1.2.20 + #688) | `cb0327fdb0eaaeb74780bb7c57e05f34b57c94db8fa8add590219d8b63c267a6` |
| `files/command_safety.py` (1.2.20 + #688) | `bc237bfd7914ecff0cb98993100ce2e707dda9a6230e55b5fbc0fbf1b68e31f3` |
| `files/tool_output_cap.py` (1.2.20 + #602) | `2aa89544a0948002e22d0f0448edf161812b611de0d614e0a510c8cfe39613b4` |
| `files/tool_context_capture.py` (1.2.20 + #602) | `140fba3972a2b296e38265c72b435e3baf8172aa322e18515dca0d9e028416ad` |
| `files/datadog_tool.py` (1.2.20 + #602) | `6b80632ec1147b99e72ccc6b4dde15bf7432fdde6e6674da0be60494d2e95bd6` |
| `files/hpa_vpa_recommendations.py` (1.2.20 + #602) | `0c30a250af6f6b085d267f7f0a1149726d94a1aa9e153e3f98f273add246788c` |
| `files/task.py` (1.2.20 + SC-2633, medido 10-11) | `5d3b2fda87fca17594d064df4402f1ba71de0990bd1a061de8cb76676f2fbcec` |

Conjunto tool-output (#602): su contenido son los 3 commits de la rama de la PR — shas
aguas arriba `d46f89e`, `ffc1b24`, `e35121a` (base de la rama: `7ffb464b` = release 1.2.18).

Aplicación reproducible desde cero (sobre la base 1.2.20):

```sh
git clone https://github.com/arvo-ai/aurora && cd aurora
git fetch origin pull/602/head:pr602
git checkout -b bridge aurora-oss-1.2.20
# conjunto tool-output (#602): los 4 ficheros de runtime de la rama
git diff 7ffb464b e35121ae -- \
  server/chat/backend/agent/utils/tool_output_cap.py \
  server/chat/backend/agent/utils/tool_context_capture.py \
  server/chat/backend/agent/tools/datadog_tool.py \
  server/services/actions/hpa_vpa_recommendations.py | patch -p2 -d server
# conjunto timeout del juez (#688)
gh pr diff 688 -R arvo-ai/aurora | filterdiff --include='*/utils/security/*' | patch -p2 -d server
# conjunto sweep 'summarizing' (SC-2633): el diff del commit del fork, aplicado sobre el
# task.py de la base 1.2.20 (los 5 hunks entran con offset, sin fuzz; medido 10-11)
git -C <clone de pocharlies-org/aurora> show 93efd635 -- server/chat/background/task.py | patch -p2 -d server
# (filterdiff equivale a recortar los hunks de server/utils/security/* del diff; los ficheros
#  resultantes son byte a byte los de esta carpeta — compáralos con los sha256 de arriba)
python3 -m py_compile server/utils/security/config.py server/utils/security/command_safety.py \
  server/chat/backend/agent/utils/tool_output_cap.py \
  server/chat/backend/agent/utils/tool_context_capture.py \
  server/chat/backend/agent/tools/datadog_tool.py \
  server/services/actions/hpa_vpa_recommendations.py \
  server/chat/background/task.py
```

## Cómo se construye

Workflow `.github/workflows/aurora-bridge-image.yml` (este repo): `arc-k8s` + los
`buildkitd-{amd64,arm64}` del namespace `buildkit` (mismo patrón multi-arch nativo que
`dgx-infra/build-bge-embedding.yml`, sin QEMU). Se dispara solo al cambiar
`images/aurora/bridge/**` o a mano («Run workflow»). No pisa ningún tag existente: sube
`sha-40dfd6d-p688c`.

El workflow crea además el tag espejo `aurora-frontend:sha-40dfd6d-p688c` con
`docker buildx imagetools create` desde el frontend upstream 1.2.20 por digest, sin rebuild:
el chart compone `aurora-frontend:{image.tag}` del mismo tag global
(`templates/frontend-deployment.yaml`, sin override por componente) y sin ese espejo el
frontend entraría en ImagePullBackOff. La retirada borra ambos tags `-p688c` (y los
`-p688*` históricos).

En `pull_request` el workflow **no publica** (`--output type=cacheonly`: valida el
build multi-arch sin exportar — `type=oci` no soporta builder multi-nodo):
los paquetes GHCR `aurora-server`/`aurora-frontend` están vinculados al repo
`aurora` y el `GITHUB_TOKEN` de este repo no tiene `write_package` sobre ellos
(Request IT enlazada a INFRA-326). La publicación ocurre solo en `main`.

## RETIRADA (por merge aguas arriba, no por fecha)

1. **Disparador: la fusión de cada PR aguas arriba retira su conjunto** (rebase o caída del
   parche). No hay fecha de caducidad: un plazo sobre la acción de un tercero que no controlamos
   no es un plan (veredicto INFRA-324).
   - Se fusiona #688 → bump a la imagen upstream que la incluya, y en ese bump se decide **de una
     vez** la pata del conjunto tool-output: el main de upstream no tiene los 3 commits
     (knobs `TOOL_OUTPUT_*` → cap fijo de 40 000) — o #602 está ya fusionada y cae también, o se
     aceptan los 40 k, o el conjunto tool-output queda como único parche vivo del fork, con su
     hash re-registrado aquí.
   - Fusionadas #688 y #602 → el fork desaparece: bump upstream limpio, borrado de
     `images/aurora/bridge/`, de la entrada de ARCHITECTURE.md §8 y de los tags `-p688*` en GHCR.
   - Se porta el cleaner aguas arriba (el de upstream sigue sin ver `summarizing`: la rama 5 es
     propia del fork, SC-2633) → cae el conjunto sweep y `files/task.py`.
2. **Regla permanente**: el fork no se extiende más allá de los tres conjuntos registrados. Un
   cambio de contenido sube el sufijo (el siguiente sería `-p688d`) en workflow, values y README;
   nunca se reescribe un tag existente.
3. **El disparador es un mecanismo, no una fecha**: el seguimiento lo da el sistema de
   actualizaciones automáticas de upstream (skill `upstream-autoupdate`) sobre el repo
   Arvo-AI/aurora — el merge de #602/#688 y el drift de upstream por encima del umbral
   (~48+ commits a 03-10 y creciendo; el 04-11 upstream ya va por 1.5.16) abren la tarea de
   rebase del conjunto correspondiente. El registro vive en `dgx-infra/ci/update-watch.yaml`
   (contrato `dgx.update-watch.registry.v1`), **fuera de este repo**: su alta se tramita aparte
   y su estado, lo que falta para ella y la propuesta de entrada van en la PR de INFRA-1157.

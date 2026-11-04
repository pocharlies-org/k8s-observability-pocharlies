# Fork documentado de aurora-server — `sha-e35121a-p688`

Puente aprobado por el CTO el 2026-10-03 (INFRA-326); el 2026-11-04 el veredicto del architect
(INFRA-324, nota-architect-puente.md) fija su estado real: **fork documentado**, no puente con
caducidad. Dos conjuntos de parches registrados, cada uno con su PR aguas arriba; la retirada es
por **merge aguas arriba** (cada PR fusionada retira su conjunto), no por fecha. Registro en
ARCHITECTURE.md §8.

## Qué es

`ghcr.io/pocharlies-org/aurora-server:sha-e35121a-p688` = la base `sha-e35121aeb7d80293d2e4ce462fe2bc05d9adb469`
(build manual del 20-08 registrado en `15a52db` = `arvo-ai/aurora@e35121a`) **más los dos conjuntos
de la tabla de abajo**. Espejo `aurora-frontend:sha-e35121a-p688` (mismo digest — el chart compone
el frontend del mismo tag global). El chart (`aurora-oss 1.2.16`, repo de charts de Arvo vía
gh-pages) no fija la imagen: la pineamos nosotros en `aurora/values.yaml`.

## Conjuntos de parches registrados (con su PR aguas arriba)

| conjunto | PR aguas arriba | estado (medido 04-11) | qué aporta |
|---|---|---|---|
| tool-output | [Arvo-AI/aurora#602](https://github.com/Arvo-AI/aurora/pull/602) «feat: make tool output limits configurable» | OPEN, sin actividad desde el 20-08 | los 3 commits de la base (`d46f89e`, `ffc1b24`, `e35121a`): knobs `TOOL_OUTPUT_PASS_THROUGH_CHARS`, `TOOL_OUTPUT_MAX_SUMMARIZATION_INPUT_CHARS`, `TOOL_CONTEXT_SUMMARIZATION_THRESHOLD_TOKENS`, usados en `aurora/values.yaml`. Sin ellos el upstream fija `PASS_THROUGH_CHARS = 40_000` y esos knobs quedan inertes. |
| timeout del juez | [Arvo-AI/aurora#688](https://github.com/Arvo-AI/aurora/pull/688) | OPEN, última actividad 03-10 | `GUARDRAILS_LLM_TIMEOUT_SECONDS` (default 10, fail-closed intacto): sin el parche los 30 s desplegados en `aurora/values.yaml` son inertes y el juez caducaba a los 10 s hardcodeados de `command_safety.py` (279/329 `on_prem_kubectl` en 7 días; sonda INFRA-432: bloqueos a 10.0 s exactos; 33 % aún con algún bloqueo con el juez actual — spec INFRA-324). |

Por qué un fork y no esperar: lo desplegado ya era un fork antes del puente (el conjunto
tool-output nunca se mergeó aguas arriba), y un bump limpio al main de upstream dejaría los
knobs `TOOL_OUTPUT_*` inertes aunque #688 se fusionara. La etiqueta del artefacto tiene que decir
la verdad (veredicto INFRA-324). El empuje aguas arriba se hizo, una vez, con la evidencia
medida: https://github.com/Arvo-AI/aurora/pull/688#issuecomment-5970039183 y el comentario
equivalente en #602.

## Por qué `files/*.py` y no `patch` en el Dockerfile

La imagen base no tiene `patch` ni `git`. Los dos ficheros de `files/` son los de
`e35121a` con el diff de #688 aplicado (ambos ficheros son idénticos entre `e35121a` y el
main de upstream — verificado el 2026-10-03), y se `COPY`an tal cual. Sin pasos `RUN`: la
capa es idéntica por arquitectura y el build multi-arch no necesita ejecutar nada.

## Auditoría (hashes SHA-256, 2026-10-03)

Conjunto timeout del juez (#688):

| fichero | sha256 |
|---|---|
| `Arvo-AI-aurora-PR688.diff` (diff íntegro de #688, rama base = main de upstream) | `a6fbc9b67765f9944025193362e98d4e2fc9f5cf8b360e6b6158670d67a10116` |
| `files/config.py` (e35121a + #688) | `cb0327fdb0eaaeb74780bb7c57e05f34b57c94db8fa8add590219d8b63c267a6` |
| `files/command_safety.py` (e35121a + #688) | `bc237bfd7914ecff0cb98993100ce2e707dda9a6230e55b5fbc0fbf1b68e31f3` |

Conjunto tool-output (#602): su contenido son los 3 commits de la base — shas aguas arriba
`d46f89e`, `ffc1b24`, `e35121a` (la imagen base `sha-e35121a…` ya los incorpora; la PR #602 es
su forma upstream).

Aplicación reproducible desde cero (sobre la base, que ya trae el conjunto tool-output):

```sh
git clone https://github.com/arvo-ai/aurora && cd aurora && git checkout e35121a
gh pr diff 688 -R arvo-ai/aurora | filterdiff --include='*/utils/security/*' | patch -p2
# (filterdiff equivale a recortar los hunks de server/utils/security/* del diff; los dos
#  ficheros son byte a byte los de esta carpeta — compáralos con los sha256 de arriba)
python3 -m py_compile server/utils/security/config.py server/utils/security/command_safety.py
```

## Cómo se construye

Workflow `.github/workflows/aurora-bridge-image.yml` (este repo): `arc-k8s` + los
`buildkitd-{amd64,arm64}` del namespace `buildkit` (mismo patrón multi-arch nativo que
`dgx-infra/build-bge-embedding.yml`, sin QEMU). Se dispara solo al cambiar
`images/aurora/bridge/**` o a mano («Run workflow»). No pisa ningún tag existente: sube
`sha-e35121a-p688`.

El workflow crea además el tag espejo `aurora-frontend:sha-e35121a-p688` con
`docker buildx imagetools create` (mismo digest que el frontend desplegado, sin rebuild):
el chart compone `aurora-frontend:{image.tag}` del mismo tag global
(`templates/frontend-deployment.yaml`, sin override por componente) y sin ese espejo el
frontend entraría en ImagePullBackOff. La retirada borra ambos tags `-p688`.

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
     `images/aurora/bridge/`, de la entrada de ARCHITECTURE.md §8 y de ambos tags `-p688` en GHCR.
2. **Regla permanente**: el fork no se extiende más allá de los dos conjuntos registrados. Un
   cambio de contenido sube el sufijo (`-p688b`) en workflow, values y README; nunca se reescribe
   un tag existente.
3. **El disparador es un mecanismo, no una fecha**: el seguimiento lo da el sistema de
   actualizaciones automáticas de upstream (skill `upstream-autoupdate`) sobre el repo
   Arvo-AI/aurora — el merge de #602/#688 y el drift de upstream por encima del umbral
   (~48+ commits a 03-10 y creciendo) abren la tarea de rebase del conjunto correspondiente. El
   registro vive en `dgx-infra/ci/update-watch.yaml` (contrato `dgx.update-watch.registry.v1`),
   **fuera de este repo**: su alta se tramita aparte y su estado, lo que falta para ella y la
   propuesta de entrada van en la PR de INFRA-1157.

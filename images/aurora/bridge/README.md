# Bridge de imagen de aurora-server — INFRA-326 (puente temporal, plan de retirada abajo)

## Qué es

`ghcr.io/pocharlies-org/aurora-server:sha-e35121a-p688` = la imagen desplegada
(`sha-e35121aeb7d80293d2e4ce462fe2bc05d9adb469`, build manual del 20-08 registrado en
`15a52db` = `arvo-ai/aurora@e35121a` + los 3 commits del tool-output no mergeados aguas
arriba) **más el parche de [Arvo-AI/aurora#688](https://github.com/Arvo-AI/aurora/pull/688)**
(hacer configurable el timeout del juez de guardarraíles vía `GUARDRAILS_LLM_TIMEOUT_SECONDS`,
default 10, fail-closed intacto). Aprobado por el CTO el 2026-10-03 como puente hasta que
#688 se fusione (decisión registrada en INFRA-326).

Por qué un puente: el juez caducaba a los 10 s hardcodeados de `command_safety.py` y fallaba
cerrado (279/329 `on_prem_kubectl` en 7 días; sonda INFRA-432: bloqueos a 10.0 s exactos).
`GUARDRAILS_LLM_TIMEOUT_SECONDS: "30"` ya está en `aurora/values.yaml` pero era inerte sin
este parche.

## Por qué `files/*.py` y no `patch` en el Dockerfile

La imagen base no tiene `patch` ni `git`. Los dos ficheros de `files/` son los de
`e35121a` con el diff de #688 aplicado (ambos ficheros son idénticos entre `e35121a` y el
main de upstream — verificado el 2026-10-03), y se `COPY`an tal cual. Sin pasos `RUN`: la
capa es idéntica por arquitectura y el build multi-arch no necesita ejecutar nada.

## Auditoría (hashes SHA-256, 2026-10-03)

| fichero | sha256 |
|---|---|
| `Arvo-AI-aurora-PR688.diff` (diff íntegro de #688, rama base = main de upstream) | `a6fbc9b67765f9944025193362e98d4e2fc9f5cf8b360e6b6158670d67a10116` |
| `files/config.py` (e35121a + #688) | `cb0327fdb0eaaeb74780bb7c57e05f34b57c94db8fa8add590219d8b63c267a6` |
| `files/command_safety.py` (e35121a + #688) | `bc237bfd7914ecff0cb98993100ce2e707dda9a6230e55b5fbc0fbf1b68e31f3` |

Aplicación reproducible desde cero:

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

## PLAN DE RETIRADA (obligatorio, no es un «temporal» para siempre)

1. **Disparador**: cuando [Arvo-AI/aurora#688](https://github.com/Arvo-AI/aurora/pull/688)
   se fusione (o se cierre con alternativa), se **retira este puente** en el mismo trimestre:
   bump a la imagen upstream que lo incluya y borrado de `images/aurora/bridge/`, de la
   entrada de ARCHITECTURE.md §8 y del tag `-p688` en GHCR.
2. En ese bump se decide **de una vez** la pata pendiente: el main de upstream no tiene los
   3 commits del tool-output (knobs `TOOL_OUTPUT_*` → cap fijo de 40 000) — o se mergea
   también esa rama aguas arriba, o se aceptan los 40 k, o el fork tool-output se re-aplica
   como puente nuevo con su propia entrada y retirada. Prohibido dejar el `sha-e35121a`
   original vivo como estado permanente mientras tanto.
3. Si #688 sigue OPEN 30 días después de este puente (2026-11-02), escalar al CTO en el
   hito mensual — el puente no se reconvierte en fork permanente.

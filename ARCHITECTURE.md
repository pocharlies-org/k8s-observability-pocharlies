# ARCHITECTURE.md — k8s-observability-pocharlies

> Plano de observabilidad del cluster: VictoriaMetrics, Loki, Alloy, blackbox, Keep (alertas) y Aurora (RCA).
> Fuente principal de métricas/logs/alertas (el Docker Compose viejo de sauvage ya no es el plano). Escrito por
> `architect` (SC-1426).

## 1. Clientes y versiones

Sin clientes propios; despliega **9 Applications** del mismo repo (tronco **`main`**, `origin/main` = 5742c27; todas
multi-source: chart upstream + `values` de este repo, salvo indicación):

| Application | fuente | versión |
|---|---|---|
| `k8s-observability` | path `.` (kustomize: `manifests/*.yaml`, dashboards, scrapes, reglas, ingressroutes) | — |
| `vm` | chart `victoria-metrics-k8s-stack` | 0.79.0 |
| `loki` | chart `loki` (grafana) | 7.0.0 |
| `alloy` | chart `alloy` | 1.8.1 |
| `blackbox-exporter` | chart `prometheus-blackbox-exporter` | 11.10.0 |
| `keep` | chart `keep` | 0.1.96 |
| `aurora` | chart `aurora-oss` (Arvo-AI, gh-pages) | 1.2.16 |
| `aurora-kubectl-agent` | **repo upstream** `Arvo-AI/aurora` path `kubectl-agent/chart` | pinneado al SHA `8d3c5462…` |

## 2. Dependencias, en ambos sentidos

- **Depende de** — todos los nodos (Alloy/scrapes), Postgres compartido (Keep/Aurora, esquema `keep_bridge`), LiteLLM (RCA de
  Aurora), Synapse/OpenClaw (webhook de VMAlertmanager), 1Password/ExternalSecrets (`*-secrets.yaml`), Kyverno (excepciones),
  Keycloak + AgentGateway (sonda `atlassian-mcp-probe`: client `atlassian-mcp-probe` y ruta `/atlassian-probe`, SC-1834).
  Desde INFRA-550 también es **consumidor de las métricas `gha_*`** del listener/controller ARC 0.14.1 (scrape en
  `manifests/arc-scrape.yaml`; las publica `k8s-gitops-pocharlies` `infra/arc.yaml`, puerto `metrics` :8080 de los pods
  de `arc-systems`) y de `ci_queue_*` del exporter `ci-queue-exporter` (ns monitoring, desplegado por la Application
  homónima del repo gitops). Desde INFRA-712 también de las `frigate_*` que Frigate 0.18 publica en `/api/metrics` (puerto 5000 del ns
  `frigate`, Application `frigate` de `k8s-frigate-pocharlies`; scrape en `manifests/frigate-scrape.yaml`): **si la NetworkPolicy `frigate`
  de ese repo deja de admitir al `vmagent` de `monitoring` en el 5000, `FrigateCaido` salta** aunque Frigate esté sano.
- **Dependen de él** — dashboard de control-nexus (`PROMETHEUS_URL` → `vmsingle-vm-victoria-metrics-k8s-stack.monitoring.svc:8428`),
  Grafana (`grafana.e-dani.com`), todos los repos que publican `VMServiceScrape/VMRule`; contrato **Keep↔Aurora**
  (`docs/keep-aurora-contract.md` v1.4: despacho a Aurora por `keep_incident_id`, solo critical; función SECURITY DEFINER `keep_bridge.aurora_rca_coverage()`).
- **Tronco**: `main`.

## 3. Stack

| pieza | versión | para qué | no se usa en su lugar |
|---|---|---|---|
| VictoriaMetrics k8s stack | 0.79.0 | métricas, vmalert, vmalertmanager | Prometheus/cAdvisor en docker (retirados) |
| Loki + Alloy | 7.0.0 / 1.8.1 | logs | Promtail |
| Keep + Aurora | 0.1.96 / 1.2.16 | correlación y RCA de alertas | Alertmanager a pelo |
| promtool | CI | test de reglas (INFRA-376) | — |
| `atlassian-mcp-probe` (Deployment, script stdlib en ConfigMap) | python 3.12 | sonda funcional del MCP de Atlassian: cada 60 s un `tools/call jira_get_issue` real vía AgentGateway `/atlassian-probe`; métrica `atlassian_mcp_tool_up` (SC-1834, H4 SC-1728) | blackbox `VMProbe` (no hace sesión MCP), `/readyz` (verde con PoolTimeout) |

## 4. Componentes compartidos

| concepto | pieza canónica | ruta | quién la usa |
|---|---|---|---|
| Reglas de enrutado de alertas | matriz | `docs/alert-routing-matrix.md`, `keep/rules/` | toda alerta del estate |
| Contrato Keep↔Aurora | `docs/keep-aurora-contract.md` | ídem | Keep, Aurora |
| Alerta de caída del MCP de Atlassian (SC-1728/H5) | `VMRule AtlassianMcpToolDown` + regla de correlación homónima | `manifests/atlassian-mcp-rules.yaml`, `keep/rules/correlation-rules.yaml` | sonda `atlassian-mcp-probe` (SC-1834); `ops-watch` (x86-host-runtime) por `rule_name` == `company_requests.REGLAS_CAIDA_JIRA` — renombrar = entrada nueva junto a la vieja |
| Reglas ARC / cola de CI (INFRA-550) | `VMRule pocharlies-arc-ci` (cola >20 min, label sin pool, runner sin progreso >10 min, pool saturado, ceguera del exporter) + scrape `gha_*`/`ci_queue_*` | `manifests/arc-rules.yaml`, `manifests/arc-scrape.yaml`; casos en `tests/promtool/arc-rules.test.yaml`, correlación en `tests/test_infra550_ci_queue_correlation.py` | Keep → incidente (Request vía ops-watch): Alertmanager las lleva a `keep` (catch-all, sin allowlist) y la regla de correlación `ci-queue-degraded` (`keep/rules/correlation-rules.yaml`, prefijo `CIQ`) las convierte en incidente — sin regla una `warning` queda registrada y calla; fuente de «label sin pool» = exporter `ci-queue-exporter` (gitops), no `gha_*` |
| Reglas de Frigate (INFRA-712) | `VMRule pocharlies-frigate` (`FrigateCaido`, `FrigateDetectorLento` >100 ms, `FrigateCamaraSinFps` de `c8w`/`hp7`, `FrigateAlmacenamientoLleno` de `frigate-media` <8 % 15 min) + scrape `frigate_*` | `manifests/frigate-rules.yaml`, `manifests/frigate-scrape.yaml`; casos en `tests/promtool/frigate-rules.test.yaml`, correlación en `tests/test_infra712_frigate_correlation.py` | Keep → incidente, como las de ARC: el catch-all de Alertmanager las lleva a `keep` (**no hay ruta por alertname ni blackhole de warnings**) y la regla de correlación `frigate-vigilancia` (prefijo `FRG`, `Frigate*`) las convierte en incidente. El `/` del nodo `ubuntu` no se duplica: lo cubre `NodeRootDiskLowOrFilling` |
| Ingesta asíncrona de Keep (INFRA-1572 / INFRA-1336 P2) | `keepsvc-redis` (Deployment + Service + PVC con AOF; cola ARQ `KEEP_ARQ_QUEUE_BASIC`) y `keepsvc-worker` (consumidor ÚNICO FIFO: replicas=1 + Recreate + gunicorn `--workers 1` con `ARQGunicornWorker` + `KEEP_EVENT_WORKERS=1`) | `keep/redis.yaml`, `keep/worker.yaml`; `keep/values.yaml` (`REDIS=true`, `REDIS_HOST`, `backend.command` API-only) | keep-backend encola y responde 202 (p99 <2 s, C1); el worker procesa y drena los workflows de evento; **no tocar** el `command` del backend ni bajar el worker a 0: dos consumidores o ninguno rompen el orden firing→resolved (keep-hub-degraded e1144f20eb). Pin: `tests/test_keep_async_ingest.py` |
| Claim de despacho a Aurora (solo critical, una vez por incidente de Keep, cooldown 6 h) | step `claim-dispatch` del workflow `aurora-investigate` | `keep/values.yaml` | Keep → Aurora; lectores `rca-datos`, `link-datos`, `mark-linked`, `aurora_rca_coverage()` (cruzan por `fingerprint`) |
| Alerta de disco raíz de los nodos del matcher `node` — ubuntu y sauvage (INFRA-623, SC-2986): <20 % libre o llena en 3 días al ritmo de las últimas 12 h (SC-6122: con 6 h las ráfagas de imágenes/WAL de ks5-cp-* abrían Requests sin nada que arreglar) | `VMRule NodeRootDiskLowOrFilling` (`pocharlies-node-disk`) + test promtool | `manifests/rules.yaml`, `tests/promtool/node-disk.test.yaml` | los defaults del chart (`NodeFilesystem*`) no saltaron el 07-10: el kubelet desaloja a <5 % libre. El resto de nodos no está vigilado: añadir un nodo = añadirlo al regex `node` (alphalink estaba a ~15 % libre el 28-10 sin aviso) |
| Saturación de load/CPU de nodos, calibrada por clase (SC-6015) | `VMRule pocharlies-node-saturation` (`NodeSystemSaturation` warning solo no-cómputo, `NodeSystemSaturationCompute` info, `NodeCPUHighUsage` info — las tres con el join `node`) | `manifests/rules.yaml`, `tests/promtool/node-saturation.test.yaml`; upstream `NodeSystemSaturation`/`NodeCPUHighUsage` desactivadas en `victoria-metrics/values.yaml` | la copia del chart no propaga `node` (sin join, dos nodos distintos compartían keep-causa → falso [PROBLEMA] SC-5976) y el load >2/core es el punto de operación en los nodos de cómputo (atlantic, los Sparks); añadir un nodo de cómputo = añadirlo a los dos regex `node` del grupo |
| Dashboards | `manifests/dashboards.yaml`, `grafana-company-dashboard.yaml`, `grafana-keep.yaml` | ídem | Grafana |
| Modelo LLM de Aurora y Keep | nombre directo `qwen38-flash-next` (residente único del perfil `llm-tp`; fallback y allowlist en LiteLLM) | `aurora/values.yaml`, `keep/values.yaml` | Aurora, Keep |
| Notificación de incidentes | el incidente de Keep ES la notificación; `ops-watch` (x86-host-runtime) lo convierte en Request | `keep/rules/correlation-rules.yaml`; `docs/keep-aurora-contract.md` | INFRA-912 (2026-10-17): retirados los workflows de aviso por Telegram (`notify-incident*`, `notify-alert-summary`, `incident-summary`) y el receiver `backstop-telegram` de Alertmanager |

## 5. Cómo se construye aquí

Un componente = `<comp>/values.yaml` + `apps/<comp>.yaml` (registrado en `k8s-gitops-pocharlies`) + manifiestos crudos en
`manifests/`. Reglas de alerta como `VMRule` junto al servicio que vigilan o en `manifests/*-rules.yaml`. Ningún LLM en bucle.
Las superficies del contrato Keep↔Aurora **no se cambian sin versionar** el documento.

## 6. Tests y validaciones

```sh
AURORA_TEST_PG_DSN=postgresql://… python3 -m pytest tests/ -q             # claim de Aurora contra Postgres desechable (INFRA-406)
promtool test rules …                                                    # test de regla INFRA-376 (ver ci.yml)
python3 scripts/verify-notification-coverage.py                          # red del cutover a Keep: ninguna serie que hoy notifica se queda muda (exit 0)
```
CI ejecuta además contratos de idempotencia, presupuesto y despacho de alertas, y el test de comportamiento del claim de
Aurora (`tests/test_keep_aurora_claim_behavior.py`: rearme, cooldown 6 h, migración expand/contract con `aurora_rca_coverage()`
igual). Necesita Postgres: sin `AURORA_TEST_PG_DSN` se salta en local y **falla si `CI=true`**. Cobertura global **pendiente de medir**.

## 7. CI/CD y despliegue

- `ci.yml` (`arc-k8s`): service container `postgres:16` + `psycopg[binary]` (elegido frente a `postgresql` por apt: sin sudo ni
  instalación de paquetes en el runner; **no medido en `arc-k8s` hasta el primer run del PR de INFRA-406**), instala promtool, ejecuta contratos de idempotencia/presupuesto/dispatch, y `reusable-ci.yml@main`
  (kustomize). `pr-review.yml`.
- Despliegue: merge a `main` → 9 apps ArgoCD. **Validación en producción**: `up` de los targets en VictoriaMetrics, una alerta de
  prueba que llegue a Keep y a Synapse, Loki devolviendo logs recientes de `sauvage`. Synced ≠ funcionando. Pendiente de ejecutar.

## 8. Decisiones y trampas

- `2026-11-23` · DGX-1789: **la sesión de arreglo se cierra con su incidente**. El workflow `alertas-cierre` escucha
  `type: incident` / `events: [updated]` (la resolución de Keep 0.52.1 sale como `updated`, no trae evento propio) y,
  solo cuando `incident.status = resolved` (`{{ incident.status }}` renderiza el repr del enum, `IncidentStatus.RESOLVED`,
  y la query lo normaliza), publica por la conexión `synapse_keep` `{tipo: cierre, fingerprints}`; cada
  fingerprint es el del despacho (= `substr(md5(keep_incident_id),1,16)`, el mismo con el que el RCA abrió la sesión y
  la clave `keep-<fingerprint>` del lanzador). El step devuelve SIEMPRE una fila (`LEFT JOIN` sobre `(VALUES (1))`)
  porque el `if` no existe en los steps y con 0 filas `results.0.0` renderiza vacío; sin columna nueva, el cierre del
  dashboard es idempotente. **Fusión**: `merge_incidents_to_id` cambia de id al absorbido, le quita las alertas y no
  emite evento (medido), así que el cierre se calcula contra la BBDD de Keep al resolverse el superviviente: un CTE
  recursivo sobre `incident.merged_into_incident_id` da todas las claves del árbol y el adapter hace un POST por
  clave (contrato del dashboard intacto). Provider nuevo `keep_db` (mismas credenciales del chart, item `keep`).
  Límite: fusionar en un incidente ya resuelto no dispara nada. Pin: `tests/test_dgx1789_keep_cierre_contract.py`.
- `2026-11-19` · SC-6015 (desde el problema SC-5976, keep-causa node-degraded:80563cc44e): `NodeSystemSaturation` y
  `NodeCPUHighUsage` del chart desactivadas y reemplazadas por `pocharlies-node-saturation` (mismo patrón SC-5736/INFRA-690):
  el join `* on(pod) group_left(node)` propaga `node` (dos saturaciones en nodos distintos ya no comparten keep-causa —
  SC-5941 en atlantic y SC-5975 en dgx3 montaban el mismo hash) y el warning de load >2/core se queda solo en los nodos
  que NO son de cómputo; atlantic y los tres Sparks viven en `NodeSystemSaturationCompute` (info → blackhole, sin Request).
  El umbral global no baja: una saturación real fuera de cómputo (ks5-cp-3 medía 2.0 el 19-11) sigue abriendo incidente.
  Pin: `tests/promtool/node-saturation.test.yaml`.

- `2026-11-16` · SC-5736 (desde el problema SC-5518): clase de nodo «servidor de modelos» (los tres Sparks, los que
  corren un worker vLLM residente) calibrada a disco alto: la rama `predict_linear` de `NodeRootDiskLowOrFilling` sale
  del crítico para dgx3 y vive en `NodeModelServerDiskPredicted` (info → sin incidente en Keep, sin Request de ops-watch;
  medido SC-5100: 84 % por pesos EN USO con 146 GiB libres). El lleno real NO se enmascara: el suelo de 100 GiB y
  `NodeDiskPressure` siguen críticos. Y el join pasa a `* on(pod) group_left(node)` en disco y memoria: la alerta lleva
  `node`, la firma keep-causa distingue el nodo y dgx3 y atlantic dejaron de compartir hash `464898bf77` (el falso
  [PROBLEMA] SC-5518). Pin: `tests/promtool/node-disk.test.yaml`.

- `2026-11-03` · INFRA-1135 (SC-4342): `cron-job-failed` agrupa por `[namespace, owner_name]` y su nombre lleva el
  CronJob. ops-watch calcula la `keep-causa` de la Request como sha1 del nombre del incidente (sin su número) más el
  conjunto de tokens de alerta —alertname y recurso, y `node` desde SC-5736— (x86-host-runtime, `FIRMA_RECURSO_LABELS`),
  así que la granularidad del incidente es la de la causa: con `[namespace, alertname]` los ~20 CronJobs de un namespace
  compartían una sola causa (medido: `9c99776a1c` bajo la que cayeron architecture-sync, memory-promotion y
  knowledge-pages). `owner_name` (el CronJob, `kube_job_owner`) llega top-level a la alerta; `job_name` (el Job, con
  sufijo de ejecución) NUNCA va al nombre: sería un número volátil en la causa. BrainIngestConsecutiveFailures no
  lleva `owner_name` → huella «none» en Keep (`rulesengine._calc_rule_fingerprint`) → sigue con su propio incidente
  (INFRA-378 se conserva). Pin: `tests/test_infra378_keep_notify_contract.py`.

- `2026-10-17` · INFRA-912 (Dani: «las alertas en Telegram son inútiles; borra todos los topics de alertas»). Fuera
  TODO envío a Telegram del repo: los cuatro workflows de aviso de `keep/values.yaml`, la action `telegram-rca` de
  `aurora-report-back` (el RCA queda en la ejecución y en Aurora; dejarlo como comentario en la Request no es trivial
  desde Keep — no hay provider Jira — y queda anotado), el receiver `backstop-telegram` con sus tres rutas de
  Alertmanager (las alertas quedan sólo en Keep), `manifests/backup-alert-reports.yaml`, el ExternalSecret
  `alertmanager-telegram-backup`, el provider `telegram_ops` de `keep-secrets.yaml` y el bloque de envío del
  `dgx-cluster-health-watcher`. Consecuencia asumida: ya no hay vía de aviso que no pase por Keep — si el hub cae,
  no hay backstop directo. Pines: `tests/test_infra912_no_telegram_emitters.py`,
  `tests/test_infra378_keep_notify_contract.py`.
- `2026-10-17` · INFRA-910 (Dani): **fuera k8sgpt** (operador, explainer y regla `k8sgpt-degraded`). Lo que detectaba
  (crashloop, Deployments degradados, CronJobs fallidos) ya lo cubren `deployment-degraded`, `workload-degraded` y
  `cron-job-failed`; su IA estaba apagada y el explainer con tope de 24 llamadas al día.
- `2026-10-16` · INFRA-882: **sin capa crónica**. Se borran la lista `chronic`, la regla `chronic-debt` y su expansión
  (apply-job, verify-notification-coverage, `alert_routing.py chronic`): tapaba alertas reales (el gmail de Synapse,
  3 h sin consumidor). Una alerta que suena siempre es algo roto (incidente acknowledged con su ticket) o una regla
  mala (se corrige). `synapse-pipeline` agrupa por `[alertname, queue]`: con `[]` una cola nueva se unía al incidente
  abierto de otra y no avisaba. Corregidas: `BlackboxProbeDown` 10m, `RabbitmqDlqGrowth` >= 5 en 6 h,
  `SynapseWorkflowFailed` (engine) >= 2 en 30m.

- `2026-10-16` · INFRA-882 (Dani: «Keep a cero, solo lo que pide acción»). `severity=info` e `InfoInhibitor` van al
  `blackhole` de Alertmanager; `TrunkCIFailed`/`UpdateWatchFailed` ya no entran (ops-watch dejó de empujarlos y sus
  reglas se borraron; las ya creadas en Keep se borran a mano, el apply-job no borra). **Trampa del reaper**: resolvía
  también lo empujado por ops-watch (nunca está en AM), ops-watch lo volvía a disparar y Keep abría otro incidente:
  ~300 incidentes por causa en 7 días y una alerta con nombre-UUID por replay. Ahora el reaper ignora `source: x86`;
  ArgoCD sigue pasando por él porque no emite `resolved`. `K8sCronJobFailed` agrega por CronJob (`owner_name`), no por
  Job, y el explicador de k8sgpt quita el sufijo de ejecución de CronJob de su huella (cada pod gastaba cupo).

- `2026-10-05` · INFRA-378: la regla `cron-job-failed` agrupa por `[namespace, alertname]` y su nombre lleva el
  `alertname` — agrupando sólo por namespace, el incidente viejo CRON absorbía las alertas nuevas sin emitir
  `created` y Telegram no se enteraba (incidente 9d403a3e, 9 días). Los resúmenes de las alertas salen del workflow
  `notify-alert-summary` (`type: alert`, `only_on_change: [status]`, sin steps ni parse_mode); `incident.alerts`
  **no se puede volcar en una plantilla** (renderiza el repr de Python). `notify-incident*` siguen en `[created]`:
  Alertmanager reenvía cada minuto y notificar en `updated` sería un mensaje/min. Test:
  `tests/test_infra378_keep_notify_contract.py`.
- `2026-10-09` · INFRA-378 / INFRA-751: **quién drena los workflows de evento de Keep**. Sin Redis (0.52.1) van por una
  cola en memoria del proceso que recibe el webhook de Alertmanager, y solo el WorkflowScheduler de ESE proceso la
  vacía. `keep-backend` lleva `SCHEDULER=true` + `WORKFLOWS_INTERVAL_ENABLED=false`; `keepsvc-scheduler`, `true` + `true`
  (únicos de intervalo). SC-1711 puso `SCHEDULER=false` en el backend: último `workflowexecution` de Telegram
  04-10 01:24:47Z, siguiente 09-10 15:10:39Z — cinco días sin un solo aviso al topic 1248 y nada lo detectó. Test:
  `tests/test_infra378_keep_scheduler_split_contract.py`. Un aviso perdido en ese hueco no se reenvía solo: con
  `only_on_change: [status]` y `[created]` solo sale en el siguiente cambio de estado.
- `aurora-kubectl-agent` apunta a un **SHA del repo upstream**, no a un chart publicado: subirlo exige revisar el diff upstream.
- README desfasado (k3s v1.32.5; describe el «estado objetivo» como tarea).
- `2026-10-02` · Keep↔Aurora v1.3 (INFRA-406): una investigación por incidente de Keep (PK `keep_incident_id`, `fingerprint` = token
  `substr(md5(incidente),1,16)`, cooldown 6 h por `alert_fingerprint`); la migración es expand → deploy → contract y la ejecuta devops.
- `2026-09-23` · Keep↔Aurora v1.2 (INFRA-217): se retira el GRANT/policy sobre `public.incidents` de v1.1 por la función
  `aurora_rca_coverage()` (revisión del architect).
- `2026-10-03` · Aurora y Keep piden `qwen38-flash-next` por nombre (residente único `llm-tp`); allowlist de keys solo en
  BBDD de LiteLLM (`keep-hub`, `aurorasvc-llm` — virtual key alias `aurora-rca`). Revierte la de 15-08 de un solo alias
  `tooling` (INFRA-324/325/327; test `tests/test_infra324_llm_models_contract.py`). No se migran `k8sgpt-explainer` ni
  el selector del chat de Aurora (`aurora-frontend-models-policy.yaml`): siguen en `tooling`.
- Trampa de los steps LLM de Keep (INFRA-327, medido 2026-10-03): el tier `low` de THINKING_TIERS gasta razonamiento
  DENTRO de `max_tokens` (en `llm-rca`, ~360–1070 tokens) y LitellmProvider no reenvía `reasoning_effort` — con 500,
  el 61 % de las pasadas con RCA pendiente devolvían `response: null`. `max_tokens: 1500` lo cubre; el techo real es
  el `timeout=60` fijo del provider (~15–45 tok/s del residente). Fixture de prompts reales: `scripts/infra324_llm_fixture.py`.
- `2026-10-03` · El juez de guardarraíles de Aurora pide el mismo residente **sin razonar** (`GUARDRAILS_LLM_MODEL:
  bedrock/qwen38-off`) y su presupuesto de espera pasa a `GUARDRAILS_LLM_TIMEOUT_SECONDS` (30; operativo desde que la
  imagen incluya Arvo-AI/aurora#688 — hoy el 10 s está hardcodeado y el juez caducaba y fallaba cerrado en el 279/329 de
  los `on_prem_kubectl`, INFRA-326). El juez sigue activo y fail-closed; sólo cambia su modelo y su espera. La key
  `aurora-rca` ganó `qwen38-off` en su allowlist (BBDD de LiteLLM, `/key/update` con lista completa).
- `2026-11-04` · **Fork documentado `aurora-server:sha-e35121a-p688`** (INFRA-324, veredicto del architect
  nota-architect-puente.md; reescribe la entrada de puente de INFRA-326 — la escalada al CTO que esa entrada
  prescribía para el 2026-11-02 queda cumplida con el veredicto, y su sello es el merge de este registro):
  lo desplegado no es un puente con caducidad, es un **fork propio con dos conjuntos de parches registrados**.
  Base `sha-e35121a` = build manual del 20-08 (`15a52db`) de `arvo-ai/aurora@e35121a`. Conjuntos:
  **(1) tool-output** — 3 commits sin mergear aguas arriba (`d46f89e`, `ffc1b24`, `e35121a`), PR aguas arriba
  Arvo-AI/aurora#602 «feat: make tool output limits configurable» (OPEN, sin actividad desde el 20-08); sin
  ella el upstream fija `PASS_THROUGH_CHARS = 40_000` y los knobs `TOOL_OUTPUT_*` de `aurora/values.yaml`
  quedan inertes. **(2) timeout del juez** — el diff de Arvo-AI/aurora#688 (OPEN, última actividad 03-10)
  sobre `config.py` (`cb0327fd…`) y `command_safety.py` (`bc237bfd…`), diff `a6fbc9b6…10116`: hace legible
  `GUARDRAILS_LLM_TIMEOUT_SECONDS`; sin él los 30 s desplegados son inertes y el juez caducaba a 10 s
  fail-closed (279/329 `on_prem_kubectl` en 7 días, INFRA-326; 33 % con el juez actual, spec INFRA-324).
  Build reproducible por digest en GitOps: `.github/workflows/aurora-bridge-image.yml` (`arc-k8s` + buildkitd
  remotos, multi-arch sin QEMU; espeja también `aurora-frontend:…-p688`, que el chart compone del mismo tag);
  base, hashes y aplicación reproducible: `images/aurora/bridge/README.md`. **Retirada por merge aguas arriba,
  no por fecha**: la fusión de cada PR retira su conjunto (rebase o caída del parche); con la de #688 se
  decide la pata `TOOL_OUTPUT_*` (knobs vs cap fijo 40 k); con ambas fusionadas, el fork desaparece (bump
  upstream + borrar `images/aurora/bridge/`, esta entrada y los tags `-p688`). Regla permanente: el fork no se
  extiende más allá de los dos conjuntos registrados — un cambio de contenido sube sufijo (`-p688b`) en
  workflow, values y README, nunca reescribe el tag. El disparador de la retirada es un mecanismo, no una
  fecha: el vigía de drift sobre Arvo-AI/aurora (registro upstream-autoupdate, en `dgx-infra` — fuera de este
  repo; su alta se tramita aparte, ver PR de INFRA-1157) convierte cada merge en la tarea de rebase del
  conjunto correspondiente.
- `2026-11-04` · **Bump de base del fork a upstream 1.2.20 → tag `sha-40dfd6d-p688b`** (INFRA-1157,
  segundo tramo): la base pasa del build manual `sha-e35121a` (1.2.18) a la imagen publicada
  `ghcr.io/arvo-ai/aurora-server:1.2.20` (commit `40dfd6d`, pineada por digest `84d9586d…` — el tag
  de upstream es mutable). Motivo medido: 1.2.20 trae Arvo-AI/aurora#610 (fusionada el 31-08), que
  pone `time_limit=420`/`soft_time_limit=330` a la tarea de resumen y desatasca los 153 incidentes
  varados en `summarizing`. Los DOS conjuntos registrados se reaplican sin conflicto sobre 1.2.20
  (medido 04-11: los ficheros que tocan no tienen drift entre 1.2.18 y 1.2.20; los ficheros del
  #688 son byte a byte los ya envasados) y el frontend se espeja desde el upstream 1.2.20 por
  digest. Sufijo nuevo `-p688b` por la regla de arriba (cambio de contenido = sufijo, nunca
  reescritura); el chart sigue en `aurora-oss 1.2.16` — subirlo es decisión aparte, no acompaña a
  este bump. Ficheros, hashes y comando de aplicación: `images/aurora/bridge/README.md`.
- `2026-11-10` · **Tercer conjunto del fork: sweep de `summarizing` → tag `sha-40dfd6d-p688c`**
  (SC-4980, Request del incidente de Keep AUR-18781): el bump a 1.2.20 redujo pero no cerró los
  varados en `aurora_status='summarizing'` — cuando el resumen LLM tarda más que el hard limit
  (420 s), Celery mata la tarea con SIGKILL, el handler de `SoftTimeLimitExceeded` no corre y el
  incidente queda clavado sin terminal; `cnpg_aurora_rca_coverage_without_rca` sube y dispara
  `AuroraRcaCoverageLow` (medido 07-11: 12/27 despachos sin RCA, ratio 0.85 en la ventana del
  disparo). El conjunto es la rama 5 del cleaner del fork (SC-2633, `pocharlies-org/aurora@93efd635`)
  aplicada sobre el `task.py` de la base 1.2.20: re-encola el resumen (5 por pasada, 2 reintentos
  por incidente) y si no, `error` terminal. Fichero `files/task.py`, hash y retirada en el README
  del puente; values y workflow suben el sufijo a `-p688c` (regla de arriba).

- `2026-11-25` · INFRA-1572 (P2 de INFRA-1336): **ingesta asíncrona de Keep (ARQ/Redis)**. El POST
  `/alerts/event/prometheus` deja de procesarse dentro del worker gunicorn de la API (thread pool de 5
  hilos + pool de Postgres del propio worker: la ráfaga los saturaba y Alertmanager perdía lotes —
  keep-hub-degraded e1144f20eb). `keep-backend` lleva `REDIS=true` + `REDIS_HOST=keepsvc-redis` y un
  `backend.command` API-only (con `REDIS=true` el entrypoint de la imagen arrancaría 2 workers ARQ más
  en el pod de la API). `keepsvc-redis` (Deployment + Service + PVC con AOF; el chart 0.1.96 no trae
  Redis) hace de cola `KEEP_ARQ_QUEUE_BASIC`; `keepsvc-worker` (patrón de `keep/scheduler.yaml`) es el
  consumidor ÚNICO FIFO: `replicas=1` + Recreate + gunicorn `--workers 1` con
  `keep.api.arq_worker_gunicorn.ARQGunicornWorker` + `KEEP_EVENT_WORKERS=1` ⇒ un `resolved` nunca se
  procesa antes que su `firing`. El worker corre el WorkflowManager (los workflows de evento caen en
  su cola en memoria — el dispatch a Redis está comentado upstream); los de intervalo siguen siendo de
  `keepsvc-scheduler` (`WORKFLOWS_INTERVAL_ENABLED=false` en backend y worker) ⇒ contrato Aurora intacto,
  sin `.vN+1`. Redis caído ⇒ el enqueue falla ⇒ reintenta Alertmanager (receiver 90 s, INFRA-1335).
  Test: `tests/test_keep_async_ingest.py`.

Última verificación contra el código: 2026-10-03 · 09373a7 (origin/main)

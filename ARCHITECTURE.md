# ARCHITECTURE.md — k8s-observability-pocharlies

> Plano de observabilidad del cluster: VictoriaMetrics, Loki, Alloy, blackbox, Keep (alertas), Aurora (RCA), K8sGPT.
> Fuente principal de métricas/logs/alertas (el Docker Compose viejo de sauvage ya no es el plano). Escrito por
> `architect` (SC-1426).

## 1. Clientes y versiones

Sin clientes propios; despliega **9 Applications** del mismo repo (tronco **`main`**, `origin/main` = 1948eb6; todas
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
| `k8sgpt` | chart `k8sgpt-operator` | 0.2.27 |

## 2. Dependencias, en ambos sentidos

- **Depende de** — todos los nodos (Alloy/scrapes), Postgres compartido (Keep/Aurora, esquema `keep_bridge`), LiteLLM (RCA de
  Aurora, K8sGPT), Synapse/OpenClaw (webhook de VMAlertmanager), 1Password/ExternalSecrets (`*-secrets.yaml`), Kyverno (excepciones).
- **Dependen de él** — dashboard de control-nexus (`PROMETHEUS_URL` → `vmsingle-vm-victoria-metrics-k8s-stack.monitoring.svc:8428`),
  Grafana (`grafana.e-dani.com`), todos los repos que publican `VMServiceScrape/VMRule`; contrato **Keep↔Aurora**
  (`docs/keep-aurora-contract.md` v1.2, función SECURITY DEFINER `keep_bridge.aurora_rca_coverage()`).
- **Tronco**: `main`.

## 3. Stack

| pieza | versión | para qué | no se usa en su lugar |
|---|---|---|---|
| VictoriaMetrics k8s stack | 0.79.0 | métricas, vmalert, vmalertmanager | Prometheus/cAdvisor en docker (retirados) |
| Loki + Alloy | 7.0.0 / 1.8.1 | logs | Promtail |
| Keep + Aurora | 0.1.96 / 1.2.16 | correlación y RCA de alertas | Alertmanager a pelo |
| K8sGPT (solo detección determinista cada 15 min) | operator 0.2.27 | diagnóstico sin bucles LLM; analyzers `ReplicaSet/Service/Job` excluidos | análisis LLM continuo |
| Python 3.12 (`k8sgpt-explainer/explainer.py`) + promtool | CI | explicador y test de reglas (INFRA-376) | — |

## 4. Componentes compartidos

| concepto | pieza canónica | ruta | quién la usa |
|---|---|---|---|
| Reglas de enrutado de alertas | matriz | `docs/alert-routing-matrix.md`, `keep/rules/` | toda alerta del estate |
| Contrato Keep↔Aurora | `docs/keep-aurora-contract.md` | ídem | Keep, Aurora |
| Dashboards | `manifests/dashboards.yaml`, `grafana-company-dashboard.yaml`, `grafana-keep.yaml` | ídem | Grafana |

## 5. Cómo se construye aquí

Un componente = `<comp>/values.yaml` + `apps/<comp>.yaml` (registrado en `k8s-gitops-pocharlies`) + manifiestos crudos en
`manifests/`. Reglas de alerta como `VMRule` junto al servicio que vigilan o en `manifests/*-rules.yaml`. Ningún LLM en bucle
(coste: ver README K8sGPT). Las superficies del contrato Keep↔Aurora **no se cambian sin versionar** el documento.

## 6. Tests y validaciones

```sh
python3 -m unittest discover -s k8sgpt-explainer/tests -p 'test_*.py'    # 7 tests del explicador
promtool test rules …                                                    # test de regla INFRA-376 (ver ci.yml)
```
CI ejecuta además contratos de idempotencia, presupuesto y despacho de alertas. Cobertura global **pendiente de medir**.

## 7. CI/CD y despliegue

- `ci.yml` (`arc-k8s`): instala promtool, ejecuta contratos de idempotencia/presupuesto/dispatch, y `reusable-ci.yml@main`
  (kustomize). `pr-review.yml`.
- Despliegue: merge a `main` → 9 apps ArgoCD. **Validación en producción**: `up` de los targets en VictoriaMetrics, una alerta de
  prueba que llegue a Keep y a Synapse, Loki devolviendo logs recientes de `sauvage`. Synced ≠ funcionando. Pendiente de ejecutar.

## 8. Decisiones y trampas

- `aurora-kubectl-agent` apunta a un **SHA del repo upstream**, no a un chart publicado: subirlo exige revisar el diff upstream.
- README desfasado (k3s v1.32.5; describe el «estado objetivo» como tarea).
- `2026-09-23` · Keep↔Aurora v1.2 (INFRA-217): se retira el GRANT/policy sobre `public.incidents` de v1.1 por la función
  `aurora_rca_coverage()` (revisión del architect).
- K8sGPT excluyó `ReplicaSet/Service/Job` porque concentraban ~2.746 hallazgos y disparaban bucles LLM.

Última verificación contra el código: 2026-10-01 · 1948eb6 (origin/main)

# Alertas empujadas directo a Keep (fuera del árbol de Alertmanager)

Mantenida **a mano**: `docs/alert-routing-matrix.md` se genera desde las VMRules
del clúster (`scripts/alert_routing.py matrix`) y estas familias no son
VMRules — no pasan por Alertmanager, entran por `POST /alerts/event` con la key
de rol `webhook`. Su cobertura la dan las reglas de correlación de
`keep/rules/correlation-rules.yaml` (pinned por
`tests/test_infra405_correlation_rules.py`); el pie de la matriz enlazada a este
fichero para que el árbol no se lea como el mapa completo.

| alerta | emisor | severidad | clave de causa | regla → prefijo | desde |
|---|---|---|---|---|---|
| `ArgoCD…` (on-sync-failed / on-health-degraded) | ArgoCD Notifications (`k8s-gitops-pocharlies/argocd/values.yaml`) | `warning` | `app` | `argocd-app-degraded` → ARGO | 29-09-2026 |
| `X86UnitFailed` | ops-watch `empujar_a_keep` (`x86-host-runtime-pocharlies`, fuente `unidades`) | `warning` | `unit` | `x86-unit-failed` → X86U | INFRA-405 |
| `TrunkCIFailed` | ops-watch (fuente `ci`) | `warning` | `repo` | `trunk-ci-failed` → CI | INFRA-405 |
| `UpdateWatchFailed` | ops-watch (fuente `updates`) | `warning` | `fail_reason` (`<via>:<firma>`) | `update-watch-failed` → UPD | INFRA-405 |

Las cuatro son `warning` a propósito: `critical-safety-net` sólo captura
critical/page, así que no solapan con ella ni figuran en su lista de exclusión
(INVARIANTE 1 de `correlation-rules.yaml`), y el carril de Aurora acepta
warning (`docs/keep-aurora-contract.md` §6). El `resolved` lo emite el emisor:
ArgoCD hoy no lo emite — riesgo conocido, medido por INFRA-408; para las
familias x86 está previsto según el diseño de INFRA-404 (su PR aún no está en
`main`).

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

`TrunkCIFailed` y `UpdateWatchFailed` dejaron de entrar en Keep (INFRA-882, 16-10): el CI en rojo y
update-watch no son incidentes de producción. Las que quedan son `warning` a propósito: `critical-safety-net` sólo captura
critical/page, así que no solapan con ella ni figuran en su lista de exclusión
(INVARIANTE 1 de `correlation-rules.yaml`), y el carril de Aurora acepta
warning (`docs/keep-aurora-contract.md` §6). El `resolved` lo emite el emisor:
ArgoCD no lo emite y lo resuelve `keepsvc-stale-reaper`; las familias x86 sí lo
emiten, y por eso el reaper no las toca (INFRA-882).

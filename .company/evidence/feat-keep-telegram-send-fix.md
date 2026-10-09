# Evidencia — INFRA-378: el envío de Keep a Telegram

Fecha: 2026-10-09 · Dónde: clúster k3s (`monitoring`), `keep-backend-6c99ffd7dd-mzf4h`, solo lectura.

## 1. Causa raíz — PASS (medida)

`SC-1711` (#79, `eafbf0b`, 2026-10-04T03:17+02:00 = 01:17Z) puso `SCHEDULER=false` en `keep-backend`. En Keep 0.52.1 sin Redis
los workflows de alerta/incidente van por una cola en memoria del proceso que recibe el webhook y solo el
WorkflowScheduler de ESE proceso la vacía: con `false` se encolaban y se perdían.

```
select w.name, x.started, x.status from workflowexecution x join workflow w ... where w.name like 'Telegram%'
 ultimo antes del hueco : 2026-10-04 01:24:47  success   (Telegram — incidentes críticos / incidentes al tema alertas)
 primero despues         : 2026-10-09 15:10:39  success   (Telegram — resúmenes de alertas al tema alertas)
 ejecuciones por dia     : 10-04 x23 · 10-05..10-08 x0 · 10-09 x7 incidentes, x7 criticos, x4 resumenes
```

El arreglo de la causa ya estaba en main: INFRA-751 (#92, `5f48af7`, sync de `k8s-observability` 14:57:38Z, pod
`keep-backend` nuevo a ~14:56Z): `SCHEDULER=true` + `WORKFLOWS_INTERVAL_ENABLED=false`.

## 2. Hipótesis del encargo

| hipótesis | veredicto | evidencia |
|---|---|---|
| (a) workflow enabled, canal/silencio roto | descartada | `workflow` de `notify-alert-summary`: `is_disabled=False`, cargado 10-08 04:36; 4 ejecuciones `success` hoy |
| (b) incidente 9d403a3e suprime el envío | descartada | `9d403a3ef4f43f4e` es el fingerprint de la alerta Brain, no un incidente que absorba; la regla nueva creó `CRON-10205 - BrainIngestConsecutiveFailures en whatsapp-mcp` (10-08 12:25Z) con el alertname en el nombre |
| (c) credencial/origen de Telegram | descartada | `telegram-incident` y `telegram-alert-summary` `ran successfully` a las 15:18 y 15:20Z; el proveedor lanza `ProviderException` si Telegram rechaza |

## 3. Lo que añade esta PR — PASS

`tests/test_infra378_keep_scheduler_split_contract.py` (3 tests) fija el reparto del scheduler; sin él SC-1711 se
deshizo sin que nada lo detectara cinco días. Prueba de que muerde:

```
python3 -m unittest discover -s tests            -> Ran 83 tests ... OK (skipped=15)
python3 scripts/verify-notification-coverage.py  -> exit 0
SCHEDULER "true" -> "false" en keep/values.yaml  -> FAILED (failures=1): keep-backend must run the WorkflowScheduler ...
```

`ARCHITECTURE.md` §8: entrada `2026-10-09` con el reparto, el hueco medido y su test.

## 4. Pendiente medido, no arreglable por GitOps

`CRON-10205 - BrainIngestConsecutiveFailures en whatsapp-mcp` (firing, creado 10-08 12:25Z) nació DENTRO del hueco: su
`created` se perdió y la alerta `9d403a3ef4f43f4e` cambió de estado (12:25 firing, 02:09 suppressed, 03:10 firing) sin
ejecutar el workflow. Con `[created]` y `only_on_change: [status]` solo avisa en el siguiente cambio de estado.

## Criterios (00-spec.md)

- C1 mensaje REAL en topic 1248: no medido como mensaje; sí 18 `workflowexecution` de Telegram `success` posteriores al arreglo (qa lo cierra con la controlada).
- C2 agrupación por `[namespace, alertname]`: medido en vivo (`CRON-10205` lleva el alertname).
- C3 resúmenes en el aviso: 4 ejecuciones de `notify-alert-summary` `success`; texto del mensaje, de qa.
- C4 `verify-notification-coverage.py` exit 0: PASS; CI de esta PR y ArgoCD Synced: tras el merge.
- C5 prueba controlada `t378-test*`: de qa.

Rol: developer · Fecha: 2026-10-02T03:10Z · Sesión: 50026508-ce25-4006-9891-d4ad5b9ddfbb · Estado: LISTO

# INFRA-406 (P3) — entrega

PR: https://github.com/pocharlies-org/k8s-observability-pocharlies/pull/65 (rama `infra-394-p3-aurora-incidente`) · CI run 36949384009.
**NO mergear hasta que devops haya hecho el paso 1.**

## Qué se hizo
- `keep/values.yaml`: `claim-dispatch` reescrito en sitio (PK `keep_incident_id`, `fingerprint` = `substr(md5(keep_incident_id::text),1,16)`, `alert_fingerprint`, `previous_keep_incident_id`, cooldown `interval '6 hours'`, `ON CONFLICT (keep_incident_id)`; los incidentes sin huella ya se despachan). `dispatch-rca` publica `rearmed_from`. `rca-datos`/`link-datos`/`mark-linked` intactos (cruzan por `fingerprint`).
- `docs/keep-aurora-contract.md` → v1.3 reescrito (§1, §2 con migración y rollback, §6 corregido: critical+warning, §8 T3).
- Tests: `tests/test_keep_aurora_dispatch_contract.py` actualizado; nuevo `tests/test_keep_aurora_claim_behavior.py` (ejecuta el SQL del claim y los bloques `-- migracion:*` del contrato contra Postgres 16).
- `ci.yml`: service container `postgres:16` + `psycopg[binary]`; `ARCHITECTURE.md` §2/§4/§6/§7/§8 y fecha.

## Hipótesis de Keep 0.52.1 (un incidente resolved no recoge alertas nuevas): NO MEDIDA
El guard de mi rol denegó `kubectl exec` en `keep-backend` (lectura del código del rules engine). El claim y los tests no dependen de ella, pero el rearme sí: si Keep metiera alertas nuevas en un incidente `resolved`, no habría `created` nuevo y no habría reinvestigación. Medición pendiente para sre/devops (solo lectura): en el pod, leer en `keep/rulesengine/rulesengine.py` si la búsqueda del incidente de la regla filtra por estado `resolved`; o en vivo con `SreDevopsChainProbe`: firing → resolved → firing y comprobar que sale un incidente nuevo (es el paso 3 repetido tras resolver). Si no sale, parar y avisar al architect.

## Tests (local, Postgres 16-alpine desechable)
`AURORA_TEST_PG_DSN=… pytest tests/ -q` → `26 passed, 1 skipped`. Sin DSN: 4 skipped; con `CI=true` y sin DSN: 4 failed (por diseño). `company-duplicados`: sin duplicación nueva.
Postgres en `arc-k8s`: service container elegido; su funcionamiento en el runner se mide en el run 36949384009 (ARCHITECTURE §7 lo dice como no medido hasta entonces; la comparación con apt no se hizo).

## SQL para devops (primario CNPG de postgres-shared, BBDD `aurora`, como `postgres`; no suponer `-1`)
Paso 0 (debe dar 0 filas; si no, parar y no borrar):
```sql
SELECT keep_incident_id, count(*) FROM keep_bridge.aurora_dispatches GROUP BY 1 HAVING count(*) > 1;
```
Paso 1 (expand, antes del merge; `CONCURRENTLY` fuera de transacción, una sentencia cada vez):
```sql
SET lock_timeout = '5s';
ALTER TABLE keep_bridge.aurora_dispatches
  ADD COLUMN IF NOT EXISTS alert_fingerprint text,
  ADD COLUMN IF NOT EXISTS previous_keep_incident_id uuid;
UPDATE keep_bridge.aurora_dispatches SET alert_fingerprint = fingerprint WHERE alert_fingerprint IS NULL;
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS aurora_dispatches_incident_uq ON keep_bridge.aurora_dispatches (keep_incident_id);
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS aurora_dispatches_fp_uq ON keep_bridge.aurora_dispatches (fingerprint);
CREATE INDEX CONCURRENTLY IF NOT EXISTS aurora_dispatches_alertfp_idx ON keep_bridge.aurora_dispatches (alert_fingerprint, dispatched_at DESC);
```
Paso 2: merge del PR; tras el sync repetir el `UPDATE … alert_fingerprint` y comprobar que Keep cargó el workflow (si no, reinicio ordenado de `keep-backend`).
Paso 3: prueba viva `SreDevopsChainProbe` (warning): 1 fila con `fingerprint = substr(md5(keep_incident_id::text),1,16)`, `alert_fingerprint` poblado, `previous_keep_incident_id` NULL; repetida <6 h → sin fila.
Paso 4 (contract, solo tras 3 verde):
```sql
BEGIN; SET LOCAL lock_timeout = '5s';
ALTER TABLE keep_bridge.aurora_dispatches DROP CONSTRAINT aurora_dispatches_pkey;
ALTER TABLE keep_bridge.aurora_dispatches ADD CONSTRAINT aurora_dispatches_pkey PRIMARY KEY USING INDEX aurora_dispatches_incident_uq;
ALTER TABLE keep_bridge.aurora_dispatches ADD CONSTRAINT aurora_dispatches_fingerprint_key UNIQUE USING INDEX aurora_dispatches_fp_uq;
COMMIT;
```
**C3-A (qa)**: `SELECT pg_get_indexdef(indexrelid) FROM pg_index WHERE indrelid='keep_bridge.aurora_dispatches'::regclass AND indisprimary;` contiene `keep_incident_id`, y `SELECT * FROM keep_bridge.aurora_rca_coverage();` sin error.

Rollback: paso 2 → revertir el PR. Paso 4 (antes de revertir el PR):
```sql
BEGIN; SET LOCAL lock_timeout = '5s';
ALTER TABLE keep_bridge.aurora_dispatches DROP CONSTRAINT aurora_dispatches_pkey;
ALTER TABLE keep_bridge.aurora_dispatches DROP CONSTRAINT aurora_dispatches_fingerprint_key;
ALTER TABLE keep_bridge.aurora_dispatches ADD PRIMARY KEY (fingerprint);
CREATE UNIQUE INDEX aurora_dispatches_incident_uq ON keep_bridge.aurora_dispatches (keep_incident_id);
COMMIT;
```
El paso 1 es aditivo, no se deshace. Los bloques están ejecutados en el test (expand idempotente, contract, rollback, `aurora_rca_coverage()` igual antes y después).

## Checklist de 00-spec.md
- [x] C3-B test de comportamiento (rearme, cooldown, ON CONFLICT, migración con filas vivas); falla con `CI=true` sin Postgres. Medición en arc-k8s: pendiente del primer run.
- [x] Test de contrato pincha `ON CONFLICT (keep_incident_id)`, PK + `fingerprint UNIQUE`, `substr(md5(`, `interval '6 hours'`, `rearmed_from`, carril critical+warning.
- [x] Contrato v1.3, ARCHITECTURE §2/§4 y fecha.
- [x] `pytest tests/` verde en local (26 passed). CI verde: pendiente del run.
- [ ] C3-A: lo verifica qa tras el contract (comando arriba).
- [ ] Hipótesis Keep 0.52.1: no medida por permisos (arriba).

## Reutilizado
- Reutilizado: step `claim-dispatch` (reescrito en sitio), `rca-datos`/`link-datos`/`mark-linked` y `aurora_rca_coverage()` sin tocar (`keep/values.yaml`, `docs/keep-aurora-contract.md`); `workflow_block` de `tests/test_keep_aurora_dispatch_contract.py`; el DDL del contrato como fuente de los tests de migración.
- Búsquedas: `rg -n "aurora_dispatches|claim-dispatch|ON CONFLICT" ~/k8s` (sin consumidores fuera del repo); `company-duplicados` → sin duplicación nueva.
- Nuevo y por qué: `tests/test_keep_aurora_claim_behavior.py` (nada ejecutaba el SQL); service container Postgres en `ci.yml` (lo exige C3-B). Sin tabla nueva, sin dual-write, sin cliente de Postgres externo.
- Documento que refleja el cambio: `docs/keep-aurora-contract.md` v1.3 y `ARCHITECTURE.md`. `.company/changes/`: no hace falta (sin consumidores fuera del repo).

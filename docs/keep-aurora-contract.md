# Contrato Keep ↔ Aurora

> Estado: **v1.3** (INFRA-406 / INFRA-394, 2026-10-02): el despacho a Aurora
> pasa de «una vez por huella de alerta» a **una vez por incidente de Keep**
> (clave `keep_incident_id`, rearme = Keep, cooldown de 6 h por huella) y se
> corrige la lane (§6: critical **y warning**). Hereda de v1.2 (INFRA-217,
> 2026-09-23) la cobertura del RCA por la función SECURITY DEFINER
> `keep_bridge.aurora_rca_coverage()` y del prefijo `cnpg_` de las series
> (§7). Este fichero es la referencia del enlace cruzado Keep↔Aurora: qué se
> guarda en cada sitio, con qué clave, quién escribe qué y qué superficie NO se
> puede cambiar sin versionar. Los anclajes son nombres de
> workflow/step/columna, no números de línea (el fichero vive sesiones en
> paralelo).

## 0. Resumen del enlace

| dirección | mecanismo | dónde vive el enlace |
|---|---|---|
| Keep → Aurora (badge «External incident» en el incidente de Keep, clicable a la ficha de Aurora) | workflow `aurora-link` (interval 120): step `link-datos` (solo lectura) + action `link-incident` (`type: mock`, `enrich_incident`) + action `mark-linked` (postgres) | tabla `alertenrichment` de la BBDD `keep` (clave = uuid del incidente de Keep) + columnas `aurora_incident_id`/`linked_at` de `keep_bridge.aurora_dispatches` (BBDD `aurora`) |
| Aurora → Keep (botón «View Alert» en la ficha de Aurora) | campo `generatorURL` de `alerts[0]` del payload de `dispatch-rca` | `alert_metadata.alertUrl` del propio registro de Aurora |

Ninguna de las dos direcciones escribe en tablas del otro sistema más allá del
esquema `keep_bridge` de la BBDD `aurora` (ver §5 dueños).

## 1. La clave de correlación: `keep_incident_id`

- **Una fila por incidente de Keep**: `keep_bridge.aurora_dispatches` tiene
  `keep_incident_id uuid PRIMARY KEY` y el claim es `ON CONFLICT
  (keep_incident_id) DO NOTHING`. La misma ejecución repetida o recibida por
  dos workers gana una sola vez.
- **`fingerprint` = token enviado a Aurora**: `substr(md5(keep_incident_id::text),
  1, 16)` (16 hex, `UNIQUE NOT NULL`). Es lo que Aurora guarda en
  `alert_metadata->>'fingerprint'` (fork `tasks.py`, upsert por `crc32(fp)`) y
  por lo que cruzan `rca-datos`, `link-datos`, `mark-linked` y
  `aurora_rca_coverage()`. Se deriva del incidente, no de la alerta, para que
  cada incidente de Keep tenga su propio incidente de Aurora: con la huella de
  la alerta, un segundo despacho caería sobre el mismo incidente de Aurora
  (upsert) y no sería una investigación nueva. La relación es **1:1** con el
  incidente de Keep. Las filas anteriores a v1.3 conservan su `fingerprint`
  (la huella de alerta de entonces) y `alert_fingerprint = fingerprint`.
- **`alert_fingerprint`** = huella hex de `alerts.0` (limpiada a
  `[0-9A-Fa-f]`), lo que antes era `fingerprint`. Sirve solo para el cooldown y
  para `previous_keep_incident_id`. `NULL` si el incidente no trae alertas con
  huella: **ya no se descartan** (v1.2 exigía `fingerprint IS NOT NULL`); se
  despachan con token de incidente y sin cooldown.
- **Rearme = Keep.** `aurora-investigate` dispara con `events: [created]`, y
  Keep abre un incidente nuevo solo cuando el anterior de esa regla/agrupación
  estaba resuelto. Una alerta recurrente tras resolverse es, por tanto, un
  incidente nuevo → un despacho nuevo, sin consultar el estado de Keep desde la
  BBDD `aurora`. Supuesto medido: un incidente `resolved` no recoge alertas
  nuevas (si las recogiera no habría incidente nuevo y no habría rearme).
- **Cooldown anti-flapping: 6 h** por `alert_fingerprint`
  (`interval '6 hours'` sobre `dispatched_at`). Un incidente nuevo con la
  misma huella dentro de la ventana **no deja fila** y no se despacha; es un
  límite de coste (cada despacho lanza agentes LLM), no una regla funcional.
  La Request de IT del incidente suprimido se cubre por la causa
  (`keep-causa`), no por Aurora.
- **`previous_keep_incident_id`** = último despacho anterior con la misma
  `alert_fingerprint` (`NULL` si es el primero). Viaja a Aurora como anotación
  `rearmed_from: https://keep.e-dani.com/incidents/<prev>` (vacía si no hay),
  vía la GUC `aurora.prev` del claim (`results.0.1`).
- **Trampa desactivada (paso 0 medido, INFRA-231)**: el fingerprint de la
  ALERTA (16 hex) y la clave del enrichment de INCIDENTES son cosas distintas.
  En `alertenrichment`, para incidentes la columna `alert_fingerprint` guarda
  **el uuid del incidente de Keep CON GUIONES y minúsculas** (el GET hace
  `cast(incident.id, String) == alert_fingerprint`; los 6759 incidentes vivos
  tienen `fingerprint=''`). Si el workflow pasara el hex, la fila se escribiría
  pero el GET del incidente jamás la encontraría (badge invisible) y colisionaría
  con el espacio de alertas. Por eso `link-incident` recibe
  `fingerprint: "{{ steps.link-datos.results.0.0 }}"` (el uuid), y el hex viaja
  solo en el `WHERE` de `mark-linked`.

## 2. Las dos tablas puente (esquema `keep_bridge`, BBDD `aurora`)

Nadie crea este esquema automáticamente: ni Keep migra en la base de Aurora ni
las migraciones de Aurora (de un tercero) pueden tocarlo. El DDL de bootstrap
vive en `keep/values.yaml` (comentario del workflow `aurora-report-back` y step
`claim-dispatch`) y hay que rehacerlo si la BBDD se recrea desde cero. Las
tablas recreadas vía `claim-dispatch` nacen ya completas; sobre una BBDD viva
los cambios de esquema van con ALTER a mano, nunca en el camino caliente del
dispatch (lock exclusivo).

### `keep_bridge.reported` — marca de «publicado en Telegram»

```sql
CREATE SCHEMA IF NOT EXISTS keep_bridge;
CREATE TABLE IF NOT EXISTS keep_bridge.reported (
  fingerprint text PRIMARY KEY,
  reported_at timestamptz NOT NULL DEFAULT now()
);
```

### `keep_bridge.aurora_dispatches` — reclamación del despacho

```sql
CREATE TABLE IF NOT EXISTS keep_bridge.aurora_dispatches (
  keep_incident_id uuid PRIMARY KEY,
  fingerprint text NOT NULL UNIQUE,   -- token enviado a Aurora (§1)
  alert_fingerprint text,             -- huella hex de alerts.0
  previous_keep_incident_id uuid,     -- despacho anterior de esa huella
  dispatched_at timestamptz NOT NULL DEFAULT now(),
  aurora_incident_id uuid,            -- enlace Keep->Aurora (P-A)
  linked_at timestamptz               -- cuándo se escribió el badge
);
CREATE INDEX IF NOT EXISTS aurora_dispatches_alertfp_idx
  ON keep_bridge.aurora_dispatches (alert_fingerprint, dispatched_at DESC);
```

- `dispatched_at`: momento del claim; el cooldown, la ventana de enlace
  (`aurora-link`) y la ventana de cobertura (§7) se miden sobre él.
- `aurora_incident_id`/`linked_at`: los escribe **solo** la action
  `mark-linked` del workflow `aurora-link` (`WHERE fingerprint = … AND
  aurora_incident_id IS NULL` → idempotente, un enlace por despacho).

#### Migración v1.2 → v1.3 (expand → deploy → contract)

Sin tabla nueva ni dual-write. Cada paso es compatible con el workflow viejo y
con el nuevo. El DDL lo ejecuta **devops** contra el primario CNPG de
`postgres-shared` como `postgres` (localizar el primario por la etiqueta
`role=primary`, no suponer un número); los bloques marcados
`-- migracion:*` los extrae `tests/test_keep_aurora_claim_behavior.py` y los
prueba contra un Postgres desechable con filas v1.2 vivas.

0. **Pre-chequeo** — debe dar 0 filas; si no, parar y no borrar nada:

```sql
-- migracion:precheck
SELECT keep_incident_id, count(*) FROM keep_bridge.aurora_dispatches
 GROUP BY 1 HAVING count(*) > 1;
```

1. **Expand** (en línea, antes del merge; aditivo, no se deshace):

```sql
-- migracion:expand
SET lock_timeout = '5s';
ALTER TABLE keep_bridge.aurora_dispatches
  ADD COLUMN IF NOT EXISTS alert_fingerprint text,
  ADD COLUMN IF NOT EXISTS previous_keep_incident_id uuid;
UPDATE keep_bridge.aurora_dispatches SET alert_fingerprint = fingerprint
 WHERE alert_fingerprint IS NULL;
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS aurora_dispatches_incident_uq
  ON keep_bridge.aurora_dispatches (keep_incident_id);
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS aurora_dispatches_fp_uq
  ON keep_bridge.aurora_dispatches (fingerprint);
CREATE INDEX CONCURRENTLY IF NOT EXISTS aurora_dispatches_alertfp_idx
  ON keep_bridge.aurora_dispatches (alert_fingerprint, dispatched_at DESC);
```

2. **Deploy**: merge del PR (ArgoCD `keep`); comprobar que Keep cargó el
   workflow nuevo y re-ejecutar el `UPDATE … alert_fingerprint` del paso 1
   (cubre filas que el workflow viejo insertó en la ventana).
3. **Prueba viva**: `SreDevopsChainProbe` (warning) → una fila con
   `fingerprint = substr(md5(keep_incident_id::text),1,16)`,
   `alert_fingerprint` poblado y `previous_keep_incident_id` NULL; repetida
   dentro de 6 h → sin fila nueva.
4. **Contract** (solo tras 3 verde):

```sql
-- migracion:contract
BEGIN;
SET LOCAL lock_timeout = '5s';
ALTER TABLE keep_bridge.aurora_dispatches DROP CONSTRAINT aurora_dispatches_pkey;
ALTER TABLE keep_bridge.aurora_dispatches
  ADD CONSTRAINT aurora_dispatches_pkey PRIMARY KEY USING INDEX aurora_dispatches_incident_uq;
ALTER TABLE keep_bridge.aurora_dispatches
  ADD CONSTRAINT aurora_dispatches_fingerprint_key UNIQUE USING INDEX aurora_dispatches_fp_uq;
COMMIT;
```

   Comprobación (C3-A): `SELECT pg_get_indexdef(indexrelid) FROM pg_index
   WHERE indrelid = 'keep_bridge.aurora_dispatches'::regclass AND indisprimary;`
   contiene `keep_incident_id`, y `SELECT * FROM
   keep_bridge.aurora_rca_coverage();` no da error.

**Rollback.** Paso 2: revertir el PR (el workflow viejo hace `ON CONFLICT
(fingerprint)`, que resuelve contra el PK o el UNIQUE; las filas con token son
inocuas). Paso 4 (antes de revertir el PR):

```sql
-- migracion:rollback-contract
BEGIN;
SET LOCAL lock_timeout = '5s';
ALTER TABLE keep_bridge.aurora_dispatches DROP CONSTRAINT aurora_dispatches_pkey;
ALTER TABLE keep_bridge.aurora_dispatches DROP CONSTRAINT aurora_dispatches_fingerprint_key;
ALTER TABLE keep_bridge.aurora_dispatches ADD PRIMARY KEY (fingerprint);
CREATE UNIQUE INDEX aurora_dispatches_incident_uq
  ON keep_bridge.aurora_dispatches (keep_incident_id);
COMMIT;
```

Si el despliegue falla a medias nunca queda «sin investigar» (el claim viejo
funciona hasta el contract); lo peor es una reinvestigación, acotada por el
cooldown.

### Cobertura del RCA: la función `keep_bridge.aurora_rca_coverage()` (v1.2)

Premisa del diseño corregida por la medición en vivo (v1.1): las consultas del
exporter **no corren como `postgres` con `pg_monitor`**; corren como el rol
`cnpg_metrics_exporter`, sin `BYPASSRLS`, y `incidents` tiene RLS
(`select_by_org`). La respuesta de v1.1 —GRANT SELECT sobre `incidents` +
política `USING (true)`— **se retira en v1.2** (revisión del architect,
nota-cto-revision-prs-infra217.md): `cnpg_metrics_exporter` es el rol con el
que corren **todas** las consultas a medida de `postgres-shared` en cualquier
BBDD, y una política `USING (true)` sobre `incidents` le daría filas completas
de todas las orgs —el payload de las alertas y los resúmenes, no dos
contadores—, exposible además a cualquier ConfigMap futuro. La lectura va
desde v1.2 por una función SECURITY DEFINER en nuestro esquema que devuelve
solo los agregados. DDL manual (BBDD `aurora`, contra el primario CNPG como
`postgres`; la ejecuta el operador):

```sql
CREATE OR REPLACE FUNCTION keep_bridge.aurora_rca_coverage()
  RETURNS TABLE (dispatched bigint, without_rca bigint)
  LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public
AS $$ SELECT count(*), count(*) FILTER (WHERE c.fp IS NULL)
    FROM keep_bridge.aurora_dispatches d
    LEFT JOIN (SELECT DISTINCT alert_metadata->>'fingerprint' AS fp FROM public.incidents
                WHERE source_type='grafana' AND aurora_status='complete') c ON c.fp = d.fingerprint
   WHERE d.dispatched_at <= now()-interval '4 hours' AND d.dispatched_at > now()-interval '28 hours' $$;
ALTER FUNCTION keep_bridge.aurora_rca_coverage() OWNER TO postgres;
REVOKE ALL ON FUNCTION keep_bridge.aurora_rca_coverage() FROM PUBLIC;
GRANT USAGE ON SCHEMA keep_bridge TO cnpg_metrics_exporter;
GRANT EXECUTE ON FUNCTION keep_bridge.aurora_rca_coverage() TO cnpg_metrics_exporter;
```

- El dueño es `postgres` (superusuario), así que la función **salta la RLS de
  `incidents` sin tocar `incidents`**: ningún GRANT ni política sobre una tabla
  de tercero (§5).
- **No crea dependencias** sobre `incidents`, así que no bloquea las
  migraciones de Aurora — la misma razón por la que no hay vistas (§5).
- Sigue el **patrón de DDL manual de `keep_bridge`** que documenta este §2:
  DDL a mano sobre la BBDD viva, nunca en el camino caliente del dispatch.

El predicado de «análisis completo» y la ventana (de 4 a 28 h sobre
`dispatched_at`) viven ahora dentro de la función; los fijó el tech-lead con
la medida F1 (§7). La consulta del exporter pasa a ser
`SELECT dispatched, without_rca FROM keep_bridge.aurora_rca_coverage()` y las
series no cambian de nombre.

- **Orden de merge (corregido por el architect)**: este PR (#43) → aplicar la
  DDL de la función → PR 158 → confirmar las series
  `cnpg_aurora_rca_coverage_*` en vmsingle → PR 44. La DDL antes que el PR 158
  evita errores de consulta del exporter en el intervalo.
- **Auto-monitorización (rectificada en v1.2)**: se retira la frase de v1.1
  según la cual `AuroraRcaCoverageAbsent` detectaría la pérdida de la
  política: era falsa. Con GRANT+policy, perdida la política la consulta no
  fallaba — devolvía 0 filas, `without_rca` igualaba a `dispatched` y saltaba
  `AuroraRcaCoverageLow` **en falso**, no `Absent`. Con la función ese modo de
  fallo no existe (no hay política que perder); si el rol perdiera EXECUTE, la
  consulta daría error y la serie faltaría — eso sí lo cubre `Absent`.

## 3. Los dos formatos de deep-link

- Aurora: `https://aurora.e-dani.com/incidents/<uuid-id-de-Aurora>` — es el
  `incident_url` del badge «External incident» y el enlace del mensaje de
  Telegram de `aurora-report-back`. El `FRONTEND_URL` de Aurora es
  **`aurora.e-dani.com`**, no `aurora.lan`.
- Keep: `https://keep.e-dani.com/incidents/<uuid-id-de-Keep>` — es la
  `generatorURL` del dispatch, que Aurora expone como `alert.metadata.alertUrl`
  y `IncidentCard.tsx` pinta como «View Alert».
- Los ids de incidente de Keep **son UUID**, no fingerprints: cualquier enlace
  a Keep se construye con `{{ incident.id }}`.

## 4. Reglas de lectura/escritura contra la BBDD `aurora`

- **RLS**: quien lea `incidents` (o cualquier tabla con políticas) con el rol
  `aurora` —el del provider `aurora_db`— debe fijar antes
  `set_config('myapp.current_org_id', (SELECT id::text FROM organizations
  ORDER BY created_at LIMIT 1), false)`. Si no, obtiene **0 filas sin error**
  (falso vacío). El prólogo va en el propio `query:` de cada step que lea
  `incidents` (`rca-datos`, `link-datos`).
- **Los steps de Keep NO commitean; las actions sí** (vía `_notify`). Escribir
  dentro de un step es lo que tumbó el sistema de alertas en julio de 2026
  (reclamación+lectura en la misma sentencia de un step): por eso `link-datos`
  es estrictamente solo lectura y las dos escrituras del enlace son actions.
  `claim-dispatch` es la excepción documentada: step con `COMMIT` explícito
  para ganar la carrera entre workers.
- **Sanitizado `keep.` → `Keep.`**: IOHandler busca el literal `keep.` en el
  texto ya sustituido y lo trata como llamada de plantilla. Cualquier texto que
  pueda contenerlo (títulos, evidencia) se desinfecta con
  `regexp_replace(…, 'keep\.', 'Keep.', 'g')` antes de salir del step.

## 5. Dónde vive cada enlace y quién es el dueño

- **Badge Keep→Aurora**: una fila en `alertenrichment` (BBDD `keep`),
  `tenant_id='keep'`, `alert_fingerprint` = uuid del incidente de Keep con
  guiones, UNIQUE `(tenant_id, alert_fingerprint)`; el JSON de `enrichments`
  lleva las claves exactas `incident_id` (uuid de Aurora con guiones),
  `incident_url` y `incident_title` (sin `incident_provider`: la UI pediría un
  icono inexistente). El enrich hace merge de claves: re-ejecutar es
  idempotente. La lectura del incidente fusiona esos campos en el DTO, y por
  eso el badge se pinta desde `incident.incident_url`.
- **Marca de enlace**: `keep_bridge.aurora_dispatches.aurora_incident_id` +
  `linked_at` (dueño: `mark-linked`).
- **Backlink Aurora→Keep**: `alert_metadata.alertUrl` del incidente de Aurora,
  alimentado por `generatorURL` del dispatch. Dueño: el propio registro de
  Aurora; no escribimos en tablas de un tercero. **Solo despachos nuevos**: los
  anteriores a este cambio no se rellenan.
- **`keep_bridge.reported` es de `aurora-report-back` y significa «enviado al
  tema 1248 de Telegram», NO «RCA listo».**
- **Nadie escribe en `public.*` de Aurora** desde Keep: el esquema propio de
  Aurora es territorio de sus migraciones (tercero).
- **Nada de vistas sobre `incidents`**: bloquearían las migraciones de Aurora.
- El contenido del RCA vive en `incidents.aurora_summary`,
  `incident_thoughts` y `execution_steps`; la tabla `rca_findings` existe en el
  esquema de Aurora pero está **sin usar** (no la leas ni la escribas).

## 6. La lane de despacho: `critical` y `warning`

El dispatch a Aurora (`aurora-investigate`) está doblemente acotado a
severidad `critical` o `warning` (desde el 29-09-2026: el agente sre-devops de
Hermes se alimenta solo por Keep → Aurora; v1.2 decía «solo critical», lo que
era falso desde esa fecha). Defensas independientes, pinadas por `tests/`:

1. SQL: `WHERE '{{ incident.severity }}' IN ('critical', 'warning')` **antes**
   del claim, para que un info/low no deje ni marca en `aurora_dispatches` (si
   después se eleva, sí puede despacharse).
2. Action: `if: "('{{ incident.severity }}' == 'critical' or '{{
   incident.severity }}' == 'warning') and '{{ steps.claim-dispatch.results.0.0
   }}' != ''"` — el resultado vacío del claim significa «otra ejecución ya lo
   reclamó» o «suprimido por el cooldown».

`aurora-link` hereda esta lane por transitividad: solo enlaza filas que dejó el
claim, y solo las de las últimas 72 h con `aurora_incident_id IS NULL`.

## 7. Métricas y alertas de cobertura (C3, P-B — nombres fijados aquí)

- Consulta del exporter CNPG sobre `keep_bridge.aurora_dispatches` (cuenta
  **despachos**, no incidentes), ventana `dispatched_at` de 4 a 28 h:
  métricas `cnpg_aurora_rca_coverage_dispatched` y
  `cnpg_aurora_rca_coverage_without_rca` (nombre base de la consulta
  `aurora_rca_coverage`, `target_databases: [aurora]`, `primary: true`).
  **v1.1: el nombre medido en vivo manda sobre el nombre base del diseño.** El
  exporter compone `<collector>_<query>_<column>` con collector fijo `cnpg`
  (operador 1.29.1, `internal/management/controller/instance_controller.go:1022`;
  verificado en vivo: las consultas por defecto salen como
  `cnpg_backends_total`), así que las series reales llevan prefijo `cnpg_`.
  Las etiquetas (`instance`, etc.) siguen sin fijarse aquí; se confirman en
  vmsingle tras el despliegue.
- Alertas vmalert (VMRule en `manifests/rules.yaml`, severidad **`warning`**):
  `AuroraRcaCoverageLow` (proporción `without_rca / clamp_min(dispatched, 1)`
  sobre umbral, `dispatched >= 3`, `for: 30m`) y `AuroraRcaCoverageAbsent`
  (`absent()` de la serie con prefijo `cnpg_`, 30m — las expresiones de las
  dos reglas usan los nombres `cnpg_aurora_rca_coverage_*`). `warning` y no
  `critical` a propósito: con
  `critical` la regla `critical-safety-net` las convertiría en incidente y
  `aurora-investigate` despacharía «Aurora está rota» a la propia Aurora.
- Enrutado: matcher «FALLOS SILENCIOSOS DE PROCESAMIENTO» de Alertmanager
  (Telegram `backstop-telegram`, sin pasar por Keep) + Keep con regla de
  correlación `name.startsWith("Aurora")`. La evaluación no puede morir con
  Keep: la hace vmalert y la entrega Alertmanager.

## 8. Provisiones para la futura épica del canal Telegram (no se construye aquí)

- **T1.** La unidad de ciclo de vida es `keep_incident_id`. El mapa
  topic↔incidente vive en el almacén del adapter (synapse), no en
  `keep_bridge`.
- **T2.** La deduplicación entre Keep y el Alertmanager directo va por el
  fingerprint de Alertmanager. Que coincida con el de Keep es una hipótesis que
  esa épica tiene que medir.
- **T3.** Rearmar las alertas recurrentes **ya está resuelto en v1.3** (§1:
  clave `keep_incident_id`, rearme = Keep, cooldown de 6 h). Cualquier cambio
  posterior de la PK o del cooldown es de nuevo un cambio de contrato
  versionado.
- **T4.** «RCA listo» hoy solo se sabe consultando la BBDD. Un evento sería una
  entrada nueva `.v1` en `CONTRACTS.yaml` de synapse.
- **T5.** El RCA que escribe report-back no se guarda en ningún sitio: solo va
  a Telegram. El botón de sesión necesitará persistirlo en su propio almacén.

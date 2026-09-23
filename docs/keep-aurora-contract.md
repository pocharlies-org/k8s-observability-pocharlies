# Contrato Keep ↔ Aurora

> Estado: **v1.1** (INFRA-217 P-A, 2026-09-23; corregido post-qa el mismo día
> tras la medición en vivo de P-B: las series del exporter salen con prefijo
> `cnpg_` y hacen falta grants/policy manuales para el rol del exporter — ver
> §2 y §7). Escrito desde
> `nota-cto-diseno-keep-aurora.md` (punto 4) + su lista F4. Este fichero es la
> referencia del enlace cruzado Keep↔Aurora: qué se guarda en cada sitio, con
> qué clave, quién escribe qué y qué superficie NO se puede cambiar sin
> versionar. Los anclajes son nombres de workflow/step/columna, no números de
> línea (el fichero vive sesiones en paralelo).

## 0. Resumen del enlace

| dirección | mecanismo | dónde vive el enlace |
|---|---|---|
| Keep → Aurora (badge «External incident» en el incidente de Keep, clicable a la ficha de Aurora) | workflow `aurora-link` (interval 120): step `link-datos` (solo lectura) + action `link-incident` (`type: mock`, `enrich_incident`) + action `mark-linked` (postgres) | tabla `alertenrichment` de la BBDD `keep` (clave = uuid del incidente de Keep) + columnas `aurora_incident_id`/`linked_at` de `keep_bridge.aurora_dispatches` (BBDD `aurora`) |
| Aurora → Keep (botón «View Alert» en la ficha de Aurora) | campo `generatorURL` de `alerts[0]` del payload de `dispatch-rca` | `alert_metadata.alertUrl` del propio registro de Aurora |

Ninguna de las dos direcciones escribe en tablas del otro sistema más allá del
esquema `keep_bridge` de la BBDD `aurora` (ver §5 dueños).

## 1. La clave de correlación: `fingerprint`

- Es el fingerprint de la **primera alerta del incidente** (`alerts.0`),
  limpiado a hexadecimal (solo `[0-9A-Fa-f]`) por el step `claim-dispatch` del
  workflow `aurora-investigate`. Keep lo manda así; Aurora lo guarda tal cual
  en `alert_metadata->>'fingerprint'` (fork `tasks.py`, sha e35121ae, upsert
  por `crc32(fp)`). La relación es **1:1**.
- **A lo sumo un despacho por fingerprint**: `keep_bridge.aurora_dispatches`
  tiene `fingerprint text PRIMARY KEY` y el claim es `ON CONFLICT DO NOTHING`.
  **Sin rearme**: un fingerprint ya despachado no vuelve a Aurora hasta que un
  operador borre la fila a mano. Consecuencia conocida: si Keep abre un
  segundo incidente para la misma alerta recurrente, ese segundo incidente no
  se despacha ni se enlaza (limitación dictada en el diseño, §6).
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
  fingerprint text PRIMARY KEY,
  keep_incident_id uuid NOT NULL,
  dispatched_at timestamptz NOT NULL DEFAULT now(),
  aurora_incident_id uuid,          -- nuevo (P-A): enlace Keep->Aurora
  linked_at timestamptz             -- nuevo (P-A): cuándo se escribió el badge
);
```

El ALTER para una BBDD viva ya aplicada (2026-09-23, primario CNPG
`postgres-shared-3`, verificado por `information_schema.columns`):

```sql
ALTER TABLE keep_bridge.aurora_dispatches
  ADD COLUMN IF NOT EXISTS aurora_incident_id uuid,
  ADD COLUMN IF NOT EXISTS linked_at timestamptz;
```

- `dispatched_at`: momento del claim; la ventana de enlace (`aurora-link`) y la
  ventana de cobertura (métricas, §7) se miden sobre él.
- `aurora_incident_id`/`linked_at`: los escribe **solo** la action
  `mark-linked` del workflow `aurora-link` (`WHERE fingerprint = … AND
  aurora_incident_id IS NULL` → idempotente, un enlace por despacho).

### Permisos de lectura del exporter CNPG (v1.1, medido por P-B)

Premisa del diseño corregida por la medición en vivo: las consultas del
exporter **no corren como `postgres` con `pg_monitor`**; corren como el rol
`cnpg_metrics_exporter`, sin `BYPASSRLS`, y `incidents` tiene RLS
(`select_by_org`). Sin estos permisos la consulta de cobertura no ve filas.
DDL manual (BBDD `aurora`, contra el primario CNPG como `postgres`; la aprueba
el tech-lead y la ejecuta el operador):

```sql
GRANT USAGE ON SCHEMA keep_bridge TO cnpg_metrics_exporter;
GRANT SELECT ON keep_bridge.aurora_dispatches TO cnpg_metrics_exporter;
GRANT SELECT ON incidents TO cnpg_metrics_exporter;
CREATE POLICY cnpg_metrics_coverage_read ON incidents
  FOR SELECT TO cnpg_metrics_exporter USING (true);
```

- **Orden de merge (P-B)**: PR 158 → ejecutar esta DDL → confirmar que las
  series `cnpg_aurora_rca_coverage_*` aparecen en vmsingle → PR 44.
- Aditiva y solo lectura. Con esta policy el exporter no necesita el prólogo
  `myapp.current_org_id` de §4: la policy es `FOR SELECT TO
  cnpg_metrics_exporter USING (true)`, así que para ese rol `incidents` ya
  devuelve filas sin fijar el org.
- **Auto-monitoreo**: si una migración futura de Aurora borrara la policy, la
  serie desaparece y `AuroraRcaCoverageAbsent` (§7) la detecta por sí sola; no
  hace falta un watchdog aparte.

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
- **La policy `cnpg_metrics_coverage_read` (§2) es la única DDL que aplicamos
  sobre una tabla de tercero (`incidents`), y es solo lectura**: `FOR SELECT`
  con `USING (true)` para el rol del exporter; no abre escritura ni cambia lo
  que ven los demás roles.
- El contenido del RCA vive en `incidents.aurora_summary`,
  `incident_thoughts` y `execution_steps`; la tabla `rca_findings` existe en el
  esquema de Aurora pero está **sin usar** (no la leas ni la escribas).

## 6. La lane de despacho: solo `critical`

El dispatch a Aurora (`aurora-investigate`) está doblemente acotado a severidad
`critical` (defensas independientes, pinadas por `tests/`):

1. SQL: `WHERE '{{ incident.severity }}' = 'critical'` **antes** del claim,
   para que un warning/info no deje ni marca en `aurora_dispatches` (si después
   se eleva a critical, sí puede despacharse).
2. Action: `if: "'{{ incident.severity }}' == 'critical' and '{{ steps.
   claim-dispatch.results.0.0 }}' != ''"` — el resultado vacío del claim
   significa «otra ejecución ya lo reclamó».

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
- **T3.** Rearmar las alertas recurrentes es un cambio de contrato versionado
  (tabla o columna nueva), nunca reinterpretar la PK.
- **T4.** «RCA listo» hoy solo se sabe consultando la BBDD. Un evento sería una
  entrada nueva `.v1` en `CONTRACTS.yaml` de synapse.
- **T5.** El RCA que escribe report-back no se guarda en ningún sitio: solo va
  a Telegram. El botón de sesión necesitará persistirlo en su propio almacén.

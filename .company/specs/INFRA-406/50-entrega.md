Rol: developer · Fecha: 2026-10-02T11:45Z · Sesión: 08da28b5-de77-421e-9542-55f8ec0a07de · Estado: LISTO

# INFRA-406 — fix de producción tras #65 (iohandler y el literal `keep.`)

Defecto: el iohandler de Keep 0.52.1 (`iohandler.py:118`) escanea el SQL ya renderizado de un step, toma `keep.…` por una llamada de plantilla y el run acaba en `SyntaxError`. Lo disparaba la URL `https://keep.e-dani.com/incidents/` dentro del `set_config('aurora.prev', …)` de `claim-dispatch` (20 ejecuciones en error tras el merge de #65).

PR: ver el PR nuevo de la rama `infra-394-p3-fix-iohandler` (contra main 9bb6e64). No mergeado; lo pulsa el CTO. No toca `keep/rules/*`.

## Cambio
- `keep/values.yaml`, `claim-dispatch`: la URL se compone troceada (`'https://' || 'keep' || '.e-dani.com/incidents/' || previous_keep_incident_id::text`). El literal `keep.` ya no aparece en el SQL; `rearmed_from` se publica igual (misma URL). Comentario con la regla.
- Clase del fallo: recorrido programático de TODOS los steps y actions con `query:` de TODOS los workflows de `keep/values.yaml`; `claim-dispatch` era el único con el literal en SQL. Los mensajes de Telegram y los cuerpos de webhook que llevan la URL entera no son SQL y llevan tiempo funcionando.
- `docs/keep-aurora-contract.md` §4: regla nueva «ninguna cadena con el literal `keep.` dentro del SQL de un step» (literales y comentarios `--`), con el fallo real.
- Tests: `KeepIohandlerLiteralTests` en `tests/test_keep_aurora_dispatch_contract.py` (falla si cualquier `query:` de cualquier workflow contiene `keep.`; y que el claim sigue construyendo la URL y `rearmed_from`). El test de comportamiento contra Postgres sigue comprobando `prev == https://keep.e-dani.com/incidents/<a>`.

## Verificación
`CI=true AURORA_TEST_PG_DSN=… pytest tests/ -q` contra Postgres 16-alpine desechable → 35 passed, 1 skipped (promtool).
No verificado: el run real en Keep tras el despliegue (el iohandler no se puede ejecutar en local). Tras el merge y el sync, devops comprueba que `aurora-investigate` deja de dar error en la siguiente ejecución.

## Checklist
- [x] Literal `keep.` fuera del SQL; `rearmed_from` igual.
- [x] Test de contrato de la regla; tests de comportamiento verdes.
- [x] Regla anotada en el contrato.
- [ ] Ejecución en producción sin error: la verifica devops/qa tras el sync.

## Reutilizado
- Reutilizado: `workflow_block` y el patrón de extracción de `claim_sql()` de los tests de P3; sin tablas ni ficheros nuevos.
- Búsquedas: recorrido yaml de todos los `query:` de `keep/values.yaml` buscando `keep.`.
- Nuevo: solo la clase de test y la regla en el contrato (necesarias para la clase del fallo).
- Documento actualizado: `docs/keep-aurora-contract.md` §4.

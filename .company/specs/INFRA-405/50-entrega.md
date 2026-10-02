Rol: devops · Fecha: 2026-10-02T01:25Z · Sesión: d4b42739-90cb-4d56-a5a3-ed27e3e1d110 · Estado: LISTO

# INFRA-405 (P2) — entrega

## Hecho

- `keep/rules/correlation-rules.yaml`: 3 reglas nuevas (patrón `argocd-app-degraded`, `createOn: any`, `resolveOn: all_resolved`, sección «X86 — host fuera del clúster»):
  - `x86-unit-failed` — `name == "X86UnitFailed"`, grouping `[unit]`, 1800 s, prefijo X86U, `"x86: {{ unit }} fallida"`
  - `trunk-ci-failed` — `name == "TrunkCIFailed"`, grouping `[repo]`, 1800 s, prefijo CI, `"CI en rojo: {{ repo }}"`
  - `update-watch-failed` — `name == "UpdateWatchFailed"`, grouping `[fail_reason]`, 3600 s, prefijo UPD, `"Actualización fallida: {{ fail_reason }}"`
- `tests/test_infra405_correlation_rules.py` (nuevo, hermético): exige las 3 reglas con su grouping/timeframe/prefijo/lifecycle, que sobrevivan la expansión de `chronic` (invariante 2 del apply-job), que ningún nombre esté en la lista crónica, que con severidad `warning` no solapen ni figuren en la exclusión del `critical-safety-net`, y que el `incidentNameTemplate` lleve sólo la etiqueta de agrupación sin números volátiles (clave de causa de P4).
- `docs/alert-routing-matrix.md`: sección «Fuera del árbol: empujadas directo a Keep» con las 4 familias que entran por `POST /alerts/event` (ArgoCD + las 3 x86). No son VMRules: el generador no las conoce.
- No se toca `keep/values.yaml` (no hizo falta), ni `synapse-webhook`, ni `apply-job.yaml` (aplica el fichero tal cual, idempotente).

## PR

- https://github.com/pocharlies-org/k8s-observability-pocharlies/pull/67 (rama `infra-394-p2-reglas` → `main`, commit b24c7e3)
- CI run: 36950345120 (workflow CI, en marcha al entregar)

## Comprobaciones (local, x86, rama)

```
$ python3 -m pytest tests/ -q
21 passed, 1 skipped in 0.18s

$ KUBECONFIG=~/.kube/config python3 scripts/verify-notification-coverage.py
reglas de correlación: 31
series que pasan a notificar y hoy están ciegas: 89
✅ ninguna regresión (8 silencios deliberados)
```

## Verificación C2 (tras merge + sync de ArgoCD `keep`, que lanza el hook PostSync apply-job)

El marcador de prueba viaja dentro de `fail_reason`, que es el nombre del incidente:

```sh
KEY=$(kubectl -n monitoring get secret keepsvc-provisioning -o jsonpath='{.data.API_KEY_PROVISIONER}' | base64 -d)
for sys in srv-a srv-b; do
  curl -s -X POST https://keep.e-dani.com/alerts/event \
    -H "x-api-key: $KEY" -H 'Content-Type: application/json' \
    -d "{\"name\":\"UpdateWatchFailed\",\"severity\":\"warning\",\"fingerprint\":\"infra405c2$sys\",\"system\":\"$sys\",\"fail_reason\":\"prueba-infra405:comun\",\"description\":\"prueba C2 INFRA-405 (borrar tras probar)\",\"source\":\"x86\"}"
done
# tras unos segundos:
curl -s -H "x-api-key: $KEY" "https://keep.e-dani.com/incidents?limit=100" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); items=d.get('items',d if isinstance(d,list) else []); print(sum(1 for i in items if 'prueba-infra405' in str(i.get('name') or i.get('user_generated_name') or '')))"
# esperado: 1  (dos alertas, mismo fail_reason, distinto system -> UN incidente)
# limpiar: repetir los dos POSTs con "status":"resolved" -> el incidente se resuelve (resolveOn: all_resolved)
```

## Checklist del 00-spec

- [x] Las 3 reglas existen con el grouping/timeframe de arriba; ninguna cae en `chronic`; ninguna coincide con la exclusión del safety-net (severidad warning). Test automatizado en `tests/`.
- [ ] C2: dos alertas sintéticas misma familia, igual `fail_reason`, distinto `system` → 1 incidente — **se verifica tras el merge y el apply-job** (instrucciones arriba; lo ejecuta quien haga la verificación en producción, qa en P5).
- [x] `python3 scripts/verify-notification-coverage.py` en verde; `python3 -m pytest tests/ -q` verde.
- [x] Documentación: matriz de rutas actualizada.

## Reutilizado

- Patrón `argocd-app-degraded` del propio `keep/rules/correlation-rules.yaml` (forma de regla, sqlQuery mínimo, `timeUnit: minutes`) — copiado, no reimplementado.
- `keep/rules/apply-job.yaml` sin tocar: la composición de `chronic` (invariante 2) ya envuelve las reglas nuevas solas.
- `scripts/verify-notification-coverage.py`: el test importa su `compose()` y `cel_matches()` vía importlib en vez de duplicar la lógica CEL (evita deriva entre test y gate).
- Estilo de test de `tests/test_keep_aurora_dispatch_contract.py` (unittest hermético que pincha YAML).
- Buscado: `rg -n "X86UnitFailed|TrunkCIFailed|UpdateWatchFailed"` en el repo → 0 hits (las familias las crea P1 en x86-host-runtime); no había nada que reutilizar para ellas. Nuevo: las 3 entradas de regla, el test y la sección de matriz.

## Reanudar

Sesión CTO: d4b42739-90cb-4d56-a5a3-ed27e3e1d110 · Agente: devops (P2) · Worktree: ~/compania/dev/INFRA-394-devops-p2 · Rama: infra-394-p2-reglas

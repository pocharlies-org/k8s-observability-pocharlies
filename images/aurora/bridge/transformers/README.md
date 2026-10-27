# Puente t2v-transformers (SC-2708)

El chart `aurora-oss` 1.2.16 hardcodea la imagen
`cr.weaviate.io/semitechnologies/transformers-inference:sentence-transformers-all-MiniLM-L6-v2`
(tag mutable, sin override por values). Su build del 23-09-2026 (digest
`sha256:75359f8b…`) deja el modelo `/app/models/model/model.safetensors` en
`0600 root:root`; el despliegue de Aurora corre como uid 1000 y el vectorizer
no puede abrirlo (safetensors lo reporta como `FileNotFoundError`). El pod cae
en bucle y arrastra a weaviate —que espera su `/.well-known/ready`— y al
CronJob `aurorasvc-brain-kb-sync` (incidente Keep DEPL-15370, 2026-10-27).

Este Dockerfile añade una sola capa de permisos (`chmod -R a+rX` sobre los
modelos); no cambia contenido ni versión.

## Construir y subir (x86, amd64 — el deployment va con nodeSelector a sauvage)

```bash
docker build --platform linux/amd64 -t \
  ghcr.io/pocharlies-org/transformers-inference:sentence-transformers-all-MiniLM-L6-v2-r1 .
docker push ghcr.io/pocharlies-org/transformers-inference:sentence-transformers-all-MiniLM-L6-v2-r1
```

ghcr.io/pocharlies-org es el registry de los puentes de Aurora (INFRA-326):
público y ya accesible desde sauvage. Harbor `homelab` no sirve aquí: es
privado y sauvage no tiene credenciales para él.

## Cómo se engancha

El chart no permite fijar la imagen, así que la sustitución la hace la política
Kyverno `aurora-t2v-image-mirror` (platform/kyverno/policies.yaml en
k8s-infra-pocharlies): reescribe la imagen en admisión del pod. El Deployment
conserva la imagen del chart y ArgoCD sigue Synced.

## Verificación

```bash
kubectl get pod -n aurora -l app.kubernetes.io/name=aurora-oss-t2v-transformers \
  -o jsonpath='{.items[0].spec.containers[0].image}'   # → ghcr.io/pocharlies-org/…-r1
kubectl logs -n aurora deploy/aurora-t2v-transformers --tail=5   # sin FileNotFoundError
```

## Plan de retirada

Se retira la política Kyverno y esta carpeta cuando el chart de Aurora permita
fijar la imagen por values o semitechnologies publique un build con el modelo
legible por uid 1000.

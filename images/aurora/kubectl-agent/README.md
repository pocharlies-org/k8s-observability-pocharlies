# Imagen aurora-kubectl-agent (SC-2708)

La imagen del vendor `gcr.io/sublime-flux-414616/aurora-kubectl-agent:1.0.3`
ya no existe (HTTP 401 anónimo; el vendor la retiró de gcr.io) y no quedaba en
la caché de ningún nodo → ImagePullBackOff desde 2026-10-25 (incidente Keep
DEPL-15370).

Aquí está la fuente exacta que llevaba esa imagen: `Dockerfile`, `agent.py` y
`requirements.txt` del directorio `kubectl-agent/src` del commit `8d3c5462` de
Arvo-AI/aurora — el mismo commit del que ArgoCD toma el chart
(`kubectl-agent/chart`), así que código y chart quedan en el mismo pin.
Hashes SHA-256:

```
94d45a05455ba1dd9ef101d2a60e23709ae7c2e36e225f3f4e3dae85377f2d79  agent.py
1bc1ff40087b0dd7269083d3f15a435605de3ce267e4dc69ef26cb7552df44ed  Dockerfile
093328096d40447ad9df80496b1b641a3a2575e34a11e4f7cba2b694698cd68b  requirements.txt
```

## Construir y subir (x86, amd64 — el deployment va con nodeSelector a sauvage)

```bash
docker build --platform linux/amd64 -t \
  harbor.e-dani.com/library/aurora-kubectl-agent:1.0.3-r1 .
docker push harbor.e-dani.com/library/aurora-kubectl-agent:1.0.3-r1
```

`harbor.e-dani.com/library` es el proyecto público de Harbor (pull anónimo
verificado desde sauvage). Consumida por `aurora/kubectl-agent-values.yaml`
(`agent.image`), desplegada en INFRA-1010.

## Retirada

Si el vendor publica la imagen en un registry accesible, se vuelve a él y esta
carpeta muere.

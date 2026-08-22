# k8s-observability-pocharlies

Stack de observabilidad: VictoriaMetrics, Grafana, Loki, Alloy, AlertManager

## Cluster
- **Master**: x86 ubuntu (192.168.50.142), k3s v1.32.5
- **Workers**: nvidia-dgx (dgx1 ARM64), gx10-ec3d (dgx2 ARM64), sauvage (WireGuard edge)

## GitOps
Gestionado por ArgoCD desde [k8s-gitops-pocharlies](https://github.com/pocharlies/k8s-gitops-pocharlies).

## Estado objetivo

El monitoring viejo de `sauvage` sigue siendo un Docker Compose local con Prometheus,
Grafana, Loki, Promtail, Alertmanager, blackbox-exporter, node-exporter, cAdvisor y
exporters específicos. Sirve como referencia funcional, pero no es el plano de
observabilidad del cluster.

El stack Kubernetes debe ser la fuente principal:

- **Metrics**: VictoriaMetrics k8s stack, kube-state-metrics, kubelet/cAdvisor y node-exporter.
- **Logs**: Loki + Alloy en todos los nodos, incluido `sauvage`.
- **Dashboards**: Grafana en `https://grafana.e-dani.com`.
- **Alertas**: VMAlert + VMAlertmanager, con webhook hacia Synapse/OpenClaw.
- **Estado de servicios**: reglas de disponibilidad de workloads y probes blackbox para ingresses LAN/publicos.

## K8sGPT sin bucles LLM

K8sGPT ejecuta sólo detección determinista cada 15 minutos. Los analyzers de
`ReplicaSet`, `Service` y `Job` están excluidos porque concentraban unos 2.746
objetos históricos o ruidosos; el scan conserva Pods, workloads, PVC, nodos y
webhooks.

La explicación se hace en `k8sgpt-explainer`, separado del RPC `Analyze`:

- observa eventos de `Result` y nunca vuelve a preguntar por un fingerprint visto;
- si existe una explicación en caché, la restaura sin usar el modelo;
- procesa una única llamada simultánea, con 1024 tokens y timeout de 180 segundos;
- limita el gasto a 24 intentos diarios y dos intentos por fingerprint;
- un fallo afecta sólo a ese Result, no repite ni invalida el lote completo;
- sólo admite namespaces de producción y su plano operativo, enumerados en
  `manifests/k8sgpt-explainer.yaml`.
- excluye siempre su propio namespace `k8sgpt` para que un rollout transitorio
  no cree una autorreferencia de explicación.

El ConfigMap `k8sgpt-explanation-cache` lo crea el worker y no está gestionado
por ArgoCD: guarda explicaciones, fingerprints y presupuesto entre rollouts.

## Pendiente HA

El despliegue actual usa `VMSingle`, suficiente para arrancar visibilidad del cluster
pero no es HA. Para alta disponibilidad real hay que migrar a `VMCluster` con al menos
dos `vmstorage`, `vminsert` y `vmselect`, mas backups/snapshots probados del backend de
metricas. Loki tambien esta en modo single-binary; para HA debe moverse a modo scalable.

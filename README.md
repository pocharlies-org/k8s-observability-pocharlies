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
- **Dashboards**: Grafana en `https://grafana.lan.e-dani.com`.
- **Alertas**: VMAlert + VMAlertmanager, con webhook hacia Synapse/OpenClaw.
- **Estado de servicios**: reglas de disponibilidad de workloads y probes blackbox para ingresses LAN/publicos.

## Pendiente HA

El despliegue actual usa `VMSingle`, suficiente para arrancar visibilidad del cluster
pero no es HA. Para alta disponibilidad real hay que migrar a `VMCluster` con al menos
dos `vmstorage`, `vminsert` y `vmselect`, mas backups/snapshots probados del backend de
metricas. Loki tambien esta en modo single-binary; para HA debe moverse a modo scalable.

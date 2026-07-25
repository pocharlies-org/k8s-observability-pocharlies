# Matriz de routing de alertas — estado actual y destino en Keep

Generado el 2026-07-25 por `scripts/alert_routing.py matrix` desde el clúster
`x86-k3s`, simulando el matching de Alertmanager sobre
`VMAlertmanagerConfig monitoring/synapse-webhook`.

**No editar a mano.** Regenerar con el script tras cualquier cambio de rutas o reglas.

**Semántica que hace falta entender:** Alertmanager entrega al receiver propio de
una ruta sólo cuando *ninguna hija encaja*. Como la última hija del árbol es
`severity = warning → blackhole`, el árbol funciona como **allowlist**: un warning
llega a algún sitio únicamente si su `alertname` aparece listado antes.

## Resumen

| destino hoy | series | % |
|---|---:|---:|
| **BLACKHOLE (se descarta)** | 118 | 42% |
| synapse-webhook + telegram-emergencia | 101 | 36% |
| synapse-webhook | 51 | 18% |
| telegram-emergencia | 7 | 2% |
| telegram-labels-deep | 2 | 1% |
| cron-analyzer | 1 | 0% |
| **TOTAL** | **280** | 100% |

### Taxonomía de severidad realmente emitida

| valor | series | ¿lo contempla el árbol? |
|---|---:|---|
| `warning` | 142 | sí — `severity = warning` → blackhole |
| `critical` | 101 | sí — `severity = critical` |
| `warn` | 18 | **no** — cae al receiver raíz |
| `page` | 9 | **no** — cae al receiver raíz |
| `info` | 8 | **no** — cae al receiver raíz |
| `none` | 2 | **no** — cae al receiver raíz |

Seis valores distintos, de los que el árbol sólo contempla dos. `page` y `warn` no
son typos aislados: son la convención de subsistemas enteros (Labels/Valkey,
LibrePlay, Tracking) que nunca se alineó con el resto.

## Hallazgos accionables

1. **118 series (42%) no pueden notificar a nadie.**
   Descontando los heartbeats (InfoInhibitor, Watchdog), son 116
   series ciegas; 9 de ellas están disparadas ahora mismo
   (14 instancias activas).
   `Watchdog` e `InfoInhibitor` deben seguir sin notificar, pero **sí** tienen que
   llegar a Keep: son la señal de que la ingesta sigue viva.

2. **Las 9 alertas `severity: page` no llegan a Telegram.** `page` es la
   convención más urgente del repo, y hoy salen sólo por el webhook de Synapse:
   - `LabelGenerationStuck`
   - `LabelsValkeyEvictions`
   - `LabelsValkeyExporterDown`
   - `LabelsValkeyMasterCountInvalid`
   - `LabelsValkeyMetricsMissing`
   - `LabelsValkeyRejectedConnections`
   - `SynapseOperatorRestarts`
   - `SynapseOrphanIndexEntries`
   - `TrackingIngestionNatsDown`

3. **Las 18 alertas `severity: warn` esquivan el blackhole** y llegan a
   Synapse. Inconsistente, pero al menos visibles — y por eso hay que decidirlas una
   a una al normalizar `warn → warning`: normalizadas sin criterio pasan de visibles
   a candidatas al ruido de fondo.
   - `LabelsValkeyMemoryGrowth`
   - `LabelsValkeyMemoryHigh`
   - `LabelsValkeyScrapeTargetsLow`
   - `LibrePlayDependencyLatencyHigh`
   - `LibrePlayQueueBacklogHigh`
   - `LibrePlayQueueFailures`
   - `LibrePlaySLOErrorBudgetBurnSlow`
   - `LibrePlaySyntheticAvailabilityBudgetLow`
   - `LibrePlaySyntheticLatencyHigh`
   - `LibrePlayWorkerOrWebRestarting`
   - `SynapseJanitorArchiveFailing`
   - `SynapseJanitorStalled`
   - `SynapsePollFaultedBacklog`
   - `TrackingIngestionBacklog`
   - `TrackingIngestionBacklogStuck`
   - `TrackingIngestionBadEvents`
   - `TrackingIngestionResubscribeStorm`
   - `TrackingIngestionSilent`

## Destino en Keep

Normalización que aplica la mapping rule de Keep:

| severidad emitida | → normalizada | destino |
|---|---|---|
| `critical` | `critical` | Keep → Telegram (sin tema) + Incident + Aurora |
| `page` | `critical` | Keep → Telegram (sin tema) + Incident + Aurora |
| `warning` | `warning` | Keep → Telegram tema 34494 + Incident + Aurora |
| `warn` | `warning` | Keep → Telegram tema 34494 + Incident + Aurora |
| `info` | `info` | Keep → sólo registro (sin notificación) |
| `none` | `info` | Keep → sólo registro (sin notificación) |

`page → critical` es un cambio de comportamiento deliberado: hoy esas alertas no
despiertan a nadie pese a llamarse `page`.

## Matriz completa

`firing` = instancias activas en el momento de generar. Agrupado por subsistema.

### Alertmanager (11 — 3 ciegas)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `AlertmanagerClusterCrashlooping` | `critical` | synapse-webhook + telegram-emergencia |  |
| `AlertmanagerClusterDown` | `critical` | synapse-webhook + telegram-emergencia |  |
| `AlertmanagerClusterFailedToSendAlerts` | `critical` | synapse-webhook + telegram-emergencia |  |
| `AlertmanagerClusterFailedToSendAlerts` | `warning` | **BLACKHOLE** |  |
| `AlertmanagerConfigInconsistent` | `critical` | synapse-webhook + telegram-emergencia |  |
| `AlertmanagerErrors` | `warning` | **BLACKHOLE** |  |
| `AlertmanagerFailedReload` | `critical` | synapse-webhook + telegram-emergencia |  |
| `AlertmanagerFailedToSendAlerts` | `warning` | **BLACKHOLE** |  |
| `AlertmanagerMembersInconsistent` | `critical` | synapse-webhook + telegram-emergencia |  |
| `AlertmanagerTelegramDeliveryFailed` | `warning` | synapse-webhook |  |
| `AlertmanagerWebhookDeliveryFailed` | `warning` | telegram-emergencia |  |

### Blackbox (1 — 1 ciegas)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `BlackboxProbeDown` | `warning` | **BLACKHOLE** | 1 |

### CronAlertAnalyzer (3)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `CronAlertAnalyzerLlmFailed` | `warning` | telegram-emergencia |  |
| `CronAlertAnalyzerMetricsMissing` | `warning` | telegram-emergencia |  |
| `CronAlertAnalyzerTelegramDeliveryFailed` | `warning` | telegram-emergencia |  |

### ImageStudio (4 — 4 ciegas)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `ImageStudioErrorRateHigh` | `warning` | **BLACKHOLE** |  |
| `ImageStudioQueueStuck` | `warning` | **BLACKHOLE** |  |
| `ImageStudioStaleCurrentRecurring` | `warning` | **BLACKHOLE** |  |
| `ImageStudioWorkerDown` | `warning` | **BLACKHOLE** |  |

### Instagram (3 — 3 ciegas)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `InstagramLoraCleanupFailure` | `warning` | **BLACKHOLE** |  |
| `InstagramLoraFailureSpike` | `warning` | **BLACKHOLE** |  |
| `InstagramLoraPrivateArtifactsStale` | `warning` | **BLACKHOLE** | 2 |

### Krea2 (3 — 3 ciegas)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `Krea2TrainerErrorSpike` | `warning` | **BLACKHOLE** |  |
| `Krea2TrainerQueueStalled` | `warning` | **BLACKHOLE** |  |
| `Krea2TrainerWorkerDown` | `warning` | **BLACKHOLE** |  |

### Kube (59 — 38 ciegas)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `KubeAPIDown` | `critical` | synapse-webhook + telegram-emergencia |  |
| `KubeAPIErrorBudgetBurn` | `critical` | synapse-webhook + telegram-emergencia |  |
| `KubeAPIErrorBudgetBurn` | `warning` | **BLACKHOLE** |  |
| `KubeAPIInstanceUnreachable` | `warning` | **BLACKHOLE** |  |
| `KubeAPITerminatedRequests` | `warning` | **BLACKHOLE** |  |
| `KubeAggregatedAPIDown` | `warning` | **BLACKHOLE** |  |
| `KubeAggregatedAPIErrors` | `warning` | **BLACKHOLE** |  |
| `KubeCPUOvercommit` | `warning` | **BLACKHOLE** |  |
| `KubeCPUQuotaOvercommit` | `warning` | **BLACKHOLE** |  |
| `KubeClientCertificateExpiration` | `critical` | synapse-webhook + telegram-emergencia |  |
| `KubeClientCertificateExpiration` | `warning` | **BLACKHOLE** |  |
| `KubeClientErrors` | `warning` | **BLACKHOLE** |  |
| `KubeContainerWaiting` | `warning` | **BLACKHOLE** |  |
| `KubeDaemonSetMisScheduled` | `warning` | **BLACKHOLE** |  |
| `KubeDaemonSetNotScheduled` | `warning` | **BLACKHOLE** |  |
| `KubeDaemonSetRolloutStuck` | `warning` | **BLACKHOLE** |  |
| `KubeDeploymentGenerationMismatch` | `warning` | **BLACKHOLE** |  |
| `KubeDeploymentReplicasMismatch` | `warning` | **BLACKHOLE** |  |
| `KubeDeploymentRolloutStuck` | `warning` | **BLACKHOLE** |  |
| `KubeHpaMaxedOut` | `warning` | **BLACKHOLE** |  |
| `KubeHpaReplicasMismatch` | `warning` | **BLACKHOLE** |  |
| `KubeJobNotCompleted` | `warning` | **BLACKHOLE** |  |
| `KubeMemoryOvercommit` | `warning` | **BLACKHOLE** |  |
| `KubeMemoryQuotaOvercommit` | `warning` | **BLACKHOLE** |  |
| `KubeNodeEviction` | `info` | synapse-webhook |  |
| `KubeNodeNotReady` | `warning` | synapse-webhook + telegram-emergencia |  |
| `KubeNodePressure` | `info` | synapse-webhook |  |
| `KubeNodeReadinessFlapping` | `warning` | **BLACKHOLE** |  |
| `KubeNodeUnreachable` | `warning` | synapse-webhook + telegram-emergencia |  |
| `KubePdbNotEnoughHealthyPods` | `warning` | **BLACKHOLE** |  |
| `KubePersistentVolumeErrors` | `critical` | synapse-webhook + telegram-emergencia |  |
| `KubePersistentVolumeFillingUp` | `critical` | synapse-webhook + telegram-emergencia |  |
| `KubePersistentVolumeFillingUp` | `warning` | **BLACKHOLE** |  |
| `KubePersistentVolumeInodesFillingUp` | `critical` | synapse-webhook + telegram-emergencia |  |
| `KubePersistentVolumeInodesFillingUp` | `warning` | **BLACKHOLE** |  |
| `KubePodCrashLooping` | `warning` | **BLACKHOLE** |  |
| `KubePodNotReady` | `warning` | **BLACKHOLE** |  |
| `KubeQuotaAlmostFull` | `info` | synapse-webhook |  |
| `KubeQuotaExceeded` | `warning` | **BLACKHOLE** |  |
| `KubeQuotaFullyUsed` | `info` | synapse-webhook |  |
| `KubeStateMetricsListErrors` | `critical` | synapse-webhook + telegram-emergencia |  |
| `KubeStateMetricsShardingMismatch` | `critical` | synapse-webhook + telegram-emergencia |  |
| `KubeStateMetricsShardsMissing` | `critical` | synapse-webhook + telegram-emergencia |  |
| `KubeStateMetricsWatchErrors` | `critical` | synapse-webhook + telegram-emergencia |  |
| `KubeStatefulSetGenerationMismatch` | `warning` | **BLACKHOLE** |  |
| `KubeStatefulSetReplicasMismatch` | `warning` | **BLACKHOLE** |  |
| `KubeStatefulSetUpdateNotRolledOut` | `warning` | **BLACKHOLE** |  |
| `KubeVersionMismatch` | `warning` | **BLACKHOLE** |  |
| `KubeletClientCertificateExpiration` | `critical` | synapse-webhook + telegram-emergencia |  |
| `KubeletClientCertificateExpiration` | `warning` | **BLACKHOLE** |  |
| `KubeletClientCertificateRenewalErrors` | `warning` | **BLACKHOLE** |  |
| `KubeletDown` | `critical` | synapse-webhook + telegram-emergencia |  |
| `KubeletInstanceUnreachable` | `warning` | synapse-webhook + telegram-emergencia |  |
| `KubeletPlegDurationHigh` | `warning` | **BLACKHOLE** |  |
| `KubeletPodStartUpLatencyHigh` | `warning` | **BLACKHOLE** |  |
| `KubeletServerCertificateExpiration` | `critical` | synapse-webhook + telegram-emergencia |  |
| `KubeletServerCertificateExpiration` | `warning` | **BLACKHOLE** |  |
| `KubeletServerCertificateRenewalErrors` | `warning` | **BLACKHOLE** |  |
| `KubeletTooManyPods` | `info` | synapse-webhook |  |

### Kubernetes (3 — 1 ciegas)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `KubernetesDaemonSetUnavailable` | `warning` | **BLACKHOLE** |  |
| `KubernetesDeploymentUnavailable` | `critical` | synapse-webhook + telegram-emergencia |  |
| `KubernetesStatefulSetUnavailable` | `critical` | synapse-webhook + telegram-emergencia |  |

### LabelGeneration (1)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `LabelGenerationStuck` | `page` | synapse-webhook |  |

### Labels (10)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `LabelsDeepMonitorIncident` | `warning` | telegram-labels-deep |  |
| `LabelsDeepMonitorMissing` | `warning` | telegram-labels-deep |  |
| `LabelsValkeyEvictions` | `page` | synapse-webhook |  |
| `LabelsValkeyExporterDown` | `page` | synapse-webhook |  |
| `LabelsValkeyMasterCountInvalid` | `page` | synapse-webhook |  |
| `LabelsValkeyMemoryGrowth` | `warn` | synapse-webhook |  |
| `LabelsValkeyMemoryHigh` | `warn` | synapse-webhook |  |
| `LabelsValkeyMetricsMissing` | `page` | synapse-webhook |  |
| `LabelsValkeyRejectedConnections` | `page` | synapse-webhook |  |
| `LabelsValkeyScrapeTargetsLow` | `warn` | synapse-webhook |  |

### LibrePlay (14)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `LibrePlayDependencyDown` | `critical` | synapse-webhook + telegram-emergencia |  |
| `LibrePlayDependencyLatencyHigh` | `warn` | synapse-webhook |  |
| `LibrePlayDeploymentUnavailable` | `critical` | synapse-webhook + telegram-emergencia |  |
| `LibrePlayMetricsScrapeMissing` | `critical` | synapse-webhook + telegram-emergencia |  |
| `LibrePlayPostgresUnavailable` | `critical` | synapse-webhook + telegram-emergencia |  |
| `LibrePlayQueueBacklogHigh` | `warn` | synapse-webhook |  |
| `LibrePlayQueueFailures` | `warn` | synapse-webhook | 1 |
| `LibrePlaySLOErrorBudgetBurnFast` | `critical` | synapse-webhook + telegram-emergencia |  |
| `LibrePlaySLOErrorBudgetBurnMedium` | `critical` | synapse-webhook + telegram-emergencia |  |
| `LibrePlaySLOErrorBudgetBurnSlow` | `warn` | synapse-webhook |  |
| `LibrePlaySyntheticAvailabilityBudgetLow` | `warn` | synapse-webhook |  |
| `LibrePlaySyntheticDown` | `critical` | synapse-webhook + telegram-emergencia |  |
| `LibrePlaySyntheticLatencyHigh` | `warn` | synapse-webhook |  |
| `LibrePlayWorkerOrWebRestarting` | `warn` | synapse-webhook |  |

### MCP (4)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `MCPBackendCrashLooping` | `warning` | synapse-webhook |  |
| `MCPBackendMemNearLimit` | `warning` | synapse-webhook |  |
| `MCPBackendOOMKilled` | `critical` | synapse-webhook + telegram-emergencia |  |
| `MCPGatewayDown` | `critical` | synapse-webhook + telegram-emergencia |  |

### Node (28 — 21 ciegas)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `NodeBecomesReadonlyIn3Days` | `warning` | **BLACKHOLE** |  |
| `NodeBondingDegraded` | `warning` | **BLACKHOLE** |  |
| `NodeCPUHighUsage` | `info` | synapse-webhook |  |
| `NodeClockNotSynchronising` | `warning` | **BLACKHOLE** |  |
| `NodeClockSkewDetected` | `warning` | **BLACKHOLE** |  |
| `NodeDiskIOSaturation` | `warning` | **BLACKHOLE** |  |
| `NodeFileDescriptorLimit` | `critical` | synapse-webhook + telegram-emergencia |  |
| `NodeFileDescriptorLimit` | `warning` | **BLACKHOLE** |  |
| `NodeFilesystemAlmostOutOfFiles` | `critical` | synapse-webhook + telegram-emergencia |  |
| `NodeFilesystemAlmostOutOfFiles` | `warning` | **BLACKHOLE** |  |
| `NodeFilesystemAlmostOutOfSpace` | `critical` | synapse-webhook + telegram-emergencia |  |
| `NodeFilesystemAlmostOutOfSpace` | `warning` | **BLACKHOLE** |  |
| `NodeFilesystemFilesFillingUp` | `critical` | synapse-webhook + telegram-emergencia |  |
| `NodeFilesystemFilesFillingUp` | `warning` | **BLACKHOLE** |  |
| `NodeFilesystemSpaceFillingUp` | `critical` | synapse-webhook + telegram-emergencia |  |
| `NodeFilesystemSpaceFillingUp` | `warning` | **BLACKHOLE** |  |
| `NodeHighNumberConntrackEntriesUsed` | `warning` | **BLACKHOLE** |  |
| `NodeMemoryHighUtilization` | `warning` | **BLACKHOLE** |  |
| `NodeMemoryMajorPagesFaults` | `warning` | **BLACKHOLE** |  |
| `NodeNetworkInterfaceFlapping` | `warning` | **BLACKHOLE** |  |
| `NodeNetworkReceiveErrs` | `warning` | **BLACKHOLE** |  |
| `NodeNetworkTransmitErrs` | `warning` | **BLACKHOLE** |  |
| `NodeRAIDDegraded` | `critical` | synapse-webhook + telegram-emergencia |  |
| `NodeRAIDDiskFailure` | `warning` | **BLACKHOLE** |  |
| `NodeSystemSaturation` | `warning` | **BLACKHOLE** | 2 |
| `NodeSystemdServiceCrashlooping` | `warning` | **BLACKHOLE** |  |
| `NodeSystemdServiceFailed` | `warning` | **BLACKHOLE** |  |
| `NodeTextFileCollectorScrapeError` | `warning` | **BLACKHOLE** |  |

### OVH (3)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `OVHPVCHubMetricMissing` | `warning` | synapse-webhook |  |
| `OVHPVCHubNeverSynced` | `warning` | synapse-webhook |  |
| `OVHPVCHubStale` | `warning` | synapse-webhook |  |

### Rabbitmq (13)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `RabbitmqClusterPartition` | `critical` | synapse-webhook + telegram-emergencia |  |
| `RabbitmqClusterSizeBelowExpected` | `critical` | synapse-webhook + telegram-emergencia |  |
| `RabbitmqDlqGrowth` | `warning` | synapse-webhook | 4 |
| `RabbitmqFunctionalQueueNoConsumer` | `warning` | synapse-webhook | 2 |
| `RabbitmqHeadMessageStale` | `critical` | synapse-webhook + telegram-emergencia |  |
| `RabbitmqMemoryAlarmActive` | `critical` | synapse-webhook + telegram-emergencia |  |
| `RabbitmqMemoryHigh` | `critical` | synapse-webhook + telegram-emergencia |  |
| `RabbitmqMnesiaPartitionStuck` | `critical` | synapse-webhook + telegram-emergencia |  |
| `RabbitmqNodeScrapeBlackout` | `critical` | synapse-webhook + telegram-emergencia |  |
| `RabbitmqPeersMetricMissing` | `critical` | synapse-webhook + telegram-emergencia |  |
| `RabbitmqQueueBacklogHigh` | `warning` | synapse-webhook |  |
| `RabbitmqScrapeMissing` | `critical` | synapse-webhook + telegram-emergencia |  |
| `RabbitmqUnackedStuck` | `critical` | synapse-webhook + telegram-emergencia |  |

### Request (1 — 1 ciegas)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `RequestErrorsToAPI` | `warning` | **BLACKHOLE** | 2 |

### ScrapePool (1 — 1 ciegas)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `ScrapePoolHasNoTargets` | `warning` | **BLACKHOLE** | 1 |

### Sii (2)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `SiiMonthlyReportFailed` | `warning` | synapse-webhook |  |
| `SiiMonthlyReportMissing` | `critical` | synapse-webhook + telegram-emergencia |  |

### Synapse (16)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `SynapseAdapterTargetDown` | `warning` | synapse-webhook |  |
| `SynapseCoreAbsent` | `critical` | telegram-emergencia |  |
| `SynapseDLQBacklog` | `warning` | synapse-webhook |  |
| `SynapseDispatcherNotPublishing` | `critical` | telegram-emergencia |  |
| `SynapseDown` | `critical` | telegram-emergencia |  |
| `SynapseJanitorArchiveFailing` | `warn` | synapse-webhook |  |
| `SynapseJanitorStalled` | `warn` | synapse-webhook |  |
| `SynapseOperatorRestarts` | `page` | synapse-webhook |  |
| `SynapseOrphanIndexEntries` | `page` | synapse-webhook |  |
| `SynapseOutboxExhausted` | `warning` | synapse-webhook | 2 |
| `SynapseOutboxOldestStale` | `warning` | synapse-webhook | 2 |
| `SynapsePollFaultedBacklog` | `warn` | synapse-webhook |  |
| `SynapseReconcileApplyFailed` | `critical` | synapse-webhook + telegram-emergencia |  |
| `SynapseReconcileApplyPartial` | `critical` | synapse-webhook + telegram-emergencia |  |
| `SynapseReconcileRevertFailed` | `critical` | synapse-webhook + telegram-emergencia |  |
| `SynapseScheduledWorkflowStalled` | `warning` | synapse-webhook |  |

### Target (1 — 1 ciegas)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `TargetDown` | `warning` | **BLACKHOLE** | 1 |

### TooMany (7 — 5 ciegas)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `TooManyLogs` | `warning` | **BLACKHOLE** | 3 |
| `TooManyMissedIterations` | `warning` | **BLACKHOLE** |  |
| `TooManyRemoteWriteErrors` | `warning` | **BLACKHOLE** |  |
| `TooManyRestarts` | `critical` | synapse-webhook + telegram-emergencia |  |
| `TooManyScrapeErrors` | `warning` | **BLACKHOLE** | 1 |
| `TooManyTSIDMisses` | `critical` | synapse-webhook + telegram-emergencia |  |
| `TooManyWriteErrors` | `warning` | **BLACKHOLE** |  |

### Tracking (7)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `TrackingIngestionBacklog` | `warn` | synapse-webhook |  |
| `TrackingIngestionBacklogStuck` | `warn` | synapse-webhook |  |
| `TrackingIngestionBadEvents` | `warn` | synapse-webhook |  |
| `TrackingIngestionNatsDown` | `page` | synapse-webhook |  |
| `TrackingIngestionResubscribeStorm` | `warn` | synapse-webhook |  |
| `TrackingIngestionSilent` | `warn` | synapse-webhook |  |
| `TrackingPage404Spike` | `critical` | synapse-webhook + telegram-emergencia |  |

### otros (85 — 36 ciegas)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `AffiliateAppHealthLatencyHigh` | `warning` | **BLACKHOLE** |  |
| `AffiliateAppMemoryHigh` | `warning` | **BLACKHOLE** |  |
| `AffiliateAppNotReady` | `critical` | synapse-webhook + telegram-emergencia |  |
| `AffiliateAppOOMKilled` | `critical` | synapse-webhook + telegram-emergencia |  |
| `AffiliateAppPublicDown` | `critical` | synapse-webhook + telegram-emergencia |  |
| `AffiliateAppRestartSpike` | `critical` | synapse-webhook + telegram-emergencia |  |
| `AlertingRulesError` | `warning` | **BLACKHOLE** | 1 |
| `CPUThrottlingHigh` | `info` | synapse-webhook |  |
| `ConcurrentInsertsHitTheLimit` | `warning` | **BLACKHOLE** |  |
| `ConfigurationReloadFailure` | `warning` | **BLACKHOLE** |  |
| `ConversationAutopilotSilent24h` | `critical` | synapse-webhook + telegram-emergencia |  |
| `ConversationDLQDepth` | `critical` | synapse-webhook + telegram-emergencia |  |
| `ConversationHandoffSpike` | `critical` | synapse-webhook + telegram-emergencia |  |
| `ConversationScrapeAbsent` | `critical` | synapse-webhook + telegram-emergencia |  |
| `ConversationTimeoutRate` | `critical` | synapse-webhook + telegram-emergencia |  |
| `DiskRunsOutOfSpace` | `critical` | synapse-webhook + telegram-emergencia |  |
| `DiskRunsOutOfSpaceIn3Days` | `critical` | synapse-webhook + telegram-emergencia |  |
| `HighQueueDepth` | `warning` | **BLACKHOLE** |  |
| `IndexDBRecordsDrop` | `critical` | synapse-webhook + telegram-emergencia |  |
| `InfoInhibitor` | `none` | **BLACKHOLE** | 1 |
| `K8sCronJobFailed` | `warning` | cron-analyzer |  |
| `LitellmNotReady` | `critical` | synapse-webhook + telegram-emergencia |  |
| `LlmPoolCapabilityUnavailable` | `critical` | synapse-webhook + telegram-emergencia |  |
| `LlmResidentDeploymentUnavailable` | `critical` | synapse-webhook + telegram-emergencia |  |
| `LlmResidentScaledToZero` | `critical` | synapse-webhook + telegram-emergencia |  |
| `LogErrors` | `warning` | **BLACKHOLE** |  |
| `MetadataCacheUtilizationIsTooHigh` | `warning` | **BLACKHOLE** |  |
| `MetricNameStatsCacheUtilizationIsTooHigh` | `warning` | **BLACKHOLE** |  |
| `OpenClawTelegramRouterDeadLetters` | `critical` | synapse-webhook + telegram-emergencia |  |
| `OpenClawTelegramRouterMetricsMissing` | `critical` | synapse-webhook + telegram-emergencia |  |
| `OpenClawTelegramRouterPaused` | `warning` | **BLACKHOLE** |  |
| `OpenClawTelegramRouterQueueBacklog` | `critical` | synapse-webhook + telegram-emergencia |  |
| `PersistentQueueForReadsIsSaturated` | `warning` | **BLACKHOLE** |  |
| `PersistentQueueForWritesIsSaturated` | `warning` | **BLACKHOLE** |  |
| `PersistentQueueIsDroppingData` | `critical` | synapse-webhook + telegram-emergencia |  |
| `PersistentQueueRunsOutOfSpaceIn12Hours` | `warning` | **BLACKHOLE** |  |
| `PersistentQueueRunsOutOfSpaceIn4Hours` | `critical` | synapse-webhook + telegram-emergencia |  |
| `PickerPurchaseRecommendStale` | `warning` | **BLACKHOLE** |  |
| `PickerSignalsNeverRan` | `warning` | **BLACKHOLE** |  |
| `PickerSignalsStale` | `warning` | **BLACKHOLE** |  |
| `ProcessNearFDLimits` | `critical` | synapse-webhook + telegram-emergencia |  |
| `RPCErrors` | `warning` | **BLACKHOLE** |  |
| `ReconcileErrors` | `warning` | **BLACKHOLE** |  |
| `RecordingRulesError` | `warning` | **BLACKHOLE** |  |
| `RecordingRulesNoData` | `info` | synapse-webhook |  |
| `RejectedRemoteWriteDataBlocksAreDropped` | `warning` | **BLACKHOLE** |  |
| `RemoteWriteConnectionIsSaturated` | `warning` | **BLACKHOLE** |  |
| `RemoteWriteDroppingData` | `critical` | synapse-webhook + telegram-emergencia |  |
| `RemoteWriteErrors` | `warning` | **BLACKHOLE** |  |
| `RemoteWriteQueueHighUsage` | `warning` | **BLACKHOLE** |  |
| `RowsRejectedOnIngestion` | `warning` | **BLACKHOLE** |  |
| `SeriesLimitDayReached` | `critical` | synapse-webhook + telegram-emergencia |  |
| `SeriesLimitHourReached` | `critical` | synapse-webhook + telegram-emergencia |  |
| `ServiceDown` | `critical` | synapse-webhook + telegram-emergencia |  |
| `SharedDatastoreCoLocated` | `warning` | synapse-webhook |  |
| `SharedDatastoreUnreachable` | `critical` | synapse-webhook + telegram-emergencia |  |
| `SharedValkeyAofUnhealthy` | `critical` | synapse-webhook + telegram-emergencia |  |
| `SharedValkeyEvictions` | `warning` | **BLACKHOLE** |  |
| `SharedValkeyExporterDown` | `critical` | synapse-webhook + telegram-emergencia |  |
| `SharedValkeyMasterCountInvalid` | `critical` | synapse-webhook + telegram-emergencia |  |
| `SharedValkeyMemoryHigh` | `warning` | **BLACKHOLE** |  |
| `SharedValkeyMetricsMissing` | `critical` | synapse-webhook + telegram-emergencia |  |
| `SharedValkeyRejectedConnections` | `critical` | synapse-webhook + telegram-emergencia |  |
| `SharedValkeyReplicaCountLow` | `critical` | synapse-webhook + telegram-emergencia |  |
| `SharedValkeyScrapeTargetsLow` | `warning` | **BLACKHOLE** |  |
| `StreamAggrDedupFlushTimeout` | `warning` | **BLACKHOLE** |  |
| `StreamAggrFlushTimeout` | `warning` | **BLACKHOLE** |  |
| `TooHighCPUUsage` | `critical` | synapse-webhook + telegram-emergencia |  |
| `TooHighChurnRate` | `warning` | **BLACKHOLE** |  |
| `TooHighChurnRate24h` | `warning` | **BLACKHOLE** |  |
| `TooHighGoroutineSchedulingLatency` | `critical` | synapse-webhook + telegram-emergencia |  |
| `TooHighMemoryUsage` | `critical` | synapse-webhook + telegram-emergencia |  |
| `TooHighQueryLoad` | `warning` | **BLACKHOLE** |  |
| `TooHighSlowInsertsRate` | `warning` | **BLACKHOLE** |  |
| `UPSBatteryLow` | `critical` | synapse-webhook + telegram-emergencia |  |
| `UPSLowCharge` | `critical` | synapse-webhook + telegram-emergencia |  |
| `UPSMetricsAbsent` | `critical` | synapse-webhook + telegram-emergencia |  |
| `UPSOnBattery` | `critical` | synapse-webhook + telegram-emergencia |  |
| `UPSReplaceBattery` | `critical` | synapse-webhook + telegram-emergencia |  |
| `VllmLaneRestartLoop` | `critical` | synapse-webhook + telegram-emergencia |  |
| `VminsertVmstorageConnectionIsSaturated` | `warning` | **BLACKHOLE** |  |
| `Watchdog` | `none` | **BLACKHOLE** | 1 |
| `WeightResolverDown` | `critical` | synapse-webhook + telegram-emergencia |  |
| `WeightResolverMetricMissing` | `critical` | synapse-webhook + telegram-emergencia |  |
| `WeightResolverRestartSpike` | `critical` | synapse-webhook + telegram-emergencia |  |


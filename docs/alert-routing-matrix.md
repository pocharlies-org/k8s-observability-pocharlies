# Matriz de routing de alertas — estado actual y destino en Keep

Generado el 2026-07-27 por `scripts/alert_routing.py matrix` desde el clúster
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
| keep | 278 | 98% |
| backstop-telegram + keep | 6 | 2% |
| **TOTAL** | **284** | 100% |

### Taxonomía de severidad realmente emitida

| valor | series | ¿lo contempla el árbol? |
|---|---:|---|
| `warning` | 143 | sí — `severity = warning` → blackhole |
| `critical` | 104 | sí — `severity = critical` |
| `warn` | 18 | **no** — cae al receiver raíz |
| `page` | 9 | **no** — cae al receiver raíz |
| `info` | 8 | **no** — cae al receiver raíz |
| `none` | 2 | **no** — cae al receiver raíz |

Seis valores distintos, de los que el árbol sólo contempla dos. `page` y `warn` no
son typos aislados: son la convención de subsistemas enteros (Labels/Valkey,
LibrePlay, Tracking) que nunca se alineó con el resto.

## Hallazgos accionables

1. **0 series (0%) no pueden notificar a nadie.**
   Descontando los heartbeats (InfoInhibitor, Watchdog), son 0
   series ciegas; 0 de ellas están disparadas ahora mismo
   (0 instancias activas).
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

### Alertmanager (11)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `AlertmanagerClusterCrashlooping` | `critical` | keep |  |
| `AlertmanagerClusterDown` | `critical` | keep |  |
| `AlertmanagerClusterFailedToSendAlerts` | `critical` | keep |  |
| `AlertmanagerClusterFailedToSendAlerts` | `warning` | keep |  |
| `AlertmanagerConfigInconsistent` | `critical` | keep |  |
| `AlertmanagerErrors` | `warning` | keep |  |
| `AlertmanagerFailedReload` | `critical` | keep |  |
| `AlertmanagerFailedToSendAlerts` | `warning` | keep |  |
| `AlertmanagerMembersInconsistent` | `critical` | keep |  |
| `AlertmanagerTelegramDeliveryFailed` | `warning` | keep |  |
| `AlertmanagerWebhookDeliveryFailed` | `warning` | backstop-telegram + keep |  |

### Blackbox (1)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `BlackboxProbeDown` | `warning` | keep | 1 |

### Dgx (2)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `Dgx2GpuMemoryCutoff` | `critical` | keep |  |
| `Dgx2GpuMemoryWarning` | `warning` | keep |  |

### ImageStudio (4)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `ImageStudioErrorRateHigh` | `warning` | keep |  |
| `ImageStudioQueueStuck` | `warning` | keep |  |
| `ImageStudioStaleCurrentRecurring` | `warning` | keep |  |
| `ImageStudioWorkerDown` | `warning` | keep |  |

### Instagram (3)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `InstagramLoraCleanupFailure` | `warning` | keep |  |
| `InstagramLoraFailureSpike` | `warning` | keep |  |
| `InstagramLoraPrivateArtifactsStale` | `warning` | keep | 10 |

### Krea2 (3)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `Krea2TrainerErrorSpike` | `warning` | keep |  |
| `Krea2TrainerQueueStalled` | `warning` | keep |  |
| `Krea2TrainerWorkerDown` | `warning` | keep |  |

### Kube (59)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `KubeAPIDown` | `critical` | keep |  |
| `KubeAPIErrorBudgetBurn` | `critical` | keep |  |
| `KubeAPIErrorBudgetBurn` | `warning` | keep |  |
| `KubeAPIInstanceUnreachable` | `warning` | keep |  |
| `KubeAPITerminatedRequests` | `warning` | keep |  |
| `KubeAggregatedAPIDown` | `warning` | keep |  |
| `KubeAggregatedAPIErrors` | `warning` | keep |  |
| `KubeCPUOvercommit` | `warning` | keep |  |
| `KubeCPUQuotaOvercommit` | `warning` | keep |  |
| `KubeClientCertificateExpiration` | `critical` | keep |  |
| `KubeClientCertificateExpiration` | `warning` | keep |  |
| `KubeClientErrors` | `warning` | keep |  |
| `KubeContainerWaiting` | `warning` | keep |  |
| `KubeDaemonSetMisScheduled` | `warning` | keep |  |
| `KubeDaemonSetNotScheduled` | `warning` | keep |  |
| `KubeDaemonSetRolloutStuck` | `warning` | keep |  |
| `KubeDeploymentGenerationMismatch` | `warning` | keep |  |
| `KubeDeploymentReplicasMismatch` | `warning` | keep |  |
| `KubeDeploymentRolloutStuck` | `warning` | keep |  |
| `KubeHpaMaxedOut` | `warning` | keep |  |
| `KubeHpaReplicasMismatch` | `warning` | keep |  |
| `KubeJobNotCompleted` | `warning` | keep |  |
| `KubeMemoryOvercommit` | `warning` | keep |  |
| `KubeMemoryQuotaOvercommit` | `warning` | keep |  |
| `KubeNodeEviction` | `info` | keep |  |
| `KubeNodeNotReady` | `warning` | backstop-telegram + keep |  |
| `KubeNodePressure` | `info` | keep |  |
| `KubeNodeReadinessFlapping` | `warning` | keep |  |
| `KubeNodeUnreachable` | `warning` | backstop-telegram + keep |  |
| `KubePdbNotEnoughHealthyPods` | `warning` | keep |  |
| `KubePersistentVolumeErrors` | `critical` | keep |  |
| `KubePersistentVolumeFillingUp` | `critical` | keep |  |
| `KubePersistentVolumeFillingUp` | `warning` | keep |  |
| `KubePersistentVolumeInodesFillingUp` | `critical` | keep |  |
| `KubePersistentVolumeInodesFillingUp` | `warning` | keep |  |
| `KubePodCrashLooping` | `warning` | keep | 1 |
| `KubePodNotReady` | `warning` | keep |  |
| `KubeQuotaAlmostFull` | `info` | keep |  |
| `KubeQuotaExceeded` | `warning` | keep |  |
| `KubeQuotaFullyUsed` | `info` | keep |  |
| `KubeStateMetricsListErrors` | `critical` | keep |  |
| `KubeStateMetricsShardingMismatch` | `critical` | keep |  |
| `KubeStateMetricsShardsMissing` | `critical` | keep |  |
| `KubeStateMetricsWatchErrors` | `critical` | keep |  |
| `KubeStatefulSetGenerationMismatch` | `warning` | keep |  |
| `KubeStatefulSetReplicasMismatch` | `warning` | keep |  |
| `KubeStatefulSetUpdateNotRolledOut` | `warning` | keep |  |
| `KubeVersionMismatch` | `warning` | keep |  |
| `KubeletClientCertificateExpiration` | `critical` | keep |  |
| `KubeletClientCertificateExpiration` | `warning` | keep |  |
| `KubeletClientCertificateRenewalErrors` | `warning` | keep |  |
| `KubeletDown` | `critical` | keep |  |
| `KubeletInstanceUnreachable` | `warning` | keep |  |
| `KubeletPlegDurationHigh` | `warning` | keep |  |
| `KubeletPodStartUpLatencyHigh` | `warning` | keep |  |
| `KubeletServerCertificateExpiration` | `critical` | keep |  |
| `KubeletServerCertificateExpiration` | `warning` | keep |  |
| `KubeletServerCertificateRenewalErrors` | `warning` | keep |  |
| `KubeletTooManyPods` | `info` | keep |  |

### Kubernetes (3)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `KubernetesDaemonSetUnavailable` | `warning` | keep |  |
| `KubernetesDeploymentUnavailable` | `critical` | keep |  |
| `KubernetesStatefulSetUnavailable` | `critical` | keep |  |

### LabelGeneration (1)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `LabelGenerationStuck` | `page` | keep |  |

### Labels (10)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `LabelsDeepMonitorIncident` | `warning` | keep |  |
| `LabelsDeepMonitorMissing` | `warning` | keep |  |
| `LabelsValkeyEvictions` | `page` | keep |  |
| `LabelsValkeyExporterDown` | `page` | keep |  |
| `LabelsValkeyMasterCountInvalid` | `page` | keep |  |
| `LabelsValkeyMemoryGrowth` | `warn` | keep |  |
| `LabelsValkeyMemoryHigh` | `warn` | keep |  |
| `LabelsValkeyMetricsMissing` | `page` | keep |  |
| `LabelsValkeyRejectedConnections` | `page` | keep |  |
| `LabelsValkeyScrapeTargetsLow` | `warn` | keep |  |

### LibrePlay (14)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `LibrePlayDependencyDown` | `critical` | keep |  |
| `LibrePlayDependencyLatencyHigh` | `warn` | keep |  |
| `LibrePlayDeploymentUnavailable` | `critical` | keep |  |
| `LibrePlayMetricsScrapeMissing` | `critical` | keep |  |
| `LibrePlayPostgresUnavailable` | `critical` | keep |  |
| `LibrePlayQueueBacklogHigh` | `warn` | keep |  |
| `LibrePlayQueueFailures` | `warn` | keep | 1 |
| `LibrePlaySLOErrorBudgetBurnFast` | `critical` | keep |  |
| `LibrePlaySLOErrorBudgetBurnMedium` | `critical` | keep |  |
| `LibrePlaySLOErrorBudgetBurnSlow` | `warn` | keep |  |
| `LibrePlaySyntheticAvailabilityBudgetLow` | `warn` | keep |  |
| `LibrePlaySyntheticDown` | `critical` | keep |  |
| `LibrePlaySyntheticLatencyHigh` | `warn` | keep |  |
| `LibrePlayWorkerOrWebRestarting` | `warn` | keep |  |

### MCP (4)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `MCPBackendCrashLooping` | `warning` | keep |  |
| `MCPBackendMemNearLimit` | `warning` | keep |  |
| `MCPBackendOOMKilled` | `critical` | keep |  |
| `MCPGatewayDown` | `critical` | keep |  |

### Node (28)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `NodeBecomesReadonlyIn3Days` | `warning` | keep |  |
| `NodeBondingDegraded` | `warning` | keep |  |
| `NodeCPUHighUsage` | `info` | keep |  |
| `NodeClockNotSynchronising` | `warning` | keep |  |
| `NodeClockSkewDetected` | `warning` | keep |  |
| `NodeDiskIOSaturation` | `warning` | keep |  |
| `NodeFileDescriptorLimit` | `critical` | keep |  |
| `NodeFileDescriptorLimit` | `warning` | keep |  |
| `NodeFilesystemAlmostOutOfFiles` | `critical` | keep |  |
| `NodeFilesystemAlmostOutOfFiles` | `warning` | keep |  |
| `NodeFilesystemAlmostOutOfSpace` | `critical` | keep |  |
| `NodeFilesystemAlmostOutOfSpace` | `warning` | keep |  |
| `NodeFilesystemFilesFillingUp` | `critical` | keep |  |
| `NodeFilesystemFilesFillingUp` | `warning` | keep |  |
| `NodeFilesystemSpaceFillingUp` | `critical` | keep |  |
| `NodeFilesystemSpaceFillingUp` | `warning` | keep |  |
| `NodeHighNumberConntrackEntriesUsed` | `warning` | keep |  |
| `NodeMemoryHighUtilization` | `warning` | keep |  |
| `NodeMemoryMajorPagesFaults` | `warning` | keep |  |
| `NodeNetworkInterfaceFlapping` | `warning` | keep |  |
| `NodeNetworkReceiveErrs` | `warning` | keep |  |
| `NodeNetworkTransmitErrs` | `warning` | keep |  |
| `NodeRAIDDegraded` | `critical` | keep |  |
| `NodeRAIDDiskFailure` | `warning` | keep |  |
| `NodeSystemSaturation` | `warning` | keep | 1 |
| `NodeSystemdServiceCrashlooping` | `warning` | keep |  |
| `NodeSystemdServiceFailed` | `warning` | keep |  |
| `NodeTextFileCollectorScrapeError` | `warning` | keep |  |

### OVH (3)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `OVHPVCHubMetricMissing` | `warning` | keep |  |
| `OVHPVCHubNeverSynced` | `warning` | keep |  |
| `OVHPVCHubStale` | `warning` | keep |  |

### Rabbitmq (13)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `RabbitmqClusterPartition` | `critical` | keep |  |
| `RabbitmqClusterSizeBelowExpected` | `critical` | keep |  |
| `RabbitmqDlqGrowth` | `warning` | keep | 26 |
| `RabbitmqFunctionalQueueNoConsumer` | `warning` | keep |  |
| `RabbitmqHeadMessageStale` | `critical` | keep |  |
| `RabbitmqMemoryAlarmActive` | `critical` | keep |  |
| `RabbitmqMemoryHigh` | `critical` | keep |  |
| `RabbitmqMnesiaPartitionStuck` | `critical` | keep |  |
| `RabbitmqNodeScrapeBlackout` | `critical` | keep |  |
| `RabbitmqPeersMetricMissing` | `critical` | keep |  |
| `RabbitmqQueueBacklogHigh` | `warning` | keep |  |
| `RabbitmqScrapeMissing` | `critical` | keep |  |
| `RabbitmqUnackedStuck` | `critical` | keep |  |

### Request (1)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `RequestErrorsToAPI` | `warning` | keep | 2 |

### ScrapePool (1)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `ScrapePoolHasNoTargets` | `warning` | keep | 1 |

### Sii (2)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `SiiMonthlyReportFailed` | `warning` | keep |  |
| `SiiMonthlyReportMissing` | `critical` | keep |  |

### Synapse (17)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `SynapseAdapterTargetDown` | `warning` | keep |  |
| `SynapseCoreAbsent` | `critical` | keep |  |
| `SynapseDLQBacklog` | `warning` | keep |  |
| `SynapseDispatcherNotPublishing` | `critical` | keep |  |
| `SynapseDown` | `critical` | keep |  |
| `SynapseJanitorArchiveFailing` | `warn` | keep |  |
| `SynapseJanitorStalled` | `warn` | keep |  |
| `SynapseOperatorRestarts` | `page` | keep |  |
| `SynapseOrphanIndexEntries` | `page` | keep |  |
| `SynapseOutboxExhausted` | `warning` | keep | 2 |
| `SynapseOutboxOldestStale` | `warning` | keep | 2 |
| `SynapsePollFaultedBacklog` | `warn` | keep |  |
| `SynapseReconcileApplyFailed` | `critical` | keep |  |
| `SynapseReconcileApplyPartial` | `critical` | keep |  |
| `SynapseReconcileRevertFailed` | `critical` | keep |  |
| `SynapseScheduledWorkflowStalled` | `warning` | keep | 1 |
| `SynapseWorkflowFailed` | `warning` | keep |  |

### Target (1)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `TargetDown` | `warning` | keep | 2 |

### TooMany (7)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `TooManyLogs` | `warning` | keep | 3 |
| `TooManyMissedIterations` | `warning` | keep |  |
| `TooManyRemoteWriteErrors` | `warning` | keep |  |
| `TooManyRestarts` | `critical` | keep |  |
| `TooManyScrapeErrors` | `warning` | keep | 1 |
| `TooManyTSIDMisses` | `critical` | keep |  |
| `TooManyWriteErrors` | `warning` | keep |  |

### Tracking (7)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `TrackingIngestionBacklog` | `warn` | keep |  |
| `TrackingIngestionBacklogStuck` | `warn` | keep |  |
| `TrackingIngestionBadEvents` | `warn` | keep |  |
| `TrackingIngestionNatsDown` | `page` | keep |  |
| `TrackingIngestionResubscribeStorm` | `warn` | keep |  |
| `TrackingIngestionSilent` | `warn` | keep |  |
| `TrackingPage404Spike` | `critical` | keep |  |

### otros (89)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `AffiliateAppHealthLatencyHigh` | `warning` | keep |  |
| `AffiliateAppMemoryHigh` | `warning` | keep |  |
| `AffiliateAppNotReady` | `critical` | keep |  |
| `AffiliateAppOOMKilled` | `critical` | keep |  |
| `AffiliateAppPublicDown` | `critical` | keep |  |
| `AffiliateAppRestartSpike` | `critical` | keep |  |
| `AlertingRulesError` | `warning` | keep | 1 |
| `CPUThrottlingHigh` | `info` | keep | 2 |
| `ConcurrentInsertsHitTheLimit` | `warning` | keep |  |
| `ConfigurationReloadFailure` | `warning` | keep |  |
| `ConversationAutopilotSilent24h` | `critical` | keep |  |
| `ConversationDLQDepth` | `critical` | keep |  |
| `ConversationHandoffSpike` | `critical` | keep |  |
| `ConversationScrapeAbsent` | `critical` | keep |  |
| `ConversationTimeoutRate` | `critical` | keep |  |
| `DiskRunsOutOfSpace` | `critical` | keep |  |
| `DiskRunsOutOfSpaceIn3Days` | `critical` | keep |  |
| `HighQueueDepth` | `warning` | keep |  |
| `IndexDBRecordsDrop` | `critical` | keep |  |
| `InfoInhibitor` | `none` | keep | 3 |
| `K8sCronJobFailed` | `warning` | keep |  |
| `KeepBackendAbsent` | `critical` | backstop-telegram + keep |  |
| `KeepBackendNotSpread` | `warning` | keep | 1 |
| `KeepIngestionDown` | `critical` | backstop-telegram + keep |  |
| `KeepIngestionSilent` | `warning` | backstop-telegram + keep |  |
| `LitellmNotReady` | `critical` | keep |  |
| `LlmPoolCapabilityUnavailable` | `critical` | keep |  |
| `LlmResidentDeploymentUnavailable` | `critical` | keep |  |
| `LlmResidentScaledToZero` | `critical` | keep |  |
| `LogErrors` | `warning` | keep |  |
| `MetadataCacheUtilizationIsTooHigh` | `warning` | keep |  |
| `MetricNameStatsCacheUtilizationIsTooHigh` | `warning` | keep |  |
| `OpenClawTelegramRouterDeadLetters` | `critical` | keep |  |
| `OpenClawTelegramRouterMetricsMissing` | `critical` | keep |  |
| `OpenClawTelegramRouterPaused` | `warning` | keep | 1 |
| `OpenClawTelegramRouterQueueBacklog` | `critical` | keep |  |
| `PersistentQueueForReadsIsSaturated` | `warning` | keep |  |
| `PersistentQueueForWritesIsSaturated` | `warning` | keep |  |
| `PersistentQueueIsDroppingData` | `critical` | keep |  |
| `PersistentQueueRunsOutOfSpaceIn12Hours` | `warning` | keep |  |
| `PersistentQueueRunsOutOfSpaceIn4Hours` | `critical` | keep |  |
| `PickerPurchaseRecommendStale` | `warning` | keep |  |
| `PickerSignalsNeverRan` | `warning` | keep |  |
| `PickerSignalsStale` | `warning` | keep |  |
| `ProcessNearFDLimits` | `critical` | keep |  |
| `RPCErrors` | `warning` | keep |  |
| `ReconcileErrors` | `warning` | keep |  |
| `RecordingRulesError` | `warning` | keep |  |
| `RecordingRulesNoData` | `info` | keep |  |
| `RejectedRemoteWriteDataBlocksAreDropped` | `warning` | keep |  |
| `RemoteWriteConnectionIsSaturated` | `warning` | keep |  |
| `RemoteWriteDroppingData` | `critical` | keep |  |
| `RemoteWriteErrors` | `warning` | keep |  |
| `RemoteWriteQueueHighUsage` | `warning` | keep |  |
| `RowsRejectedOnIngestion` | `warning` | keep |  |
| `SeriesLimitDayReached` | `critical` | keep |  |
| `SeriesLimitHourReached` | `critical` | keep |  |
| `ServiceDown` | `critical` | keep |  |
| `SharedDatastoreCoLocated` | `warning` | keep |  |
| `SharedDatastoreUnreachable` | `critical` | keep |  |
| `SharedValkeyAofUnhealthy` | `critical` | keep |  |
| `SharedValkeyEvictions` | `warning` | keep |  |
| `SharedValkeyExporterDown` | `critical` | keep |  |
| `SharedValkeyMasterCountInvalid` | `critical` | keep |  |
| `SharedValkeyMemoryHigh` | `warning` | keep |  |
| `SharedValkeyMetricsMissing` | `critical` | keep |  |
| `SharedValkeyRejectedConnections` | `critical` | keep |  |
| `SharedValkeyReplicaCountLow` | `critical` | keep |  |
| `SharedValkeyScrapeTargetsLow` | `warning` | keep |  |
| `StreamAggrDedupFlushTimeout` | `warning` | keep |  |
| `StreamAggrFlushTimeout` | `warning` | keep |  |
| `TooHighCPUUsage` | `critical` | keep |  |
| `TooHighChurnRate` | `warning` | keep |  |
| `TooHighChurnRate24h` | `warning` | keep |  |
| `TooHighGoroutineSchedulingLatency` | `critical` | keep |  |
| `TooHighMemoryUsage` | `critical` | keep |  |
| `TooHighQueryLoad` | `warning` | keep |  |
| `TooHighSlowInsertsRate` | `warning` | keep |  |
| `UPSBatteryLow` | `critical` | keep |  |
| `UPSLowCharge` | `critical` | keep |  |
| `UPSMetricsAbsent` | `critical` | keep |  |
| `UPSOnBattery` | `critical` | keep |  |
| `UPSReplaceBattery` | `critical` | keep |  |
| `VllmLaneRestartLoop` | `critical` | keep |  |
| `VminsertVmstorageConnectionIsSaturated` | `warning` | keep |  |
| `Watchdog` | `none` | keep | 1 |
| `WeightResolverDown` | `critical` | keep |  |
| `WeightResolverMetricMissing` | `critical` | keep |  |
| `WeightResolverRestartSpike` | `critical` | keep |  |


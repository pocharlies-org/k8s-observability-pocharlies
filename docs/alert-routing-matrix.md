# Matriz de routing de alertas — estado actual y destino en Keep

Generado el 2026-10-28 por `scripts/alert_routing.py matrix` desde las VMRules del
clúster `x86-k3s` y las definidas en `manifests/` (SC-1835), simulando el
matching de Alertmanager sobre `VMAlertmanagerConfig monitoring/synapse-webhook`.

**No editar a mano.** Regenerar con el script tras cualquier cambio de rutas o reglas.

**Semántica que hace falta entender:** Alertmanager entrega al receiver propio de
una ruta sólo cuando *ninguna hija encaja*.
La última hija del árbol es un catch-all (`receiver: keep`, sin
matchers): toda alerta llega a Keep, sin allowlist ni blackhole. Que haya incidente y
aviso lo decide una regla de correlación de `keep/rules/correlation-rules.yaml`
(`scripts/verify-notification-coverage.py`), no este árbol.

## Resumen

| destino hoy | series | % |
|---|---:|---:|
| keep | 353 | 98% |
| **BLACKHOLE (se descarta)** | 9 | 2% |
| **TOTAL** | **362** | 100% |

### Taxonomía de severidad realmente emitida

| valor | series | ¿lo contempla el árbol? |
|---|---:|---|
| `warning` | 214 | sí — catch-all → `keep` |
| `critical` | 138 | sí — `severity = critical` |
| `info` | 8 | **no** — cae al receiver raíz |
| `none` | 2 | **no** — cae al receiver raíz |

Seis valores distintos, de los que el árbol sólo contempla dos. `page` y `warn` no
son typos aislados: son la convención de subsistemas enteros (Labels/Valkey,
LibrePlay, Tracking) que nunca se alineó con el resto.

## Hallazgos accionables

1. **9 series (2%) no pueden notificar a nadie.**
   Descontando los heartbeats (InfoInhibitor, Watchdog), son 8
   series ciegas; 1 de ellas están disparadas ahora mismo
   (1 instancias activas).
   `Watchdog` e `InfoInhibitor` deben seguir sin notificar, pero **sí** tienen que
   llegar a Keep: son la señal de que la ingesta sigue viva.

2. **Las 0 alertas `severity: page` no notifican.** `page` es la
   convención más urgente del repo:

3. **Las 0 alertas `severity: warn` esquivan el blackhole** y llegan a
   Synapse. Inconsistente, pero al menos visibles — y por eso hay que decidirlas una
   a una al normalizar `warn → warning`: normalizadas sin criterio pasan de visibles
   a candidatas al ruido de fondo.

## Destino en Keep

Normalización que aplica la mapping rule de Keep:

| severidad emitida | → normalizada | destino |
|---|---|---|
| `critical` | `critical` | Keep → Incidente + Aurora |
| `page` | `critical` | Keep → Incidente + Aurora |
| `warning` | `warning` | Keep → Incidente + Aurora |
| `warn` | `warning` | Keep → Incidente + Aurora |
| `info` | `info` | Keep → sólo registro (sin notificación) |
| `none` | `info` | Keep → sólo registro (sin notificación) |

`page → critical` es un cambio de comportamiento deliberado: hoy esas alertas no
despiertan a nadie pese a llamarse `page`.

## Matriz completa

`firing` = instancias activas en el momento de generar. Agrupado por subsistema.

### Alertmanager (10)

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
| `AlertmanagerWebhookDeliveryFailed` | `warning` | keep |  |

### Blackbox (1)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `BlackboxProbeDown` | `warning` | keep |  |

### ImageStudio (4)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `ImageStudioErrorRateHigh` | `warning` | keep |  |
| `ImageStudioQueueStuck` | `warning` | keep |  |
| `ImageStudioStaleCurrentRecurring` | `warning` | keep |  |
| `ImageStudioWorkerDown` | `warning` | keep |  |

### Krea2 (3)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `Krea2TrainerErrorSpike` | `warning` | keep |  |
| `Krea2TrainerQueueStalled` | `warning` | keep |  |
| `Krea2TrainerWorkerDown` | `warning` | keep |  |

### Kube (59 — 5 ciegas)

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
| `KubeNodeEviction` | `info` | **BLACKHOLE** |  |
| `KubeNodeNotReady` | `warning` | keep |  |
| `KubeNodePressure` | `info` | **BLACKHOLE** |  |
| `KubeNodeReadinessFlapping` | `warning` | keep |  |
| `KubeNodeUnreachable` | `warning` | keep |  |
| `KubePdbNotEnoughHealthyPods` | `warning` | keep |  |
| `KubePersistentVolumeErrors` | `critical` | keep |  |
| `KubePersistentVolumeFillingUp` | `critical` | keep |  |
| `KubePersistentVolumeFillingUp` | `warning` | keep |  |
| `KubePersistentVolumeInodesFillingUp` | `critical` | keep |  |
| `KubePersistentVolumeInodesFillingUp` | `warning` | keep |  |
| `KubePodCrashLooping` | `warning` | keep |  |
| `KubePodNotReady` | `warning` | keep |  |
| `KubeQuotaAlmostFull` | `info` | **BLACKHOLE** |  |
| `KubeQuotaExceeded` | `warning` | keep |  |
| `KubeQuotaFullyUsed` | `info` | **BLACKHOLE** |  |
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
| `KubeletTooManyPods` | `info` | **BLACKHOLE** |  |

### Kubernetes (3)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `KubernetesDaemonSetUnavailable` | `warning` | keep |  |
| `KubernetesDeploymentUnavailable` | `critical` | keep |  |
| `KubernetesStatefulSetUnavailable` | `critical` | keep |  |

### LabelGeneration (1)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `LabelGenerationStuck` | `critical` | keep |  |

### Labels (14)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `LabelsDeepMonitorIncident` | `warning` | keep |  |
| `LabelsDeepMonitorMissing` | `warning` | keep |  |
| `LabelsFuelFreshnessMissing` | `warning` | keep |  |
| `LabelsFuelSurchargeStale` | `warning` | keep |  |
| `LabelsFuelSyncFailed` | `warning` | keep |  |
| `LabelsFuelSyncMissing` | `warning` | keep |  |
| `LabelsValkeyEvictions` | `critical` | keep |  |
| `LabelsValkeyExporterDown` | `critical` | keep |  |
| `LabelsValkeyMasterCountInvalid` | `critical` | keep |  |
| `LabelsValkeyMemoryGrowth` | `warning` | keep |  |
| `LabelsValkeyMemoryHigh` | `warning` | keep |  |
| `LabelsValkeyMetricsMissing` | `critical` | keep |  |
| `LabelsValkeyRejectedConnections` | `critical` | keep |  |
| `LabelsValkeyScrapeTargetsLow` | `warning` | keep |  |

### LibrePlay (14)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `LibrePlayDependencyDown` | `critical` | keep |  |
| `LibrePlayDependencyLatencyHigh` | `warning` | keep |  |
| `LibrePlayDeploymentUnavailable` | `critical` | keep |  |
| `LibrePlayMetricsScrapeMissing` | `critical` | keep |  |
| `LibrePlayPostgresUnavailable` | `critical` | keep |  |
| `LibrePlayQueueBacklogHigh` | `warning` | keep |  |
| `LibrePlayQueueFailures` | `warning` | keep |  |
| `LibrePlaySLOErrorBudgetBurnFast` | `critical` | keep |  |
| `LibrePlaySLOErrorBudgetBurnMedium` | `critical` | keep |  |
| `LibrePlaySLOErrorBudgetBurnSlow` | `warning` | keep |  |
| `LibrePlaySyntheticAvailabilityBudgetLow` | `warning` | keep |  |
| `LibrePlaySyntheticDown` | `critical` | keep |  |
| `LibrePlaySyntheticLatencyHigh` | `warning` | keep |  |
| `LibrePlayWorkerOrWebRestarting` | `warning` | keep |  |

### Longhorn (4)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `LonghornNodeSchedulingDisabled` | `warning` | keep | 1 |
| `LonghornTooFewSchedulableNodes` | `warning` | keep |  |
| `LonghornVolumeDegraded` | `warning` | keep |  |
| `LonghornVolumeFaulted` | `critical` | keep |  |

### MCP (4)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `MCPBackendCrashLooping` | `warning` | keep |  |
| `MCPBackendMemNearLimit` | `warning` | keep |  |
| `MCPBackendOOMKilled` | `critical` | keep |  |
| `MCPGatewayDown` | `critical` | keep |  |

### Node (32 — 1 ciegas)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `NodeBecomesReadonlyIn3Days` | `warning` | keep |  |
| `NodeBondingDegraded` | `warning` | keep |  |
| `NodeCPUHighUsage` | `info` | **BLACKHOLE** |  |
| `NodeClockNotSynchronising` | `warning` | keep |  |
| `NodeClockSkewDetected` | `warning` | keep |  |
| `NodeDiskFilling` | `warning` | keep | 2 |
| `NodeDiskIOSaturation` | `warning` | keep |  |
| `NodeDiskNearEviction` | `critical` | keep |  |
| `NodeDiskPressure` | `critical` | keep |  |
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
| `NodeRootDiskLowOrFilling` | `critical` | keep |  |
| `NodeSystemSaturation` | `warning` | keep |  |
| `NodeSystemdServiceCrashlooping` | `warning` | keep |  |
| `NodeSystemdServiceFailed` | `warning` | keep |  |
| `NodeTextFileCollectorScrapeError` | `warning` | keep | 3 |

### Postgres (5)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `PostgresSharedBackendsWaiting` | `warning` | keep |  |
| `PostgresSharedConnectionsCritical` | `critical` | keep |  |
| `PostgresSharedConnectionsHigh` | `warning` | keep | 1 |
| `PostgresSharedIdleInTransaction` | `warning` | keep |  |
| `PostgresSharedMetricsMissing` | `warning` | keep |  |

### Rabbitmq (15)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `RabbitmqClusterPartition` | `critical` | keep |  |
| `RabbitmqClusterSizeBelowExpected` | `critical` | keep |  |
| `RabbitmqContactSyncBacklogAfterWindow` | `warning` | keep |  |
| `RabbitmqDlqGrowth` | `warning` | keep | 2 |
| `RabbitmqExpensesBacklogAfterWindow` | `warning` | keep |  |
| `RabbitmqFunctionalQueueNoConsumer` | `warning` | keep | 1 |
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
| `RequestErrorsToAPI` | `warning` | keep |  |

### ScrapePool (1)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `ScrapePoolHasNoTargets` | `warning` | keep |  |

### Sii (6)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `SiiInvoicingCronStale` | `critical` | keep |  |
| `SiiInvoicingFunctionalFailure` | `warning` | keep |  |
| `SiiInvoicingTelemetryMissing` | `warning` | keep |  |
| `SiiMonthlyReportCronStale` | `critical` | keep |  |
| `SiiMonthlyReportFailed` | `warning` | keep |  |
| `SiiMonthlyReportTelemetryMissing` | `warning` | keep |  |

### Synapse (27)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `SynapseAdapterTargetDown` | `warning` | keep |  |
| `SynapseCoreAbsent` | `critical` | keep |  |
| `SynapseDLQBacklog` | `warning` | keep |  |
| `SynapseDispatcherNotPublishing` | `critical` | keep |  |
| `SynapseDown` | `critical` | keep |  |
| `SynapseDurableRetryBacklogOld` | `critical` | keep |  |
| `SynapseDurableRetryPending` | `warning` | keep |  |
| `SynapseGmailDigestFailing` | `warning` | keep |  |
| `SynapseGmailDigestLoopErroring` | `warning` | keep |  |
| `SynapseGmailWatchExpired` | `critical` | keep |  |
| `SynapseGmailWatchRenewerStale` | `critical` | keep |  |
| `SynapseJanitorArchiveFailing` | `warning` | keep |  |
| `SynapseJanitorStalled` | `warning` | keep |  |
| `SynapseOperatorRestarts` | `critical` | keep |  |
| `SynapseOrphanIndexEntries` | `critical` | keep |  |
| `SynapseOutboxExhausted` | `warning` | keep | 1 |
| `SynapseOutboxOldestStale` | `warning` | keep | 1 |
| `SynapsePollFaultedBacklog` | `warning` | keep |  |
| `SynapseReconcileApplyFailed` | `critical` | keep |  |
| `SynapseReconcileApplyPartial` | `critical` | keep |  |
| `SynapseReconcileRevertFailed` | `critical` | keep |  |
| `SynapseScheduledWorkflowRunStalledMonthly` | `warning` | keep |  |
| `SynapseScheduledWorkflowStalled` | `warning` | keep |  |
| `SynapseScheduledWorkflowStalledDaily` | `warning` | keep |  |
| `SynapseScheduledWorkflowStalledWeekly` | `warning` | keep |  |
| `SynapseUnroutableMessages` | `warning` | keep |  |
| `SynapseWorkflowFailed` | `warning` | keep | 1 |

### Target (1)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `TargetDown` | `warning` | keep | 3 |

### TooMany (7)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `TooManyLogs` | `warning` | keep | 1 |
| `TooManyMissedIterations` | `warning` | keep |  |
| `TooManyRemoteWriteErrors` | `warning` | keep |  |
| `TooManyRestarts` | `critical` | keep |  |
| `TooManyScrapeErrors` | `warning` | keep | 1 |
| `TooManyTSIDMisses` | `critical` | keep |  |
| `TooManyWriteErrors` | `warning` | keep |  |

### Tracking (7)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `TrackingIngestionBacklog` | `warning` | keep |  |
| `TrackingIngestionBacklogStuck` | `warning` | keep |  |
| `TrackingIngestionBadEvents` | `warning` | keep |  |
| `TrackingIngestionNatsDown` | `critical` | keep |  |
| `TrackingIngestionResubscribeStorm` | `warning` | keep |  |
| `TrackingIngestionSilent` | `warning` | keep |  |
| `TrackingPage404Spike` | `critical` | keep |  |

### otros (143 — 3 ciegas)

| alertname | sev | destino hoy | firing |
|---|---|---|---:|
| `AffiliateAppHealthLatencyHigh` | `warning` | keep |  |
| `AffiliateAppMemoryHigh` | `warning` | keep |  |
| `AffiliateAppNotReady` | `critical` | keep |  |
| `AffiliateAppOOMKilled` | `critical` | keep |  |
| `AffiliateAppPublicDown` | `critical` | keep |  |
| `AffiliateAppRestartSpike` | `critical` | keep |  |
| `AgentGatewayRouteErrorRateHigh` | `warning` | keep |  |
| `AlertingRulesError` | `warning` | keep |  |
| `AnalisisPuertaCerrada` | `warning` | keep |  |
| `AnalisisRevisorParado` | `warning` | keep |  |
| `AnalisisSinMetricas` | `warning` | keep |  |
| `AtlassianMcpToolDown` | `critical` | keep |  |
| `AuroraRcaCoverageAbsent` | `warning` | keep |  |
| `AuroraRcaCoverageLow` | `warning` | keep | 1 |
| `BackupRecoveryKitStale` | `critical` | keep |  |
| `BackupWeeklySnapshotStale` | `critical` | keep |  |
| `BgePoolLatencyAboveGate` | `critical` | keep |  |
| `BrainIngestConsecutiveFailures` | `warning` | keep |  |
| `BrainWindowsMassDeleteRefused` | `warning` | keep |  |
| `BrainWindowsPassStale` | `warning` | keep |  |
| `CIPoolSaturated` | `warning` | keep |  |
| `CIQueueExporterBlind` | `warning` | keep |  |
| `CIQueueJobQueuedTooLong` | `warning` | keep |  |
| `CIQueueLabelWithoutPool` | `warning` | keep |  |
| `CIRunnerNoProgress` | `warning` | keep |  |
| `CPUThrottlingHigh` | `info` | **BLACKHOLE** | 1 |
| `CertManagerCertificateMetricsMissing` | `critical` | keep |  |
| `CertificateExpiresSoon` | `warning` | keep |  |
| `CertificateNotReady` | `critical` | keep |  |
| `CompaniaSupervisorSinMetricas` | `critical` | keep |  |
| `ConcurrentInsertsHitTheLimit` | `warning` | keep |  |
| `ConfigurationReloadFailure` | `warning` | keep |  |
| `ConversationAutopilotSilent24h` | `critical` | keep |  |
| `ConversationDLQDepth` | `critical` | keep |  |
| `ConversationHandoffSpike` | `critical` | keep |  |
| `ConversationScrapeAbsent` | `critical` | keep | 1 |
| `ConversationTimeoutRate` | `critical` | keep |  |
| `CorreoBridgeMensajesPerdidos` | `warning` | keep |  |
| `DashProductorAusente` | `warning` | keep |  |
| `DeepSeekTpSpinWaitSuspected` | `critical` | keep |  |
| `DiskRunsOutOfSpace` | `critical` | keep |  |
| `DiskRunsOutOfSpaceIn3Days` | `critical` | keep |  |
| `ExternalSecretsMetricsAbsent` | `warning` | keep |  |
| `FrigateAlmacenamientoLleno` | `warning` | keep |  |
| `FrigateCaido` | `warning` | keep |  |
| `FrigateCamaraSinFps` | `warning` | keep |  |
| `FrigateDetectorLento` | `warning` | keep |  |
| `GpuArbiterResidentRestoreStuck` | `critical` | keep |  |
| `GpuArbiterStateObservationUnavailable` | `warning` | keep |  |
| `HighQueueDepth` | `warning` | keep |  |
| `IndexDBRecordsDrop` | `critical` | keep |  |
| `InfoInhibitor` | `none` | **BLACKHOLE** | 5 |
| `K8sCronJobFailed` | `warning` | keep | 3 |
| `KeepBackendAbsent` | `critical` | keep |  |
| `KeepBackendNotSpread` | `warning` | keep |  |
| `KeepIngestionDown` | `critical` | keep |  |
| `KeepIngestionSilent` | `warning` | keep |  |
| `LangfuseClickhousePvcFillingEarly` | `warning` | keep |  |
| `LitellmNotReady` | `critical` | keep |  |
| `LlmPoolCapabilityUnavailable` | `critical` | keep |  |
| `LlmResidentDeploymentUnavailable` | `critical` | keep |  |
| `LlmResidentScaledToZero` | `critical` | keep |  |
| `LogErrors` | `warning` | keep |  |
| `MetadataCacheUtilizationIsTooHigh` | `warning` | keep |  |
| `MetricNameStatsCacheUtilizationIsTooHigh` | `warning` | keep |  |
| `OnePasswordQuotaBurn` | `warning` | keep |  |
| `OnePasswordSyncMetricsAbsent` | `warning` | keep |  |
| `PersistentQueueForReadsIsSaturated` | `warning` | keep |  |
| `PersistentQueueForWritesIsSaturated` | `warning` | keep |  |
| `PersistentQueueIsDroppingData` | `critical` | keep |  |
| `PersistentQueueRunsOutOfSpaceIn12Hours` | `warning` | keep |  |
| `PersistentQueueRunsOutOfSpaceIn4Hours` | `critical` | keep |  |
| `PickerSignalsNeverRan` | `warning` | keep |  |
| `PickerSignalsStale` | `warning` | keep |  |
| `PlaudMcpPVCFull` | `warning` | keep |  |
| `PlaudMetricsAbsent` | `warning` | keep |  |
| `PlaudRecordingsStuck` | `warning` | keep |  |
| `PlaudRefreshTokenStale` | `warning` | keep |  |
| `PlaudSyncStalled` | `warning` | keep |  |
| `PlaudTokenExpired` | `critical` | keep |  |
| `PlaudWorkerNoFirstTick` | `warning` | keep |  |
| `PlaywrightMCPBrowserLeak` | `critical` | keep |  |
| `PlaywrightMCPCPUThrottled` | `warning` | keep |  |
| `PlaywrightMCPRestarting` | `warning` | keep | 1 |
| `ProcessNearFDLimits` | `critical` | keep |  |
| `Qwen38SpeculationWedged` | `critical` | keep |  |
| `Qwen38ZombieRequests` | `critical` | keep |  |
| `RPCErrors` | `warning` | keep |  |
| `ReconcileErrors` | `warning` | keep |  |
| `RecordingRulesError` | `warning` | keep |  |
| `RecordingRulesNoData` | `info` | **BLACKHOLE** |  |
| `RejectedRemoteWriteDataBlocksAreDropped` | `warning` | keep |  |
| `RemoteWriteConnectionIsSaturated` | `warning` | keep |  |
| `RemoteWriteDroppingData` | `critical` | keep |  |
| `RemoteWriteErrors` | `warning` | keep |  |
| `RemoteWriteQueueHighUsage` | `warning` | keep |  |
| `RowsRejectedOnIngestion` | `warning` | keep |  |
| `S3DriveMetricsAbsent` | `critical` | keep |  |
| `S3DriveOffline` | `critical` | keep |  |
| `S3DriveWriteErrors` | `critical` | keep |  |
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
| `ShopifyPicqerAuditFindings` | `warning` | keep |  |
| `ShopifyPicqerAuditTelemetryMissing` | `warning` | keep |  |
| `SkirmbooksInvoicingChainStalled` | `critical` | keep |  |
| `SkirmbooksInvoicingChainTelemetryMissing` | `warning` | keep |  |
| `SkirmshopAppOOMKilled` | `critical` | keep |  |
| `SkirmshopAppRestartSpike` | `critical` | keep |  |
| `SparkGpuClockStuckLow` | `warning` | keep |  |
| `StreamAggrDedupFlushTimeout` | `warning` | keep |  |
| `StreamAggrFlushTimeout` | `warning` | keep |  |
| `Studio3dJobsStuckWaitingGpu` | `warning` | keep |  |
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
| `VllmLaneRestartLoop` | `critical` | keep | 1 |
| `VminsertVmstorageConnectionIsSaturated` | `warning` | keep |  |
| `Watchdog` | `none` | keep | 1 |
| `WeightResolverDown` | `critical` | keep |  |
| `WeightResolverMetricMissing` | `critical` | keep |  |
| `WeightResolverRestartSpike` | `critical` | keep |  |
| `X86Silencioso` | `critical` | keep |  |

---

Fuera de esta matriz quedan las alertas que no son VMRules y se empujan
directo a Keep por `POST /alerts/event` (ArgoCD Notifications, familias x86
de ops-watch): se mantienen a mano en
[alert-routing-pushed-families.md](alert-routing-pushed-families.md).

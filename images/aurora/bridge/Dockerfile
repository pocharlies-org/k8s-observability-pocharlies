# Fork documentado INFRA-1157: aurora-server upstream 1.2.20 + los dos conjuntos
# registrados (tool-output = Arvo-AI/aurora#602, timeout del juez = Arvo-AI/aurora#688).
# Base pineada por DIGEST (reproducibilidad del registro, INFRA-324): el tag 1.2.20
# de upstream es mutable; el digest sha256:84d9586d… es lo que se construyó (medido
# 04-11, manifiesto OCI multi-arch amd64+arm64). Ver README.md — plan de retirada.
# Sin RUN a propósito: capa idéntica por arquitectura, build multi-arch sin ejecutar
# nada (la imagen base no trae patch/git y el runner no tiene QEMU).
ARG BASE=ghcr.io/arvo-ai/aurora-server
ARG BASE_DIGEST=sha256:84d9586d75bf2d1cab59aefa362ffc50860b71c37fbcdd9366112c1dcc356617
FROM ${BASE}@${BASE_DIGEST}

# Conjunto timeout del juez (#688): server/utils/security/* sobre la base 1.2.20
# (los dos ficheros, idénticos entre 1.2.20 y la base anterior e35121a — ver README).
COPY files/config.py /app/utils/security/config.py
COPY files/command_safety.py /app/utils/security/command_safety.py

# Conjunto tool-output (#602): los 4 ficheros de runtime de la rama de la PR,
# aplicados sin conflicto sobre 1.2.20 (ver README: verificado byte a byte).
COPY files/tool_output_cap.py /app/chat/backend/agent/utils/tool_output_cap.py
COPY files/tool_context_capture.py /app/chat/backend/agent/utils/tool_context_capture.py
COPY files/datadog_tool.py /app/chat/backend/agent/tools/datadog_tool.py
COPY files/hpa_vpa_recommendations.py /app/services/actions/hpa_vpa_recommendations.py

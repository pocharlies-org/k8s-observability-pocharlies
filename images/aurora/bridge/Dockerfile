# Puente INFRA-326: aurora-server sha-e35121a + parche Arvo-AI/aurora#688
# (timeout del juez de guardarraíles configurable) + capa SC-2633 (barrido de
# incidentes clavados en aurora_status='summarizing'). Ver README.md — retirada.
# Sin RUN a propósito: capa idéntica por arquitectura, build multi-arch sin ejecutar
# nada (la imagen base no trae patch/git y el runner no tiene QEMU).
ARG BASE=ghcr.io/pocharlies-org/aurora-server
ARG BASE_TAG=sha-e35121aeb7d80293d2e4ce462fe2bc05d9adb469
FROM ${BASE}:${BASE_TAG}

COPY files/config.py /app/utils/security/config.py
COPY files/command_safety.py /app/utils/security/command_safety.py
# SC-2633: task.py del main de pocharlies-org/aurora (pocharlies-org/aurora#5).
# El de la base es byte a byte el de e35121a (= main para este fichero, verificado
# por sha256 el 2026-10-28), así que esta capa no pisa nada del tool-output.
COPY files/task.py /app/chat/background/task.py

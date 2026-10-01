#!/bin/bash
# ETI - Monitor de salas Google Meet ("eyes") - encerramento
# Idempotente: não falha se já estiver parado.
set -u

PORT=8000
BACKUP_DIR="/home/emanoel/ETI/eyes_backup"

PID=$(pgrep -f "uvicorn app.main:app.*--port ${PORT}" | head -1)

if [ -z "${PID}" ]; then
    echo "Monitor já estava parado."
    exit 0
fi

# Persiste o relatório do encontro (JSON+TXT+HTML) ANTES de encerrar o
# processo — captura o estado final de participantes/presença.
if curl -s -m 10 -X POST "http://127.0.0.1:${PORT}/api/report/save" > /tmp/eyes_report_save.json 2>&1; then
    echo "Relatório do encontro salvo: $(cat /tmp/eyes_report_save.json)"
    # Replica para o backup persistente (data/relatorios/ some com /tmp).
    saved_dir=$(python3 -c "import json;print(json.load(open('/tmp/eyes_report_save.json'))['saved_to'])" 2>/dev/null)
    if [ -n "${saved_dir}" ] && [ -d "${saved_dir}" ]; then
        mkdir -p "${BACKUP_DIR}/data/relatorios"
        cp -r "${saved_dir}" "${BACKUP_DIR}/data/relatorios/"
        echo "Relatório replicado em ${BACKUP_DIR}/data/relatorios/$(basename "${saved_dir}")"
    fi
else
    echo "Aviso: falha ao salvar o relatório do encontro (monitor será encerrado mesmo assim)."
fi

kill "${PID}" 2>/dev/null
for i in $(seq 1 10); do
    if ! kill -0 "${PID}" 2>/dev/null; then
        echo "Monitor encerrado (PID ${PID})."
        exit 0
    fi
    sleep 1
done

kill -9 "${PID}" 2>/dev/null
echo "Monitor encerrado à força (PID ${PID})."

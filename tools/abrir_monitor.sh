#!/bin/bash
# ETI - Monitor de salas Google Meet ("eyes")
# Sobe o uvicorn em 127.0.0.1:8000 se ainda não estiver respondendo.
# Idempotente: nunca tenta um segundo bind na mesma porta.
set -u

PORT=8000
APP_DIR="/tmp/eyes"
VENV_PY="/home/emanoel/ETI/.venv/bin/python3"
BACKUP_DIR="/home/emanoel/ETI/eyes_backup"

# 1) Já está respondendo? Não faz nada.
if curl -s -m 5 "http://127.0.0.1:${PORT}/api/status" >/dev/null 2>&1; then
    echo "Monitor já está no ar em 127.0.0.1:${PORT}."
    exit 0
fi

# 2) /tmp/eyes existe e tem as adaptações? Se não, reclonar + restaurar.
if [ ! -f "${APP_DIR}/static/index.html" ] || [ ! -f "${APP_DIR}/tools/eti_token_credentials.py" ]; then
    echo "Recriando ${APP_DIR} (ausente ou incompleto)..."
    rm -rf "${APP_DIR}"
    git clone --depth 1 https://github.com/mikaelmota13/eyes.git "${APP_DIR}"
    mkdir -p "${APP_DIR}/tools" "${APP_DIR}/data"
    cp -r "${BACKUP_DIR}/app/." "${APP_DIR}/app/"
    cp -r "${BACKUP_DIR}/static/." "${APP_DIR}/static/"
    cp "${BACKUP_DIR}/tools/eti_token_credentials.py" "${APP_DIR}/tools/"
    cp "${BACKUP_DIR}/data/salas.csv" "${APP_DIR}/data/salas.csv"
    if [ -f "${BACKUP_DIR}/data/formadores.json" ]; then
        cp "${BACKUP_DIR}/data/formadores.json" "${APP_DIR}/data/formadores.json"
    fi
    if [ -f "${BACKUP_DIR}/tools/make_formadores_json.py" ]; then
        cp "${BACKUP_DIR}/tools/make_formadores_json.py" "${APP_DIR}/tools/"
    fi
fi

# 2b) formadores.json ausente mesmo após restaurar? Tenta regenerar da planilha.
if [ ! -f "${APP_DIR}/data/formadores.json" ] && [ -f "${APP_DIR}/tools/make_formadores_json.py" ]; then
    echo "Regenerando data/formadores.json..."
    (cd "${APP_DIR}" && "${VENV_PY}" tools/make_formadores_json.py) \
        || echo "Aviso: falha ao gerar formadores.json, presença de formador ficará desativada."
fi

# 3) Regenerar o CSV de salas a partir da planilha viva (fonte de verdade).
if [ -f "${APP_DIR}/tools/make_salas_csv.py" ]; then
    "${VENV_PY}" "${APP_DIR}/tools/make_salas_csv.py" || echo "Aviso: falha ao regenerar salas.csv, usando o existente."
fi

# 4) Subir o servidor em background.
cd "${APP_DIR}" || exit 1
nohup "${VENV_PY}" -m uvicorn app.main:app --host 127.0.0.1 --port "${PORT}" \
    > /tmp/eyes_uvicorn.log 2>&1 &
disown

# 5) Esperar até 30s pela porta responder.
for i in $(seq 1 30); do
    if curl -s -m 3 "http://127.0.0.1:${PORT}/api/status" >/dev/null 2>&1; then
        echo "Monitor no ar em 127.0.0.1:${PORT} (após ${i}s)."
        exit 0
    fi
    sleep 1
done

echo "ERRO: monitor não respondeu após 30s. Veja /tmp/eyes_uvicorn.log"
exit 1

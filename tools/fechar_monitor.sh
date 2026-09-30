#!/bin/bash
# ETI - Monitor de salas Google Meet ("eyes") - encerramento
# Idempotente: não falha se já estiver parado.
set -u

PID=$(pgrep -f "uvicorn app.main:app.*--port 8000" | head -1)

if [ -z "${PID}" ]; then
    echo "Monitor já estava parado."
    exit 0
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

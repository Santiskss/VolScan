#!/bin/bash
# VolScan — arranque local en Mac (doble clic o ./VolScan.command)
set -e
cd "$(dirname "$0")"
PY=${PYTHON:-python3}
if [ ! -d .venv ]; then
  echo "▶ Creando entorno Python…"
  $PY -m venv .venv
fi
.venv/bin/pip install -q -e ".[server]"
if [ ! -f web/dist/index.html ] || [ "${REBUILD:-0}" = "1" ]; then
  echo "▶ Compilando la interfaz web…"
  (cd web && npm ci --no-audit --no-fund && npm run build)
fi
if command -v ollama >/dev/null 2>&1; then
  echo "▶ IA local: Ollama detectado. Modelo: ${VOLSCAN_LLM_MODEL:-qwen3:8b} (cámbialo en .env)"
else
  echo "⚠ Ollama no está instalado: VolScan funciona igual, pero los partes y el asistente usarán solo recuperación."
fi
PORT=${PORT:-8200}
echo "▶ VolScan en http://localhost:$PORT"
( sleep 3; open "http://localhost:$PORT" 2>/dev/null || true ) &
exec .venv/bin/python -m uvicorn volscan.api.app:app --host 127.0.0.1 --port "$PORT"

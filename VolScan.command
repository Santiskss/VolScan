#!/bin/bash
# VolScan — arranque local en Mac (doble clic o ./VolScan.command)
set -e
cd "$(dirname "$0")"
# Python ≥ 3.10 (the macOS system one is 3.9): we look for the newest one available
PY=${PYTHON:-}
if [ -z "$PY" ]; then
  for c in python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v $c >/dev/null 2>&1 && $c -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)'; then PY=$c; break; fi
  done
fi
if [ -z "$PY" ]; then echo "✖ Necesitas Python 3.10 o superior (p. ej. brew install python@3.12)"; exit 1; fi
echo "▶ Python: $($PY --version)"
if [ ! -d .venv ]; then
  echo "▶ Creando entorno Python…"
  $PY -m venv .venv
fi
.venv/bin/pip install -q -e ".[server]"
# rebuild when there is no build, when asked, or when the sources changed after the last build (e.g. after git pull)
if [ ! -f web/dist/index.html ] || [ "${REBUILD:-0}" = "1" ] || [ -n "$(find web/src web/index.html web/package.json -newer web/dist/index.html 2>/dev/null | head -1)" ]; then
  echo "▶ Compilando la interfaz web…"
  command -v npm >/dev/null 2>&1 || { echo "✖ Necesitas Node.js 18+ (brew install node)"; exit 1; }
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

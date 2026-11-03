#!/bin/bash
# Despliegue completo de VolScan en Modal: Muse Glimmer en GPU + web.
# Uso (desde la carpeta de VolScan):   bash deploy/deploy.sh
set -euo pipefail
cd "$(dirname "$0")/.."

PY=.venv/bin/python
[ -x "$PY" ] || PY=python3
echo "▶ Instalando el cliente de Modal…"
$PY -m pip install -q --upgrade modal
MODAL="$PY -m modal"

if ! $MODAL profile current >/dev/null 2>&1; then
  echo "▶ Inicia sesión en Modal (se abre el navegador)…"
  $MODAL setup
fi

mkdir -p config
if [ -f config/glimmer.key ]; then KEY=$(cat config/glimmer.key); else KEY=$(openssl rand -hex 24); echo "$KEY" > config/glimmer.key; chmod 600 config/glimmer.key; fi

echo "▶ 1/3 Desplegando Muse Glimmer en GPU (A10)…"
$MODAL secret create --force volscan-glimmer "LLAMA_API_KEY=$KEY" >/dev/null
$MODAL deploy deploy/modal_glimmer.py | tee /tmp/volscan_glimmer_deploy.txt
GLIMMER_URL=$(grep -oE 'https://[A-Za-z0-9._-]*volscan-glimmer-serve[A-Za-z0-9._-]*\.modal\.run' /tmp/volscan_glimmer_deploy.txt | head -1)
[ -n "$GLIMMER_URL" ] || { echo "✖ No encuentro la URL de Glimmer en la salida de modal deploy"; exit 1; }
echo "   Glimmer: $GLIMMER_URL"

echo "▶ 2/3 Configurando la web…"
GLIMMER_URL="$GLIMMER_URL" KEY="$KEY" $PY - <<'PY'
import json, os, re
from pathlib import Path
env = {
    "VOLSCAN_LLM_BASE": os.environ["GLIMMER_URL"] + "/v1",
    "VOLSCAN_LLM_MODEL": "hf.co/meta-models/Muse-Glimmer-30B-GGUF:Q4_K_M",
    "VOLSCAN_LLM_KEY": os.environ["KEY"],
    "VOLSCAN_AUTH": "on",
}
cred = Path("config/PRODUCCION-credenciales.txt")
if cred.exists():
    m = re.search(r"^VOLSCAN_USERS_JSON=(.*)$", cred.read_text(), re.M)
    if m:
        env["VOLSCAN_USERS_JSON"] = m.group(1)
if "VOLSCAN_USERS_JSON" not in env:
    env["VOLSCAN_AUTH"] = "off"
p = Path("config/volscan-app.secret.json"); p.write_text(json.dumps(env)); p.chmod(0o600)
PY
$MODAL secret create --force volscan-app --from-json config/volscan-app.secret.json >/dev/null

if [ ! -f web/dist/index.html ]; then
  echo "▶ Compilando la interfaz…"; (cd web && npm ci --no-audit --no-fund && npm run build)
fi

echo "▶ 3/3 Desplegando la web…"
$MODAL deploy deploy/modal_app.py | tee /tmp/volscan_app_deploy.txt
APP_URL=$(grep -oE 'https://[A-Za-z0-9._-]*volscan-web[A-Za-z0-9._-]*\.modal\.run' /tmp/volscan_app_deploy.txt | head -1)

cat <<MSG

✔ Desplegado.
  VolScan:  ${APP_URL:-mira la URL de arriba}
  Glimmer:  $GLIMMER_URL

  Para grabar en el Mac usando la GPU (sin cargar el modelo en local), añade a .env:
    VOLSCAN_LLM_BASE=$GLIMMER_URL/v1
    VOLSCAN_LLM_KEY=(el contenido de config/glimmer.key)

  La primera pregunta al asistente tarda 5-10 min (descarga del modelo). Después, 1-3 min en frío.
MSG

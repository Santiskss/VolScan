"""VolScan web app (API + UI) on Modal.

From the repository root:

    (cd web && npm ci && npm run build)       # the UI is shipped pre-built
    modal deploy deploy/modal_app.py           # prints the public URL

The model is configured once in the "volscan-app" secret (see DEPLOY.md):
    modal secret create volscan-app \
        VOLSCAN_LLM_BASE=https://<workspace>--volscan-glimmer-serve.modal.run/v1 \
        VOLSCAN_LLM_MODEL=hf.co/meta-models/Muse-Glimmer-30B-GGUF:Q4_K_M \
        VOLSCAN_LLM_KEY=<LLAMA_API_KEY> VOLSCAN_AUTH=on VOLSCAN_USERS_JSON='...'

Built without the Dockerfile on purpose: Modal ignores USER and does not implement
HEALTHCHECK/EXPOSE, so a plain Modal image is the safer path here.
"""
from pathlib import Path

import modal

ROOT = Path(__file__).resolve().parents[1]
if not (ROOT / "web" / "dist" / "index.html").exists():
    raise SystemExit("Falta web/dist: ejecuta antes  (cd web && npm ci && npm run build)")

_ignore = ["**/__pycache__", "**/*.pyc", ".DS_Store"]
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("numpy>=1.24", "scipy>=1.10", "requests>=2.28", "pillow>=9", "reportlab>=4",
                 "fastapi>=0.110", "uvicorn>=0.27")
    .env({"PYTHONPATH": "/app", "VOLSCAN_PUBLIC_DEMO": "on"})
    .add_local_file(ROOT / "pyproject.toml", "/app/pyproject.toml", copy=True)
    .add_local_dir(ROOT / "data", "/app/data", copy=True, ignore=_ignore)
    .add_local_dir(ROOT / "knowledge", "/app/knowledge", copy=True, ignore=_ignore)
    .add_local_dir(ROOT / "web" / "dist", "/app/web/dist", copy=True, ignore=_ignore)
    .add_local_dir(ROOT / "volscan", "/app/volscan", copy=True, ignore=_ignore)
    .run_commands("mkdir -p /app/out /app/config")
)
app = modal.App("volscan")


@app.function(
    image=image,
    cpu=1.0,
    memory=3072,
    secrets=[modal.Secret.from_name("volscan-app")],
    scaledown_window=300,            # scales to zero after 5 idle min: you only pay while someone uses it
    timeout=60 * 10,
)
@modal.concurrent(max_inputs=50)
@modal.web_server(port=8200, startup_timeout=180)
def web():
    import subprocess

    subprocess.Popen(
        "cd /app && uvicorn volscan.api.app:app --host 0.0.0.0 --port 8200 --proxy-headers --forwarded-allow-ips='*'",
        shell=True,
    )

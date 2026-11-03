"""VolScan web app (API + UI) on Modal, built from the repository Dockerfile.

    modal deploy deploy/modal_app.py      # from the repository root

Model: create the secret once, pointing to the Glimmer endpoint (deploy/modal_glimmer.py)
or to the Meta Model API:
    modal secret create volscan-app \
        VOLSCAN_LLM_BASE=https://<workspace>--volscan-glimmer-serve.modal.run/v1 \
        VOLSCAN_LLM_MODEL=hf.co/meta-models/Muse-Glimmer-30B-GGUF:Q4_K_M \
        VOLSCAN_LLM_KEY=<LLAMA_API_KEY>
(Meta API instead: META_API_KEY=... and no VOLSCAN_LLM_BASE.)
"""
from pathlib import Path

import modal

ROOT = Path(__file__).resolve().parents[1]
image = modal.Image.from_dockerfile(ROOT / "Dockerfile", context_dir=ROOT)
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

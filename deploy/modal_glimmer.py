"""Meta Muse Glimmer 30B on a Modal GPU, behind an OpenAI-compatible API (llama.cpp server).

Used by the public VolScan deployment, where there is no Mac with Ollama next to the server.

    pip install modal && modal setup
    modal secret create volscan-glimmer LLAMA_API_KEY=$(openssl rand -hex 24)
    modal deploy deploy/modal_glimmer.py

Then in the VolScan server environment:
    VOLSCAN_LLM_BASE=https://<workspace>--volscan-glimmer-serve.modal.run/v1
    VOLSCAN_LLM_MODEL=hf.co/meta-models/Muse-Glimmer-30B-GGUF:Q4_K_M
    VOLSCAN_LLM_KEY=<the same LLAMA_API_KEY>

The GPU scales to zero after 10 idle minutes; the first request after that waits for a cold
start (~1-3 min with the weights cached in the volume). Warm it up before recording a demo.
"""
import subprocess

import modal

MODEL_REPO = "meta-models/Muse-Glimmer-30B-GGUF:Q4_K_M"   # ~17 GB weights + 1.4 GB vision projector
PORT = 8080

image = (
    modal.Image.from_registry("ghcr.io/ggml-org/llama.cpp:server-cuda", add_python="3.12")
    .entrypoint([])
    .env({"LLAMA_CACHE": "/cache"})
)
cache = modal.Volume.from_name("volscan-glimmer-cache", create_if_missing=True)
app = modal.App("volscan-glimmer")


@app.function(
    image=image,
    gpu="L40S",                      # 48 GB: weights + vision + 32k context with room to spare
    volumes={"/cache": cache},
    secrets=[modal.Secret.from_name("volscan-glimmer")],
    scaledown_window=600,
    timeout=60 * 60,
)
@modal.concurrent(max_inputs=4)
@modal.web_server(port=PORT, startup_timeout=20 * 60)
def serve():
    import os

    subprocess.Popen([
        "/app/llama-server",
        "-hf", MODEL_REPO,
        "--jinja",                    # required by Glimmer's chat template (tool calling)
        "--host", "0.0.0.0", "--port", str(PORT),
        "-ngl", "999",                # everything on the GPU
        "-c", "32768",
        "--parallel", "4",
        "--api-key", os.environ["LLAMA_API_KEY"],
    ])

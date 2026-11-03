"""Meta Muse Glimmer (open weights, local) is VolScan's default model."""
from __future__ import annotations

import json

from volscan.adapters import MetaGlimmerLocalAdapter
from volscan.ai import llm
from volscan.application import META_MODEL_PRESETS, VolScanContainer
from volscan.ports import LanguageModelPort, MultimodalVisionLanguagePort


def _clear(monkeypatch):
    for k in ("META_API_KEY", "VOLSCAN_LLM_BASE", "VOLSCAN_LLM_MODEL", "VOLSCAN_LLM_ADAPTER",
              "VOLSCAN_GLIMMER_MODEL", "VOLSCAN_GLIMMER_BASE", "VOLSCAN_REASONING_STRENGTH"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(llm, "_load_dotenv", lambda: None)
    import volscan.adapters.meta_ai as m
    monkeypatch.setattr(m, "_load_dotenv", lambda: None)


def test_default_config_is_glimmer_local(monkeypatch):
    _clear(monkeypatch)
    cfg = llm.LLMConfig.from_env()
    assert cfg.model == llm.GLIMMER_DEFAULT_MODEL
    assert cfg.provider == "meta-local"
    assert cfg.adapter_name == "MetaGlimmerLocalAdapter"
    assert cfg.public()["open_weights"] is True
    assert cfg.public()["base"].startswith("http://localhost")


def test_meta_api_key_still_switches_to_muse_spark(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("META_API_KEY", "k")
    cfg = llm.LLMConfig.from_env()
    assert cfg.provider == "meta" and cfg.model == "muse-spark-1.3"


def test_other_local_model_is_labelled_local(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("VOLSCAN_LLM_MODEL", "qwen3:8b")
    cfg = llm.LLMConfig.from_env()
    assert cfg.provider == "local" and cfg.adapter_name == "OllamaLocalAdapter"


def test_glimmer_adapter_conforms_and_preset_swaps(monkeypatch):
    _clear(monkeypatch)
    a = MetaGlimmerLocalAdapter()
    assert isinstance(a, LanguageModelPort) and isinstance(a, MultimodalVisionLanguagePort)
    assert a.timeout >= 300
    assert "meta_glimmer_local" in META_MODEL_PRESETS
    st = VolScanContainer().switch_llm_adapter("meta_glimmer_local")
    assert st["adapter"] == "MetaGlimmerLocalAdapter" and st["provider"] == "meta-local"


def test_reasoning_strength_goes_in_system_prompt(monkeypatch):
    _clear(monkeypatch)
    msgs = [dict(role="system", content="Eres VolScan."), dict(role="user", content="hola")]
    out = llm.with_reasoning_strength(msgs, llm.GLIMMER_DEFAULT_MODEL)
    assert out[0]["content"].startswith("Reasoning strength: low\n\nEres VolScan.")
    assert msgs[0]["content"] == "Eres VolScan."          # caller's list untouched
    monkeypatch.setenv("VOLSCAN_REASONING_STRENGTH", "high")
    out = llm.with_reasoning_strength([dict(role="user", content="x")], llm.GLIMMER_DEFAULT_MODEL)
    assert out[0] == dict(role="system", content="Reasoning strength: high")
    assert llm.with_reasoning_strength(msgs, "qwen3:8b") is msgs


def test_glimmer_request_body(monkeypatch):
    _clear(monkeypatch)
    sent = {}

    class R:
        status_code = 200
        def json(self):
            return {"choices": [{"message": {"content": "<think>x</think>Parte listo.", "tool_calls": [
                {"id": "c1", "function": {"name": "canarias_live", "arguments": json.dumps({"zone": "tenerife"})}}]}}]}

    import requests
    def fake_post(url, headers=None, data=None, timeout=None):
        sent.update(url=url, body=json.loads(data), timeout=timeout)
        return R()
    monkeypatch.setattr(requests, "post", fake_post)
    turn = MetaGlimmerLocalAdapter().complete([dict(role="user", content="¿Cómo está Tenerife?")])
    assert sent["url"] == "http://localhost:11434/v1/chat/completions"
    assert sent["body"]["model"] == llm.GLIMMER_DEFAULT_MODEL
    assert sent["body"]["messages"][0]["content"].startswith("Reasoning strength:")
    assert sent["timeout"] >= 300
    assert turn.content == "Parte listo." and turn.tool_calls[0].arguments == {"zone": "tenerife"}
    assert turn.provider == "meta-local"

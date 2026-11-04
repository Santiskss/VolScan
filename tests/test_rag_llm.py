import datetime as dt

import pytest

from volscan.ai import llm
from volscan.ai.rag import Chunk, Index, build_data_docs, build_prompt, load_curated, split_markdown, tokenize
from volscan.sources.ign_catalog import IgnEvent


def test_tokenize_strips_accents_and_stopwords():
    assert tokenize("La erupción de Tajogaite") == ["erupcion", "tajogaite"]


def test_split_markdown_keeps_title_and_section():
    ch = split_markdown("x", "# Título\n\n## Sección A\ntexto a\n## Sección B\ntexto b")
    assert [(c.doc, c.section) for c in ch] == [("Título", "Sección A"), ("Título", "Sección B")]


def test_curated_knowledge_answers_basic_questions():
    idx = Index(load_curated())
    top = idx.search("¿Cuándo llegó la lava al mar en La Palma?", k=3)
    assert any("Tajogaite" in c.doc for c, _ in top)
    top = idx.search("Tagoro La Restinga", k=2)
    assert "Hierro" in top[0][0].doc


def test_data_docs_from_events():
    t = dt.datetime(2021, 9, 12, tzinfo=dt.timezone.utc)
    ev = [IgnEvent("a", t, 28.6, -17.85, 10.0, 2.5, "mbLg", "", "EL PASO.ILP"),
          IgnEvent("b", t, 28.6, -17.85, 5.0, 3.1, "mbLg", "III", "EL PASO.ILP")]
    docs = build_data_docs(ev)
    assert len(docs) == 1 and "La Palma" in docs[0].doc
    assert "2 earthquakes" in docs[0].text and "3.1" in docs[0].text and "maximum intensity III" in docs[0].text


def test_prompt_contains_numbered_context_and_rules():
    idx = Index([Chunk("Doc", "S", "contenido de prueba volcán")])
    msgs = build_prompt("volcán", idx.search("volcán"), live={"x": 1})
    assert msgs[0]["role"] == "system" and "PEVOLCA" in msgs[0]["content"]
    assert "[1] Doc — S" in msgs[1]["content"] and "LIVE DATA" in msgs[1]["content"]


def test_llm_unavailable_is_an_explicit_error(monkeypatch):
    monkeypatch.setenv("VOLSCAN_LLM_BASE", "http://127.0.0.1:9/v1")
    with pytest.raises(llm.LLMUnavailable):
        llm.chat([{"role": "user", "content": "hola"}], timeout=2)


def test_config_prefers_meta_when_key_present(monkeypatch):
    monkeypatch.delenv("VOLSCAN_LLM_BASE", raising=False)
    monkeypatch.setenv("META_API_KEY", "test")
    monkeypatch.delenv("VOLSCAN_LLM_MODEL", raising=False)
    cfg = llm.LLMConfig.from_env()
    assert cfg.provider == "meta" and cfg.model == "muse-spark-1.3"
    assert "test" not in str(cfg.public())

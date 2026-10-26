"""Retrieval over VolScan's knowledge base: curated documents + summaries generated from the data.

- Curated documents: `knowledge/*.md`, written with their sources cited.
- Generated documents (`build_data_docs`): monthly summaries of seismicity per
  zone from the IGN catalogue, and the table of Copernicus EMS lava
  observations. They are numbers computed from the data, not text written by
  a model.

Retrieval: BM25 (dependency-free, deterministic). If an embeddings model
responds (Ollama `nomic-embed-text` or Meta), it's combined with cosine
similarity (hybrid by rank, RRF). Each fragment keeps its document and
section so the answer can cite them.
"""
from __future__ import annotations

import datetime as dt
import math
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE = ROOT / "knowledge"

_STOP = set("""a al algo ante antes como con contra cual cuando de del desde donde dos el ella ellas ellos en entre era
es esa ese eso esta estan este esto fue ha han hay la las le les lo los mas me mi muy no nos o otra otro para pero
por que se sea ser si sin sobre son su sus tambien te tiene un una uno unos y ya the of and in to is for on at by with""".split())


def tokenize(text: str) -> list[str]:
    t = unicodedata.normalize("NFKD", text.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return [w for w in re.findall(r"[a-z0-9]+(?:[.,][0-9]+)?", t) if w not in _STOP and len(w) > 1]


@dataclass
class Chunk:
    doc: str
    section: str
    text: str
    kind: str = "curated"          # curated | data
    tokens: list = field(default_factory=list)


def split_markdown(name: str, md: str, kind: str = "curated", max_chars: int = 1400) -> list[Chunk]:
    chunks, title, section, buf = [], name, "", []

    def flush():
        body = "\n".join(buf).strip()
        if body:
            for k in range(0, len(body), max_chars):
                chunks.append(Chunk(title, section, body[k:k + max_chars], kind))
        buf.clear()

    for line in md.splitlines():
        if line.startswith("# "):
            flush()
            title = line[2:].strip()
        elif line.startswith("## "):
            flush()
            section = line[3:].strip()
        else:
            buf.append(line)
    flush()
    return chunks


class Index:
    def __init__(self, chunks: list[Chunk], k1: float = 1.4, b: float = 0.75):
        self.chunks = chunks
        for c in chunks:
            c.tokens = tokenize(f"{c.doc} {c.section} {c.text}")
        self.k1, self.b = k1, b
        self.df = Counter()
        for c in chunks:
            self.df.update(set(c.tokens))
        self.avgdl = sum(len(c.tokens) for c in chunks) / max(1, len(chunks))
        self.tf = [Counter(c.tokens) for c in chunks]
        self.emb = None

    def bm25(self, query: str) -> np.ndarray:
        q = tokenize(query)
        n = len(self.chunks)
        s = np.zeros(n)
        for term in set(q):
            df = self.df.get(term, 0)
            if not df:
                continue
            idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
            for i, tf in enumerate(self.tf):
                f = tf.get(term, 0)
                if f:
                    dl = len(self.chunks[i].tokens)
                    s[i] += idf * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
        return s

    def try_embeddings(self, embed_fn) -> bool:
        vecs = embed_fn([f"{c.doc} · {c.section}\n{c.text}" for c in self.chunks])
        if not vecs:
            return False
        m = np.array(vecs, float)
        self.emb = m / np.maximum(np.linalg.norm(m, axis=1, keepdims=True), 1e-9)
        return True

    def search(self, query: str, k: int = 6, embed_fn=None) -> list[tuple[Chunk, float]]:
        s = self.bm25(query)
        order = list(np.argsort(-s))
        if self.emb is not None and embed_fn is not None:
            qv = embed_fn([query])
            if qv:
                q = np.array(qv[0], float)
                q /= max(np.linalg.norm(q), 1e-9)
                cos = self.emb @ q
                r1 = {i: r for r, i in enumerate(order)}
                r2 = {i: r for r, i in enumerate(np.argsort(-cos))}
                fused = {i: 1 / (60 + r1[i]) + 1 / (60 + r2[i]) for i in range(len(self.chunks))}
                order = sorted(fused, key=lambda i: -fused[i])
                return [(self.chunks[i], fused[i]) for i in order[:k]]
        return [(self.chunks[i], float(s[i])) for i in order[:k] if s[i] > 0]


def load_curated() -> list[Chunk]:
    out = []
    for f in sorted(KNOWLEDGE.glob("*.md")):
        out.extend(split_markdown(f.stem, f.read_text(encoding="utf-8")))
    return out


MONTHS = "ene feb mar abr may jun jul ago sep oct nov dic".split()


def build_data_docs(events, lava_obs=None) -> list[Chunk]:
    """Monthly seismic summaries per zone (IGN) + the CEMS lava observation table, as retrievable text."""
    from ..zones import BY_KEY, zone_of
    groups = defaultdict(list)
    for e in events:
        groups[(zone_of(e.lat, e.lon).key, e.time_utc.year, e.time_utc.month)].append(e)
    chunks = []
    for (zk, y, m), evs in sorted(groups.items()):
        mags = [e.mag for e in evs if e.mag is not None]
        deps = sorted(e.depth_km for e in evs if e.depth_km is not None)
        big = max(evs, key=lambda e: e.mag if e.mag is not None else -9)
        felt = [e for e in evs if e.int_max]
        zname = BY_KEY[zk].name
        txt = (f"Sismicidad en {zname} en {MONTHS[m - 1]} de {y} según el catálogo del IGN: {len(evs)} terremotos localizados. "
               + (f"Magnitud máxima {max(mags):.1f} ({big.mag_type}) el {big.time_utc:%d-%m-%Y %H:%M} UTC en {big.location}, "
                  f"a {big.depth_km if big.depth_km is not None else '—'} km. " if mags else "")
               + (f"Profundidad mediana {deps[len(deps) // 2]:.1f} km (entre {deps[0]:.0f} y {deps[-1]:.0f} km). " if deps else "")
               + (f"{len(felt)} sentidos (intensidad máxima {max(e.int_max for e in felt)}). " if felt else "Ninguno con intensidad registrada. "))
        chunks.append(Chunk(f"Catálogo IGN · {zname}", f"{MONTHS[m - 1]} {y}", txt, "data"))
    if lava_obs:
        rows = [f"{o.observed_at:%d-%m-%Y %H:%M} UTC: {o.area_ha_reported:.0f} ha" for o in lava_obs if o.area_ha_reported]
        for k in range(0, len(rows), 16):
            chunks.append(Chunk("Copernicus EMS EMSR546 · coladas La Palma 2021", f"observaciones {k + 1}-{min(k + 16, len(rows))}",
                                "Superficie cartografiada de las coladas de Tajogaite (Copernicus EMS, fotointerpretación): "
                                + "; ".join(rows[k:k + 16]) + ".", "data"))
    return chunks


_INDEX: Index | None = None


def get_index(events=None, lava_obs=None, rebuild: bool = False) -> Index:
    global _INDEX
    if _INDEX is None or rebuild:
        chunks = load_curated()
        if events:
            chunks += build_data_docs(events, lava_obs)
        _INDEX = Index(chunks)
    return _INDEX


SYSTEM = """Eres el analista de VolScan (TephraLabs), un sistema de apoyo a la decisión sobre riesgo volcánico en Canarias.
Reglas:
- Responde en español, claro y breve, para técnicos de emergencias.
- Usa SOLO la información del CONTEXTO y los DATOS EN VIVO que se te dan. Si algo no está, di que no consta.
- Cita las fuentes entre corchetes con el número del fragmento, p. ej. [2].
- VolScan NO emite niveles de alerta ni probabilidades de erupción: las alertas son del PEVOLCA. Nunca afirmes que habrá o no habrá una erupción.
- Distingue siempre histórico, simulación/pronóstico y dato en directo. Las cifras con su incertidumbre."""


def build_prompt(question: str, hits, live: dict | None = None) -> list[dict]:
    ctx = "\n\n".join(f"[{i + 1}] {c.doc} — {c.section}\n{c.text}" for i, (c, _) in enumerate(hits))
    user = f"CONTEXTO:\n{ctx}\n\n"
    if live:
        import json
        user += f"DATOS EN VIVO (calculados por VolScan ahora):\n{json.dumps(live, ensure_ascii=False, default=str)[:4000]}\n\n"
    user += f"PREGUNTA: {question}"
    return [dict(role="system", content=SYSTEM), dict(role="user", content=user)]


def cite(hits) -> list[dict]:
    return [dict(n=i + 1, doc=c.doc, section=c.section, kind=c.kind, excerpt=c.text[:280]) for i, (c, _) in enumerate(hits)]


def today_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

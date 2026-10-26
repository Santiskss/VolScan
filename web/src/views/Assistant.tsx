import { useState } from 'react'
import { api, type Citation } from '../api'

type Msg = { role: 'user' | 'ai'; text: string; citations?: Citation[]; meta?: string }

const SUGGEST = [
  '¿Qué precursores sísmicos tuvo la erupción de La Palma de 2021?',
  '¿Cómo está ahora la actividad sísmica en Tenerife?',
  '¿Cuánto tardó la lava en llegar al mar en 2021 y dónde?',
  'Compara la crisis de El Hierro 2011 con la de La Palma 2021',
  '¿Qué erupciones históricas ha tenido Lanzarote?',
]

export default function Assistant() {
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [q, setQ] = useState('')
  const [ctx, setCtx] = useState('canarias')
  const [busy, setBusy] = useState(false)
  const ask = (question: string) => {
    if (!question.trim() || busy) return
    setMsgs((m) => [...m, { role: 'user', text: question }])
    setQ('')
    setBusy(true)
    api.chat(question, ctx || undefined).then((r) => {
      setMsgs((m) => [...m, r.ai
        ? { role: 'ai', text: r.answer ?? '', citations: r.citations, meta: `${r.model.provider === 'meta' ? 'Meta' : 'Modelo local'} · ${r.model.model}` }
        : { role: 'ai', text: `No hay modelo de lenguaje disponible (${r.error}). Estos son los fragmentos más relevantes de la base de conocimiento:`, citations: r.citations, meta: 'solo recuperación (RAG sin generación)' }])
    }).catch((e) => setMsgs((m) => [...m, { role: 'ai', text: `Error: ${e}` }])).finally(() => setBusy(false))
  }
  return (
    <div className="page">
      <h2>Asistente VolScan</h2>
      <p className="lead">Responde con la base de conocimiento de VolScan (erupciones de Canarias, La Palma 2021, El Hierro 2011, actividad actual en Tenerife y metodología) y con los datos que calcula en directo a partir del catálogo del IGN. Cita sus fuentes. No emite alertas: las oficiales son del PEVOLCA.</p>
      <div className="chat">
        {msgs.length === 0 && <div className="suggest">{SUGGEST.map((s) => <button key={s} onClick={() => ask(s)}>{s}</button>)}</div>}
        {msgs.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            {m.text}
            {m.citations && m.citations.length > 0 && <div className="cites">{m.citations.map((c) => <div key={c.n} className="cite"><b>[{c.n}] {c.doc}</b> — {c.section}{m.meta?.startsWith('solo') ? <div>{c.excerpt}…</div> : null}</div>)}</div>}
            {m.meta && <div className="note" style={{ marginTop: 6 }}>{m.meta}</div>}
          </div>
        ))}
        {busy && <div className="loading">Buscando en la base de conocimiento y redactando…</div>}
        <div className="ask">
          <select value={ctx} onChange={(e) => setCtx(e.target.value)}>
            <option value="canarias">Datos en vivo: Canarias</option>
            <option value="lapalma2021:2021-09-18">La Palma · 18 sep 2021</option>
            <option value="lapalma2021:2021-09-22">La Palma · 22 sep 2021</option>
            <option value="lapalma2021:2021-10-15">La Palma · 15 oct 2021</option>
            <option value="">Sin datos en vivo</option>
          </select>
          <input type="text" value={q} placeholder="Pregunta sobre volcanes y sismicidad en Canarias…" onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && ask(q)} />
          <button className="btn primary" disabled={busy} onClick={() => ask(q)}>Preguntar</button>
        </div>
      </div>
    </div>
  )
}

import { useEffect, useState } from 'react'
import { api, fmt, STATIC, type Status } from './api'
import AtlasLaPalma from './views/AtlasLaPalma'
import Assistant from './views/Assistant'
import CanariasLive from './views/CanariasLive'
import Solunar from './views/Solunar'

const TABS = [
  ['atlas', 'Atlas volcánico · 3D'],
  ['canarias', 'Canarias en directo'],
  ['mareas', 'Mareas y Luna'],
  ['asistente', 'Asistente IA'],
] as const
type Tab = (typeof TABS)[number][0]

const HEADERS: Record<Tab, [string, string, string]> = {
  atlas: ['La Palma', 'Tajogaite · 19 sep – 13 dic 2021 · EMSR546', 'Histórico real · reconstrucción, no en directo'],
  canarias: ['Canarias', 'Sismicidad por zona volcánica', 'En directo · catálogo IGN'],
  mareas: ['Canarias', 'Correlación solunar · 2011–hoy', 'Hipótesis medida, no asumida'],
  asistente: ['Canarias', 'RAG sobre conocimiento y datos', 'Apoyo a la decisión · no alerta'],
}

function Logo() {
  return (
    <span className="logo">
      <svg viewBox="0 0 32 32"><path d="M16 3 L29 28 H3 Z" fill="#b4532f" /><path d="M16 3 L20 11 L12 11 Z" fill="#f3efe6" /></svg>
      VolScan
    </span>
  )
}

export default function App() {
  const [tab, setTab] = useState<Tab>(() => (location.hash.slice(1).split('@')[0] as Tab) || 'atlas')
  const [status, setStatus] = useState<Status | null>(null)
  useEffect(() => { if (location.hash.slice(1).split('@')[0] !== tab) location.hash = tab }, [tab])
  useEffect(() => {
    const load = () => api.status().then(setStatus).catch(() => setStatus(null))
    load()
    const t = setInterval(load, 60000)
    return () => clearInterval(t)
  }, [])
  const [place, sub, badge] = HEADERS[tab]
  const llm = status?.llm
  return (
    <>
      <div className="topbar">
        {TABS.map(([k, label]) => <button key={k} className={`tab ${tab === k ? 'active' : ''}`} onClick={() => setTab(k)}>{label}</button>)}
        <span className="spacer" />
        <span className="chip"><span className={`dot ${llm?.ok ? 'ok' : 'warn'}`} />{STATIC ? 'IA: solo en versión local' : <>IA: {llm ? (llm.provider === 'meta' ? 'Meta · ' : 'Local · ') + llm.model : '—'}{llm && !llm.ok ? ' (sin conexión)' : ''}</>}</span>
        <span className="chip"><span className={`dot ${status?.catalog.refresh_error ? 'warn' : 'ok'}`} />IGN: {status ? `${fmt.int(status.catalog.n_events)} sismos` : '—'}</span>
        {STATIC && status && <span className="chip"><span className="dot warn" />Instantánea · {fmt.dateTime(status.now)}</span>}
      </div>
      <div className="header">
        <Logo />
        <span className="sep" />
        <span className="kicker">Volcano Atlas</span>
        <span className="place-title">{place}</span>
        <span className="note" style={{ fontSize: 12.5 }}>{sub}</span>
        <span style={{ flex: 1 }} />
        <span className="badge">{badge}</span>
      </div>
      {tab === 'atlas' && <AtlasLaPalma />}
      {tab === 'canarias' && <CanariasLive />}
      {tab === 'mareas' && <Solunar />}
      {tab === 'asistente' && <Assistant />}
    </>
  )
}

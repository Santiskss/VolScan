import { useEffect, useState } from 'react'
import { api, authEvents, fmt, modelLabel, setToken, STATIC, type AuthUser, type Status } from './api'
import AuditLog from './views/AuditLog'
import Login from './views/Login'
import AtlasLaPalma from './views/AtlasLaPalma'
import CanariasLive from './views/CanariasLive'
import Reports from './views/Reports'
import TenerifeScenarios from './views/TenerifeScenarios'
import Validation from './views/Validation'

const TABS = [
  ['atlas', 'Atlas 3D · Caso Real 2021'],
  ['canarias', 'Canarias en directo (IGN)'],
  ['tenerife', 'Tenerife · Simulación'],
  ['validacion', 'Validación (Real vs Estimado)'],
  ['informes', 'Dossier de Crisis e Informes'],
  ['registro', 'Registro ENS'],
] as const
type Tab = (typeof TABS)[number][0]

const HEADERS: Record<Tab, [string, string, string]> = {
  atlas: ['La Palma 2021', 'Dato real (IGN + Copernicus EMS) + Pronóstico asimilado VolScan a 72 h', 'Caso real + Modelo'],
  canarias: ['Canarias hoy', 'Telemetría real en directo (IGN sismos · NGL GNSS · NASA SO2) + Índice VolScan', '100 % Dato en directo'],
  tenerife: ['Tenerife', 'Simulación condicional a 30 días sobre MDE real si abriera una boca', 'Simulación de planificación'],
  validacion: ['Auditoría 2021', 'Comparación de los 83 pronósticos de VolScan frente a lo cartografiado por Copernicus', 'Acierto medido: 81 %'],
  registro: ['VolScan', 'Trazabilidad criptográfica SHA-256 de acciones y exportaciones', 'Seguridad · ENS'],
  informes: ['Informes y Crisis', 'Dossier de Catástrofe (Tajogaite 2021: reología, evolución, mareas) y boletines por isla', 'Dato real vs Estimado'],
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
  const [tab, setTab] = useState<Tab>(() => ((TABS.map((t) => t[0]) as string[]).includes(location.hash.slice(1).split('@')[0]) ? location.hash.slice(1).split('@')[0] as Tab : 'atlas'))
  const [visited, setVisited] = useState<Record<string, boolean>>(() => ({ [tab]: true }))
  const [status, setStatus] = useState<Status | null>(null)
  const [auth, setAuth] = useState<{ enabled: boolean; user: AuthUser | null } | null>(null)
  useEffect(() => {
    api.authConfig().then((a) => setAuth({ enabled: a.enabled, user: a.user })).catch(() => setAuth({ enabled: true, user: null }))
    const h = () => { setToken(null); setAuth((a) => ({ enabled: a?.enabled ?? true, user: null })) }
    authEvents.addEventListener('unauthorized', h)
    return () => authEvents.removeEventListener('unauthorized', h)
  }, [])
  useEffect(() => {
    setVisited((v) => (v[tab] ? v : { ...v, [tab]: true }))
    if (location.hash.slice(1).split('@')[0] !== tab) location.hash = tab
  }, [tab])
  useEffect(() => {
    const load = () => api.status().then(setStatus).catch(() => setStatus(null))
    load()
    const t = setInterval(load, 60000)
    return () => clearInterval(t)
  }, [])
  const [place, sub, badge] = HEADERS[tab]
  const isAdmin = !auth?.enabled || auth?.user?.role === 'admin'
  const tabs = TABS.filter(([k]) => k !== 'registro' || (!STATIC && isAdmin))
  if (auth?.enabled && !auth.user) return <><div className="topbar"><span className="spacer" /></div><Login onDone={(u) => setAuth({ enabled: true, user: u })} /></>
  const llm = status?.llm
  return (
    <>
      <div className="topbar">
        {tabs.map(([k, label]) => <button key={k} className={`tab ${tab === k ? 'active' : ''}`} onClick={() => setTab(k)}>{label}</button>)}
        <span className="spacer" />
        {status?.vision && <span className="chip" title={status.vision.note}><span className={`dot ${status.vision.ready ? 'ok' : 'warn'}`} />Visión: {status.vision.mode === 'remote_api' ? 'endpoint configurado' : 'algoritmo determinista · sin pesos SAM'}</span>}
        <span className="chip"><span className={`dot ${llm?.ok ? 'ok' : 'warn'}`} />{STATIC ? 'IA: solo en versión local' : <>IA: {llm ? modelLabel(llm.provider, llm.model) : '—'}{llm && !llm.ok ? ' (modo determinista)' : ''}</>}</span>
        <span className="chip" title={status?.catalog.health?.message ?? ''}><span className={`dot ${!STATIC && status?.catalog.health && !status.catalog.health.ok ? 'warn' : 'ok'}`} />IGN: {status ? `${fmt.int(status.catalog.n_events)} sismos` : '—'}{!STATIC && status?.catalog.health && !status.catalog.health.ok ? ` · ${status.catalog.health.level}` : ''}</span>
        {STATIC && status && <span className="chip"><span className="dot warn" />Instantánea · {fmt.dateTime(status.now)}</span>}
        {auth?.enabled && auth.user && <span className="chip"><span className="dot ok" />{auth.user.name} · {auth.user.role}<button className="linklike" onClick={() => { api.logout().finally(() => { setToken(null); setAuth({ enabled: true, user: null }) }) }}>Salir</button></span>}
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
      {visited.atlas && <div style={{ display: tab === 'atlas' ? 'contents' : 'none' }}><AtlasLaPalma /></div>}
      {visited.canarias && <div style={{ display: tab === 'canarias' ? 'contents' : 'none' }}><CanariasLive /></div>}
      {visited.tenerife && <div style={{ display: tab === 'tenerife' ? 'contents' : 'none' }}><TenerifeScenarios /></div>}
      {visited.validacion && <div style={{ display: tab === 'validacion' ? 'contents' : 'none' }}><Validation /></div>}
      {visited.informes && <div style={{ display: tab === 'informes' ? 'contents' : 'none' }}><Reports /></div>}
      {visited.registro && <div style={{ display: tab === 'registro' ? 'contents' : 'none' }}><AuditLog /></div>}
    </>
  )
}

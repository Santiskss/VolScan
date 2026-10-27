import { useEffect, useState } from 'react'
import { api, fmt, type AuditEntry } from '../api'

export default function AuditLog() {
  const [d, setD] = useState<{ entries: AuditEntry[]; chain: { ok: boolean; lines: number; broken_at?: number }; auth_enabled: boolean } | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const load = () => api.audit(300).then(setD).catch((e) => setErr(String(e)))
  useEffect(() => { load() }, [])
  return (
    <div className="page">
      <h2>Registro de auditoría</h2>
      <p className="lead">Cada llamada a VolScan queda anotada con hora, usuario, rol y resultado. Cada línea lleva la huella (SHA-256) de la anterior: si alguien borra o cambia una, la cadena se rompe y se ve aquí.</p>
      {err && <div className="note">{err}</div>}
      {d && <div className="kpis kpis-page">
        <div className="kpi"><div className="k">Cadena de integridad</div><div className="v" style={{ fontSize: 20 }}><span className={`lvl ${d.chain.ok ? 'ok' : 'bad'}`}>{d.chain.ok ? 'íntegra' : `rota en la línea ${d.chain.broken_at}`}</span></div><div className="s">{fmt.int(d.chain.lines)} entradas verificadas</div></div>
        <div className="kpi"><div className="k">Control de acceso</div><div className="v" style={{ fontSize: 20 }}>{d.auth_enabled ? 'activado' : 'demo local'}</div><div className="s">{d.auth_enabled ? 'usuarios con rol lector, técnico o admin' : 'sin usuarios (VOLSCAN_AUTH=off); todo se registra como «local»'}</div></div>
        <div className="kpi"><div className="k">Mostradas</div><div className="v">{d.entries.length}</div><div className="s">las más recientes primero</div></div>
        <div className="kpi"><div className="k">Exportar</div><div className="v" style={{ fontSize: 15 }}><button className="btn" onClick={load}>Actualizar</button></div><div className="s">el archivo completo está en out/audit/audit.jsonl</div></div>
      </div>}
      {d && <div className="card" style={{ marginTop: 14 }}>
        <table className="places">
          <thead><tr><th>Hora (UTC)</th><th>Usuario</th><th>Rol</th><th>Acción</th><th>Resultado</th></tr></thead>
          <tbody>{d.entries.map((e, i) => <tr key={i}><td>{fmt.dateTime(e.t)}</td><td>{e.user ?? '—'}</td><td>{e.role ?? '—'}</td>
            <td><code>{e.method} {e.path}{e.query ? `?${e.query}` : ''}</code>{e.event ? <span className="note"> · {e.event}</span> : null}</td>
            <td><span className={`lvl ${e.status < 400 ? 'ok' : e.status === 401 || e.status === 403 ? 'warn' : 'bad'}`}>{e.status}</span></td></tr>)}</tbody>
        </table>
      </div>}
    </div>
  )
}

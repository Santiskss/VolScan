import { useEffect, useState } from 'react'
import { api, fmt, type AuditEntry } from '../api'

export default function AuditLog() {
  const [d, setD] = useState<{ entries: AuditEntry[]; chain: { ok: boolean; lines: number; broken_at?: number }; auth_enabled: boolean } | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const load = () => api.audit(300).then(setD).catch((e) => setErr(String(e)))
  useEffect(() => { load() }, [])
  return (
    <div className="page">
      <h2>Audit log</h2>
      <p className="lead">Every call to VolScan is logged with time, user, role and result. Each line carries the SHA-256 fingerprint of the previous one: if someone deletes or edits a line, the chain breaks and it shows here.</p>
      {err && <div className="note">{err}</div>}
      {d && <div className="kpis kpis-page">
        <div className="kpi"><div className="k">Integrity chain</div><div className="v" style={{ fontSize: 20 }}><span className={`lvl ${d.chain.ok ? 'ok' : 'bad'}`}>{d.chain.ok ? 'intact' : `broken at line ${d.chain.broken_at}`}</span></div><div className="s">{fmt.int(d.chain.lines)} entries verified</div></div>
        <div className="kpi"><div className="k">Access control</div><div className="v" style={{ fontSize: 20 }}>{d.auth_enabled ? 'enabled' : 'local demo'}</div><div className="s">{d.auth_enabled ? 'users with reader, technician or admin role' : 'no users (VOLSCAN_AUTH=off); everything is logged as “local”'}</div></div>
        <div className="kpi"><div className="k">Shown</div><div className="v">{d.entries.length}</div><div className="s">most recent first</div></div>
        <div className="kpi"><div className="k">Export</div><div className="v" style={{ fontSize: 15 }}><button className="btn" onClick={load}>Refresh</button></div><div className="s">the full file is in out/audit/audit.jsonl</div></div>
      </div>}
      {d && <div className="card" style={{ marginTop: 14 }}>
        <table className="places">
          <thead><tr><th>Time (UTC)</th><th>User</th><th>Role</th><th>Action</th><th>Result</th></tr></thead>
          <tbody>{d.entries.map((e, i) => <tr key={i}><td>{fmt.dateTime(e.t)}</td><td>{e.user ?? '—'}</td><td>{e.role ?? '—'}</td>
            <td><code>{e.method} {e.path}{e.query ? `?${e.query}` : ''}</code>{e.event ? <span className="note"> · {e.event}</span> : null}</td>
            <td><span className={`lvl ${e.status < 400 ? 'ok' : e.status === 401 || e.status === 403 ? 'warn' : 'bad'}`}>{e.status}</span></td></tr>)}</tbody>
        </table>
      </div>}
    </div>
  )
}

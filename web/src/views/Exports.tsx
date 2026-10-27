import { useState } from 'react'
import { download, STATIC } from '../api'

export type ExportItem = { label: string; url: string; file: string; hint?: string }

/** Download buttons (PDF, CSV, CAP, GeoJSON). Hidden in the static snapshot, which has no server to build files. */
export default function Exports({ items, title = 'Exportar' }: { items: ExportItem[]; title?: string }) {
  const [busy, setBusy] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)
  if (STATIC) return <div className="note">Exportar (PDF, CSV, aviso CAP para el 112, capas GeoJSON/OGC) funciona en la versión local.</div>
  return (
    <div className="exports">
      <div className="subh">{title}</div>
      <div className="ind-row">
        {items.map((it) => <button key={it.url} className="btn" title={it.hint} disabled={busy === it.url}
          onClick={() => { setBusy(it.url); setErr(null); download(it.url, it.file).catch((e) => setErr(String(e.message ?? e))).finally(() => setBusy(null)) }}>
          {busy === it.url ? 'Generando…' : it.label}</button>)}
      </div>
      {err && <div className="note warn-text">{err}</div>}
    </div>
  )
}

import { useState } from 'react'
import { download, STATIC } from '../api'

export type ExportItem = { label: string; url: string; file: string; hint?: string }

/** Download buttons (PDF, CSV, CAP, GeoJSON). Hidden in the static snapshot, which has no server to build files. */
export default function Exports({ items, title = 'Export' }: { items: ExportItem[]; title?: string }) {
  const [busy, setBusy] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)
  if (STATIC) return <div className="note">Export (PDF, CSV, CAP alert for 112, GeoJSON/OGC layers) works in the local version.</div>
  return (
    <div className="exports">
      <div className="subh">{title}</div>
      <div className="ind-row">
        {items.map((it) => <button key={it.url} className="btn" title={it.hint} disabled={busy === it.url}
          onClick={() => { setBusy(it.url); setErr(null); download(it.url, it.file).catch((e) => setErr(String(e.message ?? e))).finally(() => setBusy(null)) }}>
          {busy === it.url ? 'Generating…' : it.label}</button>)}
      </div>
      {err && <div className="note warn-text">{err}</div>}
    </div>
  )
}

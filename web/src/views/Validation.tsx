import { useEffect, useMemo, useState } from 'react'
import { api, fmt, type Sam3Validation, type ValidationData, type ValidationRow } from '../api'

const pc = (v: number | null | undefined) => (v == null ? '—' : `${Math.round(100 * v)} %`)

const W = 900, H = 320, M = { l: 52, r: 16, t: 16, b: 34 }

function Chart({ rows }: { rows: ValidationRow[] }) {
  const [hover, setHover] = useState<number | null>(null)
  const data = rows.filter((r) => r.obs_72 != null)
  const n = data.length
  const ymax = Math.max(50, ...data.map((r) => Math.max(r.pred_72.p10_p90[1], r.obs_72 ?? 0))) * 1.05
  const x = (i: number) => M.l + (i / Math.max(1, n - 1)) * (W - M.l - M.r)
  const y = (v: number) => H - M.b - (v / ymax) * (H - M.t - M.b)
  const ticks = useMemo(() => { const step = ymax > 600 ? 200 : ymax > 250 ? 100 : 50; const t = []; for (let v = 0; v <= ymax; v += step) t.push(v); return t }, [ymax])
  const band = data.map((r, i) => `${x(i)},${y(r.pred_72.p10_p90[1])}`).join(' ') + ' ' + [...data].reverse().map((r, k) => `${x(n - 1 - k)},${y(r.pred_72.p10_p90[0])}`).join(' ')
  const line = data.map((r, i) => `${i ? 'L' : 'M'}${x(i)},${y(r.pred_72.expected)}`).join(' ')
  const months = data.map((r, i) => ({ i, d: r.date })).filter((o) => o.d.endsWith('-01') || o.i === 0)
  const h = hover != null ? data[hover] : null
  return (
    <div className="chart-wrap">
      <div className="legend-row">
        <span><i className="sw band" />VolScan forecast (calibrated P10–P90)</span>
        <span><i className="sw line" />Central forecast</span>
        <span><i className="sw dot" />Observed by Copernicus</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="New buildings reached in the next 72 h: forecast vs observed"
        onMouseLeave={() => setHover(null)}
        onMouseMove={(e) => { const b = (e.currentTarget as SVGSVGElement).getBoundingClientRect(); const px = ((e.clientX - b.left) / b.width) * W; setHover(Math.max(0, Math.min(n - 1, Math.round(((px - M.l) / (W - M.l - M.r)) * (n - 1))))) }}>
        {ticks.map((t) => <g key={t}><line x1={M.l} x2={W - M.r} y1={y(t)} y2={y(t)} className="grid" /><text x={M.l - 8} y={y(t) + 4} textAnchor="end" className="axis">{t}</text></g>)}
        {months.map((m) => <text key={m.d} x={x(m.i)} y={H - 10} className="axis" textAnchor="start">{new Date(m.d + 'T12:00:00Z').toLocaleDateString('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' })}</text>)}
        <polygon points={band} className="band" />
        <path d={line} className="central" />
        {data.map((r, i) => <circle key={r.date} cx={x(i)} cy={y(r.obs_72 ?? 0)} r={hover === i ? 5.5 : 4} className="obs" />)}
        {h && <g>
          <line x1={x(hover!)} x2={x(hover!)} y1={M.t} y2={H - M.b} className="cross" />
        </g>}
        <text x={M.l} y={M.t - 4} className="axis">buildings</text>
      </svg>
      {h && <div className="tip" style={{ left: `${(x(hover!) / W) * 100}%` }}>
        <b>{fmt.date(h.date + 'T12:00:00Z')}</b> (end of day) → 72 h<br />
        Forecast: {Math.round(h.pred_72.expected)} ({Math.round(h.pred_72.p10_p90[0])}–{Math.round(h.pred_72.p10_p90[1])})<br />
        Observed: {h.obs_72} · already lost: {h.lost_buildings}
      </div>}
    </div>
  )
}

export default function Validation() {
  const [d, setD] = useState<ValidationData | null>(null)
  const [samVal, setSamVal] = useState<Sam3Validation | null>(null)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => {
    api.lpValidation().then(setD).catch((e) => setErr(String(e)))
    api.lpSam3Validation().then(setSamVal).catch(() => setSamVal(null))
  }, [])
  const s = d?.summary
  const first = d?.rows.find((r) => r.obs_72 != null)
  const sens = d?.delay_sensitivity
  return (
    <div className="page">
      <h2>How accurate is VolScan? La Palma 2021, day by day</h2>
      <p className="lead">Every day of the eruption, VolScan forecast how many new buildings the lava would reach in the next 72 h, using only what was known that day. Here it is compared with what Copernicus mapped afterwards.</p>
      {d && <p className="note">{d.method}</p>}
      {err && <div className="note">Could not load the validation: {err}</div>}
      {!d && !err && <div className="loading">Computing 83 forecasts and comparing them with reality (a couple of minutes the first time)…</div>}
      {s && <div className="kpis kpis-page">
        <div className="kpi"><div className="k">Days inside the range</div><div className="v">{s.within_p10_p90_72h}<small>/ {s.days}</small></div><div className="s">{Math.round(100 * s.within_p10_p90_72h / s.days)} % of days (a well-calibrated P10–P90 would give 80 %)</div></div>
        <div className="kpi"><div className="k">Total bias</div><div className="v">{s.bias_pct != null && s.bias_pct > 0 ? '+' : ''}{fmt.num(s.bias_pct)}<small> %</small></div><div className="s">{fmt.int(s.total_pred_72)} forecast vs {fmt.int(s.total_obs_72)} observed (72 h windows, overlapping)</div></div>
        <div className="kpi"><div className="k">Mean error</div><div className="v">{fmt.num(s.mae_72)}</div><div className="s">buildings per 72 h forecast</div></div>
        {s.watch && <div className="kpi"><div className="k">Watch list</div><div className="v">{pc(s.watch.with_pocket.recall)}</div><div className="s">of lost buildings were on the list 72 h earlier ({pc(s.watch.high.recall)} without hemmed-in ones)</div></div>}
      </div>}
      {d && <Chart rows={d.rows} />}
      {d && s && <div className="cards" style={{ marginTop: 16 }}>
        <div className="card"><h3>Where it works</h3><p className="note">{(() => {
          const ph = d.rows.filter((r) => r.obs_72 != null && r.date >= '2021-09-23' && r.date <= '2021-10-08')
          const inR = ph.filter((r) => r.pred_72.p10_p90[0] <= (r.obs_72 as number) && (r.obs_72 as number) <= r.pred_72.p10_p90[1]).length
          return `While the lava advanced towards the sea and Todoque (23 Sep – 8 Oct), the real value fell inside the range on ${inR} of ${ph.length} days. `
        })()}{first ? `The first two forecasts with a map overestimate (${fmt.date(first.date + 'T12:00:00Z')}: ${Math.round(first.pred_72.expected)} forecast vs ${first.obs_72}): the first growth rate is extrapolated with no history. ` : ''}Overall it is {fmt.num(Math.abs(s.bias_pct ?? 0))} % {(s.bias_pct ?? 0) < 0 ? 'low' : 'high'}.</p></div>
        <div className="card"><h3>Where it fails, and what we do</h3><p className="note">Sudden bursts of lateral growth fill the ground between flow arms in dense areas. We tried three ways to forecast that “where” and none improved the central count, so they are not mixed in; we do widen the top of the range with that infill, which recovers 12–13 October. 25–28 October (about 10 buildings per new hectare) is still outside. They do help the <b>watch list</b>: buildings hemmed in by the flow caught {s.watch ? pc((s.watch.with_pocket.recall ?? 0) - (s.watch.high.recall ?? 0)) : '—'} more of the losses, with {s.watch ? pc(s.watch.with_pocket.precision) : '—'} precision.</p></div>
        <div className="card"><h3>Map delivery delay</h3><p className="note">Copernicus delivers each map 7 h (rush mode) to 48 h (standard mode) after receiving the image. Here we assume {fmt.num(d.map_delay_h)} h. {sens ? `With 7 h: ${sens['7'].within_p10_p90_72h}/${sens['7'].days} days in range and ${fmt.num(sens['7'].bias_pct)} % bias. With 48 h: ${sens['48'].within_p10_p90_72h}/${sens['48'].days} and ${fmt.num(sens['48'].bias_pct)} %.` : ''}</p></div>
        <div className="card"><h3>Ground truth</h3><p className="note">{d.truth}. An institution can defend a decision made with a tool whose accuracy is measured; that is why this page exists.</p></div>
      </div>}

      {samVal && (
        <div style={{ marginTop: 28 }}>
          <h3>Segmentation experiment on synthetic scenes derived from CEMS ({samVal.n_scenes} EMSR546 scenes)</h3>
          <p className="note">{samVal.note}</p>
          <div className="kpis kpis-page" style={{ marginTop: 10 }}>
            <div className="kpi">
              <div className="k">Mean IoU (Jaccard)</div>
              <div className="v">{fmt.num(samVal.summary.mean_iou, 3)}</div>
              <div className="s">median {fmt.num(samVal.summary.median_iou, 3)} over {samVal.n_scenes} reference masks (circular test)</div>
            </div>
            <div className="kpi">
              <div className="k">Precision / Recall</div>
              <div className="v">{pc(samVal.summary.mean_precision)}<small> / {pc(samVal.summary.mean_recall)}</small></div>
              <div className="s">mean F1 {fmt.num(samVal.summary.mean_f1, 3)} against the reference used to build the input</div>
            </div>
            <div className="kpi">
              <div className="k">Lead-time gain</div>
              <div className="v">Not shown</div>
              <div className="s">No independent observed scenes and no measured operational latency</div>
            </div>
            <div className="kpi">
              <div className="k">Latency per scene</div>
              <div className="v">{fmt.num(samVal.summary.mean_latency_ms, 1)}<small> ms</small></div>
              <div className="s">{samVal.adapter.adapter} ({samVal.adapter.model})</div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

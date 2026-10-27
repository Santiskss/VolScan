import { useEffect, useMemo, useState } from 'react'
import { api, fmt, type ValidationRow } from '../api'

type Sum = { days: number; within_p10_p90_72h: number; total_pred_72: number; total_obs_72: number; first_10_days: { days: number; within: number } }

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
        <span><i className="sw band" />Pronóstico VolScan (bajo–alto)</span>
        <span><i className="sw line" />Pronóstico central</span>
        <span><i className="sw dot" />Observado por Copernicus</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Edificios nuevos alcanzados en las 72 h siguientes: pronóstico frente a observado"
        onMouseLeave={() => setHover(null)}
        onMouseMove={(e) => { const b = (e.currentTarget as SVGSVGElement).getBoundingClientRect(); const px = ((e.clientX - b.left) / b.width) * W; setHover(Math.max(0, Math.min(n - 1, Math.round(((px - M.l) / (W - M.l - M.r)) * (n - 1))))) }}>
        {ticks.map((t) => <g key={t}><line x1={M.l} x2={W - M.r} y1={y(t)} y2={y(t)} className="grid" /><text x={M.l - 8} y={y(t) + 4} textAnchor="end" className="axis">{t}</text></g>)}
        {months.map((m) => <text key={m.d} x={x(m.i)} y={H - 10} className="axis" textAnchor="start">{new Date(m.d + 'T12:00:00Z').toLocaleDateString('es-ES', { day: 'numeric', month: 'short', timeZone: 'UTC' })}</text>)}
        <polygon points={band} className="band" />
        <path d={line} className="central" />
        {data.map((r, i) => <circle key={r.date} cx={x(i)} cy={y(r.obs_72 ?? 0)} r={hover === i ? 5.5 : 4} className="obs" />)}
        {h && <g>
          <line x1={x(hover!)} x2={x(hover!)} y1={M.t} y2={H - M.b} className="cross" />
        </g>}
        <text x={M.l} y={M.t - 4} className="axis">edificios</text>
      </svg>
      {h && <div className="tip" style={{ left: `${(x(hover!) / W) * 100}%` }}>
        <b>{fmt.date(h.date + 'T12:00:00Z')}</b> (fin del día) → 72 h<br />
        Pronóstico: {Math.round(h.pred_72.expected)} ({Math.round(h.pred_72.p10_p90[0])}–{Math.round(h.pred_72.p10_p90[1])})<br />
        Observado: {h.obs_72} · ya perdidos: {h.lost_buildings}
      </div>}
    </div>
  )
}

export default function Validation() {
  const [d, setD] = useState<{ rows: ValidationRow[]; summary: Sum; truth: string } | null>(null)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => { api.lpValidation().then(setD).catch((e) => setErr(String(e))) }, [])
  const s = d?.summary
  return (
    <div className="page">
      <h2>¿Cuánto acierta VolScan? La Palma 2021, día a día</h2>
      <p className="lead">Cada día de la erupción, VolScan pronosticó cuántos edificios nuevos alcanzaría la lava en las 72 h siguientes, solo con lo que se sabía ese día. Aquí se compara con lo que Copernicus cartografió después. El dónde lo da el conjunto de coladas; el cuánto, el ritmo de crecimiento de la colada observado en los días previos.</p>
      {err && <div className="note">No se pudo cargar la validación: {err}</div>}
      {!d && !err && <div className="loading">Calculando 80 pronósticos y comparándolos con la realidad (30 s la primera vez)…</div>}
      {s && <div className="kpis kpis-page">
        <div className="kpi"><div className="k">Días dentro del rango</div><div className="v">{s.within_p10_p90_72h}<small>/ {s.days}</small></div><div className="s">{Math.round(100 * s.within_p10_p90_72h / s.days)} % de los días, el valor real cayó dentro del rango bajo–alto</div></div>
        <div className="kpi"><div className="k">Primeros 10 días</div><div className="v">{s.first_10_days.within}<small>/ {s.first_10_days.days}</small></div><div className="s">la semana crítica para evacuar</div></div>
        <div className="kpi"><div className="k">Edificios · pronóstico total</div><div className="v">{fmt.int(s.total_pred_72)}</div><div className="s">suma de ventanas de 72 h (se solapan)</div></div>
        <div className="kpi"><div className="k">Edificios · observado total</div><div className="v">{fmt.int(s.total_obs_72)}</div><div className="s">VolScan se queda corto un {Math.round(100 * (1 - s.total_pred_72 / s.total_obs_72))} %</div></div>
      </div>}
      {d && <Chart rows={d.rows} />}
      {d && <div className="cards" style={{ marginTop: 16 }}>
        <div className="card"><h3>Dónde acierta</h3><p className="note">En la primera semana, cuando más importa: el 20 de septiembre previó 282 edificios para las 72 h siguientes (rango 54–528), y fueron 277. La dirección de la colada y los núcleos alcanzados (Todoque, Los Campitos, Triana) salen bien desde el primer día.</p></div>
        <div className="card"><h3>Dónde falla</h3><p className="note">Las aperturas de bocas nuevas y los desbordamientos laterales bruscos, como los del 11–12 y el 26 de octubre, quedan por encima del rango. El modelo no anticipa saltos de caudal. Mejora prevista: bocas nuevas como miembros del conjunto y caudal estimado con imagen térmica.</p></div>
        <div className="card"><h3>Verdad de terreno</h3><p className="note">{d.truth}. Una institución puede defender una decisión con una herramienta cuyo acierto está medido; por eso esta página existe.</p></div>
      </div>}
    </div>
  )
}

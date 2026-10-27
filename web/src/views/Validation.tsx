import { useEffect, useMemo, useState } from 'react'
import { api, fmt, type ValidationData, type ValidationRow } from '../api'

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
        <span><i className="sw band" />Pronóstico VolScan (P10–P90 calibrado)</span>
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
  const [d, setD] = useState<ValidationData | null>(null)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => { api.lpValidation().then(setD).catch((e) => setErr(String(e))) }, [])
  const s = d?.summary
  const first = d?.rows.find((r) => r.obs_72 != null)
  const sens = d?.delay_sensitivity
  return (
    <div className="page">
      <h2>¿Cuánto acierta VolScan? La Palma 2021, día a día</h2>
      <p className="lead">Cada día de la erupción, VolScan pronosticó cuántos edificios nuevos alcanzaría la lava en las 72 h siguientes, solo con lo que se sabía ese día. Aquí se compara con lo que Copernicus cartografió después.</p>
      {d && <p className="note">{d.method}</p>}
      {err && <div className="note">No se pudo cargar la validación: {err}</div>}
      {!d && !err && <div className="loading">Calculando 83 pronósticos y comparándolos con la realidad (un par de minutos la primera vez)…</div>}
      {s && <div className="kpis kpis-page">
        <div className="kpi"><div className="k">Días dentro del rango</div><div className="v">{s.within_p10_p90_72h}<small>/ {s.days}</small></div><div className="s">{Math.round(100 * s.within_p10_p90_72h / s.days)} % de los días (un P10–P90 bien calibrado daría 80 %)</div></div>
        <div className="kpi"><div className="k">Sesgo total</div><div className="v">{s.bias_pct != null && s.bias_pct > 0 ? '+' : ''}{fmt.num(s.bias_pct)}<small> %</small></div><div className="s">{fmt.int(s.total_pred_72)} pronosticados frente a {fmt.int(s.total_obs_72)} observados (ventanas de 72 h, se solapan)</div></div>
        <div className="kpi"><div className="k">Error medio</div><div className="v">{fmt.num(s.mae_72)}</div><div className="s">edificios por pronóstico de 72 h</div></div>
        {s.watch && <div className="kpi"><div className="k">Lista de vigilancia</div><div className="v">{pc(s.watch.with_pocket.recall)}</div><div className="s">de los edificios perdidos estaban en la lista 72 h antes ({pc(s.watch.high.recall)} sin los cercados)</div></div>}
      </div>}
      {d && <Chart rows={d.rows} />}
      {d && s && <div className="cards" style={{ marginTop: 16 }}>
        <div className="card"><h3>Dónde acierta</h3><p className="note">{(() => {
          const ph = d.rows.filter((r) => r.obs_72 != null && r.date >= '2021-09-23' && r.date <= '2021-10-08')
          const inR = ph.filter((r) => r.pred_72.p10_p90[0] <= (r.obs_72 as number) && (r.obs_72 as number) <= r.pred_72.p10_p90[1]).length
          return `En la fase de avance hacia el mar y Todoque (23 sep – 8 oct), el valor real cayó en el rango ${inR} de ${ph.length} días. `
        })()}{first ? `Los dos primeros pronósticos con mapa sobreestiman (${fmt.date(first.date + 'T12:00:00Z')}: ${Math.round(first.pred_72.expected)} previstos frente a ${first.obs_72}): el primer ritmo de crecimiento se extrapola sin historial. ` : ''}En conjunto se queda un {fmt.num(Math.abs(s.bias_pct ?? 0))} % {(s.bias_pct ?? 0) < 0 ? 'corto' : 'largo'}.</p></div>
        <div className="card"><h3>Dónde falla, y qué hacemos</h3><p className="note">Los saltos bruscos de crecimiento lateral rellenan el terreno entre brazos de la colada, en zona densa. Probamos tres formas de pronosticar ese «dónde» y ninguna mejoró el recuento central, así que no se mezclan; sí ampliamos el extremo alto del rango con ese relleno, lo que recupera el 12–13 de octubre. El 25–28 de octubre (unos 10 edificios por hectárea nueva) sigue fuera. Sí sirven para la <b>lista de vigilancia</b>: los edificios cercados por la colada recogieron {s.watch ? pc((s.watch.with_pocket.recall ?? 0) - (s.watch.high.recall ?? 0)) : '—'} más de lo perdido, con una precisión del {s.watch ? pc(s.watch.with_pocket.precision) : '—'}.</p></div>
        <div className="card"><h3>Retraso de los mapas</h3><p className="note">Copernicus entrega cada mapa entre 7 h (modo rápido) y 48 h (modo estándar) después de recibir la imagen. Aquí se supone {fmt.num(d.map_delay_h)} h. {sens ? `Con 7 h: ${sens['7'].within_p10_p90_72h}/${sens['7'].days} días en rango y sesgo ${fmt.num(sens['7'].bias_pct)} %. Con 48 h: ${sens['48'].within_p10_p90_72h}/${sens['48'].days} y ${fmt.num(sens['48'].bias_pct)} %.` : ''}</p></div>
        <div className="card"><h3>Verdad de terreno</h3><p className="note">{d.truth}. Una institución puede defender una decisión con una herramienta cuyo acierto está medido; por eso esta página existe.</p></div>
      </div>}
    </div>
  )
}

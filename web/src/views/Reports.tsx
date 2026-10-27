import { useEffect, useState } from 'react'
import { api, fmt, STATIC, type Report } from '../api'
import Solunar from './Solunar'
import { GnssTable, LevelChip } from './Indicators'

const ZONE_ORDER = ['tenerife', 'la_palma', 'el_hierro', 'gran_canaria', 'lanzarote_fuerteventura', 'la_gomera', 'enmedio']

function Bars({ values, label, unit, fmtv = (v: number) => String(v) }: { values: (number | null)[]; label: string; unit: string; fmtv?: (v: number) => string }) {
  const [h, setH] = useState<number | null>(null)
  const W = 620, Hh = 140, l = 36, b = 20, t = 8
  const vals = values.map((v) => v ?? 0)
  const max = Math.max(1, ...vals)
  const bw = (W - l - 4) / values.length
  const y = (v: number) => Hh - b - (v / max) * (Hh - b - t)
  return (
    <div className="mini-chart">
      <div className="subh">{label}</div>
      <svg viewBox={`0 0 ${W} ${Hh}`} onMouseLeave={() => setH(null)} role="img" aria-label={label}>
        {[0, max / 2, max].map((v) => <g key={v}><line x1={l} x2={W} y1={y(v)} y2={y(v)} className="grid" /><text x={l - 6} y={y(v) + 4} textAnchor="end" className="axis">{fmtv(v)}</text></g>)}
        {values.map((v, i) => v == null ? null : <rect key={i} x={l + i * bw + 1} y={y(v)} width={Math.max(1, bw - 2)} height={Math.max(0, Hh - b - y(v))} rx={2} className={h === i ? 'bar on' : 'bar'} onMouseEnter={() => setH(i)} />)}
        {[0, 9, 19, 29].filter((i) => i < values.length).map((i) => <text key={i} x={l + i * bw} y={Hh - 5} className="axis">{i + 1}</text>)}
      </svg>
      {h != null && <div className="note">Día {h + 1}: {values[h] == null ? 'sin dato' : `${fmtv(values[h] as number)} ${unit}`}</div>}
    </div>
  )
}

export default function Reports() {
  const [months, setMonths] = useState<string[]>([])
  const [zones, setZones] = useState<{ key: string; name: string }[]>([])
  const [zone, setZone] = useState('tenerife')
  const [month, setMonth] = useState('')
  const [rep, setRep] = useState<Report | null>(null)
  const [ai, setAi] = useState<{ text: string | null; error?: string; model?: string } | null>(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    api.reportMonths().then((m) => {
      setMonths(m.months); setZones([...m.zones].sort((a, b) => ZONE_ORDER.indexOf(a.key) - ZONE_ORDER.indexOf(b.key)))
      setMonth(m.months[0])
    })
  }, [])
  useEffect(() => { if (month) { setRep(null); setAi(null); api.report(zone, month).then(setRep).catch(() => setRep(null)) } }, [zone, month])
  const s = rep?.stats
  const delta = (a: number | null | undefined, b: number | null | undefined) => a == null || b == null ? '' : a > b ? '▲' : a < b ? '▼' : '='
  return (
    <div className="page report">
      <div className="report-bar">
        <select id="rep-zone" value={zone} onChange={(e) => setZone(e.target.value)}>{zones.map((z) => <option key={z.key} value={z.key}>{z.name}</option>)}</select>
        <select id="rep-month" value={month} onChange={(e) => setMonth(e.target.value)}>{months.map((m) => <option key={m} value={m}>{new Date(m + '-15T12:00:00Z').toLocaleDateString('es-ES', { month: 'long', year: 'numeric', timeZone: 'UTC' })}</option>)}</select>
        <span style={{ flex: 1 }} />
        {!STATIC && <button className="btn" onClick={() => window.print()}>Imprimir o guardar PDF</button>}
      </div>
      {!rep && <div className="loading">Preparando informe…</div>}
      {rep && s && <>
        <div className="report-head">
          <div className="kicker">Informe mensual de vigilancia volcánica · VolScan</div>
          <h2>{rep.title}{rep.partial ? ' (mes en curso)' : ''}</h2>
          <div className="note">Datos: catálogo del IGN · generado el {fmt.dateTime(rep.generated_at)} · zona: {rep.zone.note || rep.zone.name}</div>
        </div>
        <div className="card summary-card">
          <p>{ai?.text ?? rep.summary}</p>
          <div className="brief-meta">
            <span>{ai?.text ? `Redactado con IA (${ai.model}) a partir de las cifras del informe` : 'Resumen automático a partir de las cifras'}</span>
            {!ai?.text && <button className="btn" disabled={busy} onClick={() => { setBusy(true); api.reportRewrite(zone, month).then((r) => setAi({ text: r.text, error: r.error, model: r.model.model })).finally(() => setBusy(false)) }}>{busy ? 'Redactando…' : 'Redactar con IA'}</button>}
          </div>
          {ai?.error && <div className="note">{ai.error}</div>}
        </div>
        <div className="kpis kpis-page">
          <div className="kpi"><div className="k">Terremotos</div><div className="v">{fmt.int(s.n)}</div><div className="s">{delta(s.n, rep.prev.n)} mes anterior {fmt.int(rep.prev.n)} · ×{fmt.num(rep.rate_ratio)} la tasa anual</div></div>
          <div className="kpi"><div className="k">Magnitud máxima</div><div className="v">{fmt.num(s.max_mag)}</div><div className="s">{s.n_m3} de M≥3 · {s.n_m2} de M≥2 · {rep.felt} sentidos</div></div>
          <div className="kpi"><div className="k">Profundidad mediana</div><div className="v">{fmt.num(s.depth_median)}<small>km</small></div><div className="s">{delta(rep.prev.depth_median, s.depth_median)} anterior {fmt.num(rep.prev.depth_median)} km · {s.shallow_lt5} a menos de 5 km</div></div>
          <div className="kpi"><div className="k">Índice de actividad (fin)</div><div className="v">{rep.unrest_end.index == null ? '—' : fmt.num(rep.unrest_end.index)}<small>/ 10</small></div><div className="s">{rep.b ? `b-value ${fmt.num(rep.b.b, 2)} ± ${fmt.num(rep.b.sigma, 2)}` : 'b-value: pocos datos'}</div></div>
        </div>
        <div className="report-charts">
          <Bars values={rep.daily} label="Terremotos por día" unit="terremotos" fmtv={(v) => String(Math.round(v))} />
          <Bars values={rep.daily_depth} label="Profundidad mediana por día (km)" unit="km" fmtv={(v) => v.toFixed(0)} />
        </div>
        <div className="cards">
          <div className="card">
            <h3>Terremotos más destacados</h3>
            <table className="places">
              <thead><tr><th>Fecha UTC</th><th>M</th><th>Prof.</th><th>Int.</th></tr></thead>
              <tbody>{rep.top_events.map((e) => <tr key={e.id} title={e.place}><td>{fmt.dateTime(e.t)}<div className="note">{e.place}</div></td><td>{fmt.num(e.mag)}</td><td>{e.depth == null ? '—' : `${fmt.num(e.depth)} km`}</td><td>{e.int_max ?? '—'}</td></tr>)}</tbody>
            </table>
          </div>
          <div className="card">
            <h3>Comparación</h3>
            <table className="places">
              <thead><tr><th>Indicador</th><th>Este mes</th><th>Anterior</th></tr></thead>
              <tbody>
                <tr><td>Terremotos</td><td>{fmt.int(s.n)}</td><td>{fmt.int(rep.prev.n)}</td></tr>
                <tr><td>Magnitud máxima</td><td>{fmt.num(s.max_mag)}</td><td>{fmt.num(rep.prev.max_mag)}</td></tr>
                <tr><td>M ≥ 3</td><td>{s.n_m3}</td><td>{rep.prev.n_m3}</td></tr>
                <tr><td>Prof. mediana (km)</td><td>{fmt.num(s.depth_median)}</td><td>{fmt.num(rep.prev.depth_median)}</td></tr>
                <tr><td>Sismos a &lt; 5 km</td><td>{s.shallow_lt5}</td><td>{rep.prev.shallow_lt5}</td></tr>
                <tr><td>Media diaria (12 meses previos)</td><td colSpan={2}>{fmt.num(rep.baseline.rate_day, 2)} terremotos/día</td></tr>
              </tbody>
            </table>
            <h3 style={{ marginTop: 14 }}>Mareas y Luna este mes</h3>
            {rep.tides ? <div className="stat">
              <span className="k">Marea semidiurna (exceso en máximo)</span><span className={`sig ${rep.tides.semidiurnal.p_shift < 0.05 ? 'yes' : 'no'}`}>p = {rep.tides.semidiurnal.p_shift.toFixed(2).replace('.', ',')}</span>
              <span className="k">Mareas vivas (exceso en sizigia)</span><span className={`sig ${rep.tides.fortnightly.p_shift < 0.05 ? 'yes' : 'no'}`}>p = {rep.tides.fortnightly.p_shift.toFixed(2).replace('.', ',')}</span>
            </div> : <div className="note">Menos de 30 terremotos: no se calcula.</div>}
            <p className="note">Prueba robusta con el catálogo desagrupado y 100 desplazamientos temporales. El historial completo está más abajo.</p>
          </div>
        </div>
        <div className="cards" style={{ marginTop: 12 }}>
          <div className="card">
            <h3>Deformación (GNSS) {rep.deformation && <LevelChip level={rep.deformation.level} />}</h3>
            {rep.deformation ? <GnssTable stations={rep.deformation.stations} /> : <div className="note">Sin estaciones GNSS públicas con datos para este mes.</div>}
            <p className="note">Desviación de los últimos 30 días respecto a la tendencia de los 3 años anteriores. Estaciones procesadas por el Nevada Geodetic Laboratory.</p>
          </div>
          <div className="card">
            <h3>Gases (SO2 por satélite) {rep.so2 && <LevelChip level={rep.so2.days_detected ? 'SO2 detectado' : 'sin SO2 visible'} />}</h3>
            {rep.so2 ? <div className="kv">
              <span className="k">Días con dato</span><span>{rep.so2.days}</span>
              <span className="k">Días con SO2 ≥ {fmt.num(rep.so2.threshold_kt, 0)} kt</span><span>{rep.so2.days_detected}</span>
              <span className="k">Máximo diario</span><span>{fmt.num(rep.so2.max_kt, 2)} kt</span>
            </div> : <div className="note">Sin datos de SO2 para este mes (la serie diaria cubre 2021 y los dos últimos años).</div>}
            <p className="note">NASA OMPS, troposfera baja, sobre el archipiélago. Detecta erupciones y desgasificación fuerte, no la difusa.</p>
          </div>
        </div>
        <p className="note" style={{ marginTop: 10 }}>Fuentes: {rep.sources.join(' · ')}. VolScan no emite niveles de alerta; la valoración oficial corresponde al PEVOLCA.</p>
        <details className="research">
          <summary>Investigación · mareas, Luna y sismicidad desde 2011</summary>
          <Solunar />
        </details>
      </>}
    </div>
  )
}

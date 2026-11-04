import { useEffect, useMemo, useState } from 'react'
import { api, fmt, STATIC, type Status, type Calibration, type Indicators, type Quake, type Terrain, type Zone } from '../api'
import { GnssTable, LevelChip, So2Bars, type So2Status } from './Indicators'
import Atlas3D, { type Label, type QuakePoint } from '../three/Atlas3D'

// UTM 28N approximation of zone centroids via the quakes we already have, falling back to fixed points
const ZONE_XY: Record<string, [number, number]> = {
  el_hierro: [205000, 3070000], la_palma: [221000, 3170000], la_gomera: [282000, 3115000], tenerife: [345000, 3130000],
  enmedio: [405000, 3105000], gran_canaria: [440000, 3090000], lanzarote_fuerteventura: [600000, 3165000],
}

function Spark({ data }: { data: number[] }) {
  const max = Math.max(1, ...data)
  const w = 120, h = 26
  const pts = data.map((v, i) => `${(i / Math.max(1, data.length - 1)) * w},${h - (v / max) * h}`).join(' ')
  return <svg width={w} height={h} style={{ display: 'block' }}><polyline points={pts} fill="none" stroke="var(--accent)" strokeWidth="1.4" /></svg>
}

export default function CanariasLive() {
  const [terrain, setTerrain] = useState<Terrain | null>(null)
  const [zones, setZones] = useState<Zone[]>([])
  const [quakes, setQuakes] = useState<Quake[]>([])
  const [active, setActive] = useState<string | null>(null)
  const [days, setDays] = useState(30)
  const [refreshing, setRefreshing] = useState(false)
  const [focus, setFocus] = useState<{ x: number; y: number; distKm: number } | null>(null)
  const [at, setAt] = useState<string>('')
  const [so2, setSo2] = useState<So2Status | null>(null)
  const [cat, setCat] = useState<Status['catalog'] | null>(null)
  const [ind, setInd] = useState<Indicators | null>(null)
  const [cal, setCal] = useState<Calibration | null>(null)
  const indZone = active ?? 'tenerife'
  useEffect(() => { setInd(null); api.indicators(indZone).then(setInd).catch(() => setInd(null)) }, [indZone])
  useEffect(() => { api.calibration().then(setCal).catch(() => setCal(null)) }, [])

  const load = () => {
    api.zones().then((z) => { setZones(z.zones); setAt(z.at); setSo2(z.so2) })
    api.status().then((st) => setCat(st.catalog)).catch(() => setCat(null))
    api.quakes(days).then((q) => setQuakes(q.quakes))
  }
  useEffect(() => { api.terrain('archipelago').then(setTerrain) }, [])
  useEffect(load, [days])

  const now = Date.now()
  const pts: QuakePoint[] = useMemo(() => quakes.filter((q) => q.depth != null && (!active || q.zone === active))
    .map((q) => ({ x: q.x, y: q.y, depth: q.depth as number, mag: (q.mag ?? 0.5) * 1.6, ageH: (now - Date.parse(q.t)) / 3600000 })), [quakes, active])
  const labels: Label[] = useMemo(() => zones.filter((z) => z.key !== 'enmedio').map((z) => ({ x: ZONE_XY[z.key][0], y: ZONE_XY[z.key][1] + 9000, text: z.name.replace(' y Fuerteventura', ' · Fuerteventura').replace(' and Fuerteventura', ' · Fuerteventura'), kind: 'zonelabel' as const })), [zones])
  const total7 = zones.reduce((a, z) => a + z.n7, 0)
  const maxMag = Math.max(...quakes.map((q) => q.mag ?? -9), -9)

  return (
    <div className="view">
      <div className="stage" style={{ gridTemplateRows: '1fr auto' }}>
        <div className="canvas-wrap">
          <Atlas3D terrain={terrain} quakes={pts} labels={labels} exaggeration={4} depthScale={1.2} terrainOpacity={0.9} maxDepthKm={40} focus={focus} quakeScale={6} />
          <div className="corner tl">Archipelago · 500 m terrain ×4 · IGN earthquakes at their depth (×1.2)</div>
          <div className="obs-card"><div className="k">{STATIC ? 'Snapshot' : 'Live'}</div><div className="v"><span className={`dot ${STATIC || cat?.health?.ok !== false ? 'ok' : 'warn'}`} />IGN catalogue · {at ? fmt.dateTime(at) : '—'}</div>
            {!STATIC && cat?.health && !cat.health.ok && <div className="note" style={{ maxWidth: 280, marginTop: 4 }}>{cat.health.message}</div>}
            {cat?.last && <div className="note">last earthquake: {fmt.dateTime(cat.last)}</div>}</div>
          <div className="legend-strip"><div className="item"><b style={{ color: '#e23d14' }}>●</b> 24 h <b style={{ color: '#f08a35' }}>●</b> 7 days <b style={{ color: '#8f8577' }}>●</b> {days} days · size = magnitude</div></div>
          <div className="controls-row">
            {[7, 30, 90, 365].map((d) => <button key={d} className={`btn ${d === days ? 'primary' : ''}`} onClick={() => setDays(d)}>{d === 365 ? '1 year' : `${d} d`}</button>)}
            <button className="btn" onClick={() => { setActive(null); setFocus({ x: 420000, y: 3150000, distKm: 260 }) }}>Archipelago</button>
          </div>
        </div>
        <div className="kpis">
          <div className="kpi"><div className="k">Earthquakes 7 days · Canaries</div><div className="v">{fmt.int(total7)}</div><div className="s">in the volcanic zones analysed</div></div>
          <div className="kpi"><div className="k">Maximum magnitude</div><div className="v">{maxMag > -9 ? fmt.num(maxMag) : '—'}</div><div className="s">in the period shown</div></div>
          <div className="kpi"><div className="k">Satellite SO2 · 7 days</div><div className="v" style={{ fontSize: 20 }}>{so2 ? <LevelChip level={so2.level} /> : '—'}</div><div className="s">max {so2?.max_kt == null ? '—' : `${fmt.num(so2.max_kt, 2)} kt`} · NASA OMPS</div></div>
          <div className="kpi"><div className="k">Most active zone</div><div className="v" style={{ fontSize: 20 }}>{zones[0]?.index ? zones[0].name : 'None anomalous'}</div><div className="s">{zones[0]?.index ? `index ${fmt.num(zones[0].index)} / 10` : `index 0 in every zone · ${fmt.int(pts.length)} earthquakes on screen`}</div></div>
        </div>
      </div>
      <aside className="side">
        <section>
          <h3>Volcanic zones · unrest index</h3>
          <div className="zone-list">
            {zones.map((z) => (
              <button key={z.key} className={`zone ${active === z.key ? 'active' : ''}`} onClick={() => { setActive(active === z.key ? null : z.key); setFocus({ x: ZONE_XY[z.key][0], y: ZONE_XY[z.key][1], distKm: 70 }) }}>
                <div className="row"><span className="name">{z.name}</span><span className="idx">{z.index == null ? '—' : fmt.num(z.index)}</span></div>
                <div className="idxbar"><i style={{ width: `${(z.index ?? 0) * 10}%` }} /></div>
                <div className="row" style={{ marginTop: 6 }}>
                  <Spark data={z.daily30} />
                  <span className="meta">{z.n7} quakes/7 d · {z.n30}/30 d</span>
                </div>
                <div className="meta">Mmax 30 d {fmt.num(z.max_mag30)} · median depth {fmt.num(z.depth_median30)} km{z.b ? ` · b ${fmt.num(z.b.b, 2)}` : ''}{z.mc != null ? ` · Mc ${fmt.num(z.mc)}` : ''}</div>
                <div className="ind-row"><span className="lab">Deformation</span><LevelChip level={z.deformation.level} />{z.deformation.evaluated_at && <span className="lab">GNSS to {z.deformation.evaluated_at}</span>}</div>
              </button>
            ))}
          </div>
          <p className="note">The index (0–10) compares the last 7 days with each zone’s previous year, counting only earthquakes above the magnitude of completeness (Mc): how unlikely the rate is, energy against the year’s worst week, and shallowing. <b>It is not an eruption probability</b>. The official traffic light is run by PEVOLCA.</p>
          {zones.find((z) => z.key === (active ?? zones[0]?.key))?.history && <p className="note">{zones.find((z) => z.key === (active ?? zones[0]?.key))?.history}</p>}
          {!STATIC && <button className="btn olive" disabled={refreshing} onClick={() => { setRefreshing(true); api.refresh().finally(() => { setRefreshing(false); load() }) }}>{refreshing ? 'Updating from IGN…' : 'Update from IGN'}</button>}
        </section>
        <section>
          <h3>Deformation and gas · {zones.find((z) => z.key === indZone)?.name ?? indZone}</h3>
          {!ind && <div className="loading">Loading GNSS and SO2…</div>}
          {ind && <>
            <div className="subh">GNSS deformation · deviation from the 3-year trend</div>
            <GnssTable stations={ind.deformation.stations} />
            <p className="note">{ind.notes.deformation} Level: |z| &lt; 3 normal · 3–6 watch · &gt; 6 anomalous.</p>
            <div className="subh">Satellite SO2 · archipelago · 120 days</div>
            <So2Bars series={ind.so2_series.map((r) => ({ date: r.date, kt: r.so2_kt }))} threshold={ind.so2.threshold_kt ?? 1} />
            <p className="note">{ind.notes.so2}</p>
          </>}
        </section>
        {cal && <section>
          <h3>Index track record · {cal.start.slice(0, 4)}–{cal.end.slice(0, 4)}</h3>
          <table className="places cal-table">
            <thead><tr><th>Index ≥</th><th>Episodes</th><th>Before an eruption</th><th>Lead time</th></tr></thead>
            <tbody>{cal.table.map((r) => <tr key={r.threshold}><td>{r.threshold}</td><td>{r.episodes}</td><td>{r.preceded_eruption} / {r.eruptions}</td>
              <td>{Object.entries(r.lead_days).map(([z, d]) => `${z === 'el_hierro' ? 'EH' : 'LP'} ${d} d`).join(' · ') || '—'}</td></tr>)}</tbody>
          </table>
          <p className="note">Episodes across the archipelago (index every 2 days). Eruptions in the period: {Object.values(cal.eruptions).map((e) => `${e.name} (${e.date})`).join(' and ')}. The other episodes were real unrest without an eruption, like the deep swarms under La Palma in 2017–2020. Two eruptions are not enough to give a probability.</p>
        </section>}
        <section>
          <h3>Latest earthquakes</h3>
          <table className="places">
            <thead><tr><th>Date UTC</th><th>M</th><th>Depth</th></tr></thead>
            <tbody>
              {[...quakes].filter((q) => !active || q.zone === active).reverse().slice(0, 14).map((q) => (
                <tr key={q.id} title={q.place}><td>{fmt.dateTime(q.t)}<div className="note">{q.place}</div></td><td>{fmt.num(q.mag)}</td><td>{q.depth == null ? '—' : `${fmt.num(q.depth)} km`}</td></tr>
              ))}
            </tbody>
          </table>
          <p className="note">Source: Instituto Geográfico Nacional (IGN), earthquake catalogue. doi:10.7419/162.03.2022</p>
        </section>
      </aside>
    </div>
  )
}

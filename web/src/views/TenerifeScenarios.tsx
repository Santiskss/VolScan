import { useEffect, useMemo, useState } from 'react'
import { api, fmt, type Terrain, type TfScenario } from '../api'
import Atlas3D, { preloadImage, type Label, type SurfacePoint } from '../three/Atlas3D'
import Exports from './Exports'

const r0 = (v: number | null | undefined) => (v == null ? '—' : Math.round(v).toLocaleString('en-GB'))
const TOWNS: [string, number, number][] = [
  ['Garachico', 327243, 3139786], ['Icod de los Vinos', 331546, 3139059], ['Santiago del Teide', 322116, 3131328],
  ['La Orotava', 350788, 3141349], ['Puerto de la Cruz', 348274, 3144041], ['Güímar', 361666, 3133016],
  ['Arafo', 361010, 3135573], ['Vilaflor', 339366, 3115677], ['Guía de Isora', 325410, 3121858], ['Adeje', 330472, 3111921],
  ['Teide', 338921, 3128505],
]

export default function TenerifeScenarios() {
  const [terrain, setTerrain] = useState<Terrain | null>(null)
  const [list, setList] = useState<{ key: string; name: string; history: string }[]>([])
  const [note, setNote] = useState('')
  const [key, setKey] = useState('dorsal_noroeste')
  const [sc, setSc] = useState<TfScenario | null>(null)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [showAssets, setShowAssets] = useState(true)
  const [focus, setFocus] = useState<{ x: number; y: number; distKm: number } | null>(null)

  useEffect(() => {
    api.terrain('tenerife').then((t) => { preloadImage(t.texture); setTerrain(t) })
    api.tfScenarios().then((d) => {
      setList(d.scenarios)
      setNote(d.note)
      d.scenarios.forEach((s) => {
        if (s.key !== key) api.tfScenario(s.key).then((v) => preloadImage(v.overlay?.png)).catch(() => {})
      })
    })
  }, [])
  useEffect(() => {
    let alive = true
    setLoading(true); setErr(null)
    api.tfScenario(key).then((d) => {
      preloadImage(d.overlay?.png)
      if (alive) { setSc(d); const v = d.vents?.[0]?.xy; if (v) setFocus({ x: v[0], y: v[1] + 4000, distKm: 30 }) }
    })
      .catch((e) => alive && setErr(String(e))).finally(() => alive && setLoading(false))
    return () => { alive = false }
  }, [key])

  const labels: Label[] = useMemo(() => {
    const ls: Label[] = TOWNS.map(([text, x, y]) => ({ x, y, text }))
    if (sc?.vents && sc.key !== 'sismicidad_actual') sc.vents.forEach((v, i) => ls.push({ x: v.xy[0], y: v.xy[1], text: sc.vent_names?.[i] ?? 'Vent', kind: 'vent' }))
    return ls
  }, [sc])
  const assets: SurfacePoint[] = useMemo(() => (!showAssets || !sc?.buildings_at_risk_xy) ? [] : sc.buildings_at_risk_xy.map(([x, y, v]) => ({ x, y, v })), [sc, showAssets])
  const cur = list.find((s) => s.key === key)

  return (
    <div className="view">
      <div className="stage" style={{ gridTemplateRows: '1fr auto' }}>
        <div className="canvas-wrap">
          <Atlas3D terrain={terrain} overlay={sc?.overlay ?? null} labels={labels} surfacePoints={assets} focus={focus} exaggeration={1.6} terrainOpacity={0.95} />
          <div className="corner tl">Tenerife · 100 m terrain · planning scenario, not a forecast</div>
          <div className="obs-card"><div className="k">Scenario</div><div className="v"><span className="dot warn" />{cur?.name ?? '—'}</div></div>
          <div className="legend-strip">
            <div className="item">Probability that lava reaches each point within 30 days<span className="grad" /></div>
            <div className="item">Squares = buildings with P ≥ 5 % (OpenStreetMap)</div>
          </div>
          <div className="controls-row top">
            {list.map((s) => <button key={s.key} className={`btn ${s.key === key ? 'primary' : ''}`} onClick={() => setKey(s.key)}>{s.name}</button>)}
          </div>
          <div className="controls-row">
            <button className="btn" onClick={() => terrain && setFocus({ x: 345000, y: 3128000, distKm: 75 })}>Whole island</button>
          </div>
        </div>
        <div className="kpis">
          <div className="kpi"><div className="k">Buildings reachable</div><div className="v">{r0(sc?.buildings?.expected)}</div><div className="s">P10–P90 {r0(sc?.buildings?.p10_p90[0])}–{r0(sc?.buildings?.p10_p90[1])} · {r0(sc?.n_buildings_exposed)} with P ≥ 5 %</div></div>
          <div className="kpi"><div className="k">Roads</div><div className="v">{fmt.num(sc?.road_km?.expected)}<small> km</small></div><div className="s">P10–P90 {fmt.num(sc?.road_km?.p10_p90[0])}–{fmt.num(sc?.road_km?.p10_p90[1])} km</div></div>
          <div className="kpi"><div className="k">Reaches the sea</div><div className="v">{sc?.reach_sea == null ? '—' : fmt.pct(sc.reach_sea)}</div><div className="s">of ensemble paths</div></div>
          <div className="kpi"><div className="k">Historical basis</div><div className="v" style={{ fontSize: 15 }}>{cur?.history ?? '—'}</div><div className="s">{sc?.n_paths ?? '—'} lava flow paths</div></div>
        </div>
      </div>
      <aside className="side">
        <section className="impact">
          <h3>What would be exposed · {cur?.name}</h3>
          {loading && <div className="loading">Computing the scenario (takes a few seconds the first time)…</div>}
          {err && <div className="note">Could not compute: {err}</div>}
          {sc?.unavailable && <div className="note">{sc.note}</div>}
          {sc?.note && !sc.unavailable && <p className="note" style={{ marginTop: 0 }}>{sc.note}</p>}
          {sc?.places && sc.places.length > 0 && <>
            <div className="subh">Neighbourhoods</div>
            <table className="places">
              <thead><tr><th>Neighbourhood</th><th>P</th></tr></thead>
              <tbody>{sc.places.slice(0, 10).map((p) => <tr key={p.name} style={{ cursor: 'pointer' }} onClick={() => setFocus({ x: p.x, y: p.y, distKm: 8 })}><td>{p.name}</td><td><span className="pbar" style={{ width: Math.max(2, p.p * 120) }} />{fmt.pct(p.p)}</td></tr>)}</tbody>
            </table>
          </>}
          {sc?.isolation && sc.isolation.length > 0 && <>
            <div className="subh">Neighbourhoods that could be cut off</div>
            <table className="places">
              <thead><tr><th>Neighbourhood</th><th>Reached</th><th>Isolated</th></tr></thead>
              <tbody>{sc.isolation.slice(0, 7).map((i) => <tr key={i.name}><td>{i.name}</td><td>{fmt.pct(i.p_reached)}</td><td className={i.p_isolated >= 0.2 ? 'warn' : ''}>{fmt.pct(i.p_isolated)}</td></tr>)}</tbody>
            </table>
          </>}
          {sc?.facilities && sc.facilities.length > 0 && <>
            <div className="subh">Services and infrastructure</div>
            <table className="places">
              <thead><tr><th>Service</th><th>P</th><th>Arrival P50</th></tr></thead>
              <tbody>{sc.facilities.slice(0, 10).map((f, k) => <tr key={k}><td>{f.kind}{f.name !== f.kind ? <span className="note"> · {f.name}</span> : null}</td><td>{fmt.pct(f.p)}</td><td>{fmt.hours(f.eta_h[1])}</td></tr>)}</tbody>
            </table>
          </>}
          {sc?.exposure_note && <p className="note">{sc.exposure_note}</p>}
          {sc && !sc.unavailable && <Exports items={[
            { label: 'PDF report', url: `/api/export/impact/tenerife/${key}.pdf`, file: `volscan_tenerife_${key}.pdf` },
            { label: 'CSV', url: `/api/export/impact/tenerife/${key}.csv`, file: `volscan_tenerife_${key}.csv` },
            { label: 'CAP alert (112)', url: `/api/cap/tenerife/${key}.xml`, file: `volscan_cap_tenerife_${key}.xml`, hint: 'CAP 1.2, status “Exercise”: scenario, not an alert' },
            { label: 'GeoJSON', url: `/ogc/collections/tenerife-escenario/items?escenario=${key}`, file: `volscan_tenerife_${key}.geojson` },
          ]} />}
        </section>
        <section>
          <h3>Layers</h3>
          <label className="check"><input type="checkbox" checked={showAssets} onChange={(e) => setShowAssets(e.target.checked)} /><span>Buildings reachable<span className="hint">yellow→maroon = probability</span></span></label>
        </section>
        <section>
          <h3>How to read this</h3>
          <p className="note">{note}</p>
          <p className="note">Same engine as La Palma 2021 (flow ensemble and impact engine), with vents at the historical eruptive centres and 700–800 m of uncertainty. Flow parameters are basaltic: valid for the rifts; a phonolitic eruption of Teide or Pico Viejo would give shorter, thicker flows and an explosive phase this model does not cover.</p>
          <p className="note">Sources: Copernicus DEM GLO-30 · © OpenStreetMap (ODbL) · IGN earthquake catalogue.</p>
        </section>
      </aside>
    </div>
  )
}

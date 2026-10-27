import { useEffect, useMemo, useState } from 'react'
import { api, fmt, type Terrain, type TfScenario } from '../api'
import Atlas3D, { type Label, type SurfacePoint } from '../three/Atlas3D'
import Exports from './Exports'

const r0 = (v: number | null | undefined) => (v == null ? '—' : Math.round(v).toLocaleString('es-ES'))
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

  useEffect(() => { api.terrain('tenerife').then(setTerrain); api.tfScenarios().then((d) => { setList(d.scenarios); setNote(d.note) }) }, [])
  useEffect(() => {
    let alive = true
    setLoading(true); setErr(null)
    api.tfScenario(key).then((d) => { if (alive) { setSc(d); const v = d.vents?.[0]?.xy; if (v) setFocus({ x: v[0], y: v[1] + 4000, distKm: 30 }) } })
      .catch((e) => alive && setErr(String(e))).finally(() => alive && setLoading(false))
    return () => { alive = false }
  }, [key])

  const labels: Label[] = useMemo(() => {
    const ls: Label[] = TOWNS.map(([text, x, y]) => ({ x, y, text }))
    if (sc?.vents && sc.key !== 'sismicidad_actual') sc.vents.forEach((v, i) => ls.push({ x: v.xy[0], y: v.xy[1], text: sc.vent_names?.[i] ?? 'Boca', kind: 'vent' }))
    return ls
  }, [sc])
  const assets: SurfacePoint[] = useMemo(() => (!showAssets || !sc?.buildings_at_risk_xy) ? [] : sc.buildings_at_risk_xy.map(([x, y, v]) => ({ x, y, v })), [sc, showAssets])
  const cur = list.find((s) => s.key === key)

  return (
    <div className="view">
      <div className="stage" style={{ gridTemplateRows: '1fr auto' }}>
        <div className="canvas-wrap">
          <Atlas3D terrain={terrain} overlay={sc?.overlay ?? null} labels={labels} surfacePoints={assets} focus={focus} exaggeration={1.6} terrainOpacity={0.95} />
          <div className="corner tl">Tenerife · relieve 100 m · escenario de planificación, no pronóstico</div>
          <div className="obs-card"><div className="k">Escenario</div><div className="v"><span className="dot warn" />{cur?.name ?? '—'}</div></div>
          <div className="legend-strip">
            <div className="item">Probabilidad de que la colada alcance cada punto en 30 días<span className="grad" /></div>
            <div className="item">Cuadrados = edificios con P ≥ 5 % (OpenStreetMap)</div>
          </div>
          <div className="controls-row top">
            {list.map((s) => <button key={s.key} className={`btn ${s.key === key ? 'primary' : ''}`} onClick={() => setKey(s.key)}>{s.name}</button>)}
          </div>
          <div className="controls-row">
            <button className="btn" onClick={() => terrain && setFocus({ x: 345000, y: 3128000, distKm: 75 })}>Isla completa</button>
          </div>
        </div>
        <div className="kpis">
          <div className="kpi"><div className="k">Edificios alcanzables</div><div className="v">{r0(sc?.buildings?.expected)}</div><div className="s">P10–P90 {r0(sc?.buildings?.p10_p90[0])}–{r0(sc?.buildings?.p10_p90[1])} · {r0(sc?.n_buildings_exposed)} con P ≥ 5 %</div></div>
          <div className="kpi"><div className="k">Carreteras</div><div className="v">{fmt.num(sc?.road_km?.expected)}<small> km</small></div><div className="s">P10–P90 {fmt.num(sc?.road_km?.p10_p90[0])}–{fmt.num(sc?.road_km?.p10_p90[1])} km</div></div>
          <div className="kpi"><div className="k">Llega al mar</div><div className="v">{sc?.reach_sea == null ? '—' : fmt.pct(sc.reach_sea)}</div><div className="s">de los recorridos del conjunto</div></div>
          <div className="kpi"><div className="k">Base histórica</div><div className="v" style={{ fontSize: 15 }}>{cur?.history ?? '—'}</div><div className="s">{sc?.n_paths ?? '—'} recorridos de colada</div></div>
        </div>
      </div>
      <aside className="side">
        <section className="impact">
          <h3>Qué quedaría expuesto · {cur?.name}</h3>
          {loading && <div className="loading">Calculando el escenario (la primera vez tarda unos segundos)…</div>}
          {err && <div className="note">No se pudo calcular: {err}</div>}
          {sc?.unavailable && <div className="note">{sc.note}</div>}
          {sc?.note && !sc.unavailable && <p className="note" style={{ marginTop: 0 }}>{sc.note}</p>}
          {sc?.places && sc.places.length > 0 && <>
            <div className="subh">Núcleos</div>
            <table className="places">
              <thead><tr><th>Núcleo</th><th>P</th></tr></thead>
              <tbody>{sc.places.slice(0, 10).map((p) => <tr key={p.name} style={{ cursor: 'pointer' }} onClick={() => setFocus({ x: p.x, y: p.y, distKm: 8 })}><td>{p.name}</td><td><span className="pbar" style={{ width: Math.max(2, p.p * 120) }} />{fmt.pct(p.p)}</td></tr>)}</tbody>
            </table>
          </>}
          {sc?.isolation && sc.isolation.length > 0 && <>
            <div className="subh">Barrios que podrían quedar aislados</div>
            <table className="places">
              <thead><tr><th>Núcleo</th><th>Alcanzado</th><th>Aislado</th></tr></thead>
              <tbody>{sc.isolation.slice(0, 7).map((i) => <tr key={i.name}><td>{i.name}</td><td>{fmt.pct(i.p_reached)}</td><td className={i.p_isolated >= 0.2 ? 'warn' : ''}>{fmt.pct(i.p_isolated)}</td></tr>)}</tbody>
            </table>
          </>}
          {sc?.facilities && sc.facilities.length > 0 && <>
            <div className="subh">Servicios e infraestructuras</div>
            <table className="places">
              <thead><tr><th>Servicio</th><th>P</th><th>Llegada P50</th></tr></thead>
              <tbody>{sc.facilities.slice(0, 10).map((f, k) => <tr key={k}><td>{f.kind}{f.name !== f.kind ? <span className="note"> · {f.name}</span> : null}</td><td>{fmt.pct(f.p)}</td><td>{fmt.hours(f.eta_h[1])}</td></tr>)}</tbody>
            </table>
          </>}
          {sc?.exposure_note && <p className="note">{sc.exposure_note}</p>}
          {sc && !sc.unavailable && <Exports items={[
            { label: 'Parte PDF', url: `/api/export/impact/tenerife/${key}.pdf`, file: `volscan_tenerife_${key}.pdf` },
            { label: 'CSV', url: `/api/export/impact/tenerife/${key}.csv`, file: `volscan_tenerife_${key}.csv` },
            { label: 'Aviso CAP (112)', url: `/api/cap/tenerife/${key}.xml`, file: `volscan_cap_tenerife_${key}.xml`, hint: 'CAP 1.2, estado «Exercise»: escenario, no alerta' },
            { label: 'GeoJSON', url: `/ogc/collections/tenerife-escenario/items?escenario=${key}`, file: `volscan_tenerife_${key}.geojson` },
          ]} />}
        </section>
        <section>
          <h3>Capas</h3>
          <label className="check"><input type="checkbox" checked={showAssets} onChange={(e) => setShowAssets(e.target.checked)} /><span>Edificios alcanzables<span className="hint">amarillo→granate = probabilidad</span></span></label>
        </section>
        <section>
          <h3>Cómo leer esto</h3>
          <p className="note">{note}</p>
          <p className="note">Mismo motor que en La Palma 2021 (conjunto de coladas y motor de impacto), con bocas en los centros eruptivos históricos y 700–800 m de incertidumbre. Los parámetros de la colada son basálticos: valen para las dorsales; una erupción fonolítica del Teide o Pico Viejo daría coladas más cortas y gruesas, y una fase explosiva que este modelo no cubre.</p>
          <p className="note">Fuentes: Copernicus DEM GLO-30 · © OpenStreetMap (ODbL) · IGN, catálogo de terremotos.</p>
        </section>
      </aside>
    </div>
  )
}

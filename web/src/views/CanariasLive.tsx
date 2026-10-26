import { useEffect, useMemo, useState } from 'react'
import { api, fmt, type Quake, type Terrain, type Zone } from '../api'
import Atlas3D, { type Label, type QuakePoint } from '../three/Atlas3D'

// UTM 28N approximation of zone centroids via the quakes we already have, falling back to fixed points
const ZONE_XY: Record<string, [number, number]> = {
  el_hierro: [205000, 3070000], la_palma: [221000, 3170000], la_gomera: [282000, 3115000], tenerife: [345000, 3130000],
  enmedio: [405000, 3105000], gran_canaria: [440000, 3090000], lanzarote_fuerteventura: [600000, 3165000],
}

function Spark({ data }: { data: number[] }) {
  const max = Math.max(1, ...data)
  const w = 120, h = 26
  const pts = data.map((v, i) => `${(i / (data.length - 1)) * w},${h - (v / max) * h}`).join(' ')
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

  const load = () => {
    api.zones().then((z) => { setZones(z.zones); setAt(z.at) })
    api.quakes(days).then((q) => setQuakes(q.quakes))
  }
  useEffect(() => { api.terrain('archipelago').then(setTerrain) }, [])
  useEffect(load, [days])

  const now = Date.now()
  const pts: QuakePoint[] = useMemo(() => quakes.filter((q) => q.depth != null && (!active || q.zone === active))
    .map((q) => ({ x: q.x, y: q.y, depth: q.depth as number, mag: (q.mag ?? 0.5) * 1.6, ageH: (now - Date.parse(q.t)) / 3600000 })), [quakes, active])
  const labels: Label[] = useMemo(() => zones.filter((z) => z.key !== 'enmedio').map((z) => ({ x: ZONE_XY[z.key][0], y: ZONE_XY[z.key][1] + 9000, text: z.name.replace(' y Fuerteventura', ' · Fuerteventura'), kind: 'zonelabel' as const })), [zones])
  const total7 = zones.reduce((a, z) => a + z.n7, 0)
  const maxMag = Math.max(...quakes.map((q) => q.mag ?? -9), -9)

  return (
    <div className="view">
      <div className="stage" style={{ gridTemplateRows: '1fr auto' }}>
        <div className="canvas-wrap">
          <Atlas3D terrain={terrain} quakes={pts} labels={labels} exaggeration={4} depthScale={1.2} terrainOpacity={0.9} maxDepthKm={40} focus={focus} quakeScale={6} />
          <div className="corner tl">Archipiélago · relieve 500 m ×4 · sismos IGN a su profundidad (×1,2)</div>
          <div className="obs-card"><div className="k">En directo</div><div className="v"><span className="dot ok" />catálogo IGN · {at ? fmt.dateTime(at) : '—'}</div></div>
          <div className="legend-strip"><div className="item"><b style={{ color: '#e23d14' }}>●</b> 24 h <b style={{ color: '#f08a35' }}>●</b> 7 días <b style={{ color: '#8f8577' }}>●</b> {days} días · tamaño = magnitud</div></div>
          <div className="controls-row">
            {[7, 30, 90, 365].map((d) => <button key={d} className={`btn ${d === days ? 'primary' : ''}`} onClick={() => setDays(d)}>{d === 365 ? '1 año' : `${d} d`}</button>)}
            <button className="btn" onClick={() => { setActive(null); setFocus({ x: 420000, y: 3150000, distKm: 260 }) }}>Archipiélago</button>
          </div>
        </div>
        <div className="kpis">
          <div className="kpi"><div className="k">Sismos 7 días · Canarias</div><div className="v">{fmt.int(total7)}</div><div className="s">en las zonas volcánicas analizadas</div></div>
          <div className="kpi"><div className="k">Sismos en pantalla</div><div className="v">{fmt.int(pts.length)}</div><div className="s">últimos {days} días{active ? ` · ${zones.find((z) => z.key === active)?.name}` : ''}</div></div>
          <div className="kpi"><div className="k">Magnitud máxima</div><div className="v">{maxMag > -9 ? fmt.num(maxMag) : '—'}</div><div className="s">en el periodo mostrado</div></div>
          <div className="kpi"><div className="k">Zona más activa</div><div className="v" style={{ fontSize: 20 }}>{zones[0]?.name ?? '—'}</div><div className="s">índice {zones[0]?.index == null ? '—' : fmt.num(zones[0].index)} / 10</div></div>
        </div>
      </div>
      <aside className="side">
        <section>
          <h3>Zonas volcánicas · índice de actividad anómala</h3>
          <div className="zone-list">
            {zones.map((z) => (
              <button key={z.key} className={`zone ${active === z.key ? 'active' : ''}`} onClick={() => { setActive(active === z.key ? null : z.key); setFocus({ x: ZONE_XY[z.key][0], y: ZONE_XY[z.key][1], distKm: 70 }) }}>
                <div className="row"><span className="name">{z.name}</span><span className="idx">{z.index == null ? '—' : fmt.num(z.index)}</span></div>
                <div className="idxbar"><i style={{ width: `${(z.index ?? 0) * 10}%` }} /></div>
                <div className="row" style={{ marginTop: 6 }}>
                  <Spark data={z.daily30} />
                  <span className="meta">{z.n7} sismos/7 d · {z.n30}/30 d</span>
                </div>
                <div className="meta">Mmáx 30 d {fmt.num(z.max_mag30)} · prof. mediana {fmt.num(z.depth_median30)} km{z.b ? ` · b ${fmt.num(z.b.b, 2)}` : ''}</div>
              </button>
            ))}
          </div>
          <p className="note">El índice (0–10) compara los últimos 7 días con el año anterior de cada zona: tasa, energía y somerización. <b>No es una probabilidad de erupción</b>. El semáforo oficial lo gestiona el PEVOLCA.</p>
          <button className="btn olive" disabled={refreshing} onClick={() => { setRefreshing(true); api.refresh().finally(() => { setRefreshing(false); load() }) }}>{refreshing ? 'Actualizando desde IGN…' : 'Actualizar desde IGN'}</button>
        </section>
        <section>
          <h3>Últimos sismos</h3>
          <table className="places">
            <thead><tr><th>Fecha UTC</th><th>M</th><th>Prof.</th></tr></thead>
            <tbody>
              {[...quakes].filter((q) => !active || q.zone === active).reverse().slice(0, 14).map((q) => (
                <tr key={q.id} title={q.place}><td>{fmt.dateTime(q.t)}<div className="note">{q.place}</div></td><td>{fmt.num(q.mag)}</td><td>{q.depth == null ? '—' : `${fmt.num(q.depth)} km`}</td></tr>
              ))}
            </tbody>
          </table>
          <p className="note">Fuente: Instituto Geográfico Nacional (IGN), Catálogo de terremotos. doi:10.7419/162.03.2022</p>
        </section>
      </aside>
    </div>
  )
}

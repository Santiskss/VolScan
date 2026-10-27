import { useEffect, useMemo, useRef, useState } from 'react'
import { api, fmt, type Citation, type DayState, type ImpactDay, type Meta, type Quake, type Terrain } from '../api'
import ImpactPanel from './ImpactPanel'
import { LevelChip, So2Bars } from './Indicators'
import Atlas3D, { type Label, type QuakePoint, type SurfacePoint } from '../three/Atlas3D'

type Brief = { text: string; ai: boolean; error?: string; model: { provider: string; model: string }; citations: Citation[] }

const DAY_MS = 86400000

export default function AtlasLaPalma() {
  const [meta, setMeta] = useState<Meta | null>(null)
  const [terrain, setTerrain] = useState<Terrain | null>(null)
  const [quakes, setQuakes] = useState<Quake[]>([])
  const [idx, setIdx] = useState(0)
  const [day, setDay] = useState<DayState | null>(null)
  const [playing, setPlaying] = useState(false)
  const [showQuakes, setShowQuakes] = useState(true)
  const [cumulative, setCumulative] = useState(false)
  const [showLava, setShowLava] = useState(true)
  const [showLabels, setShowLabels] = useState(true)
  const [opacity, setOpacity] = useState(0.82)
  const [depthScale, setDepthScale] = useState(0.5)
  const [brief, setBrief] = useState<Brief | null>(null)
  const [briefLoading, setBriefLoading] = useState(false)
  const [focus, setFocus] = useState<{ x: number; y: number; distKm: number } | null>(null)
  const [imp, setImp] = useState<ImpactDay | null>(null)
  const [impLoading, setImpLoading] = useState(false)
  const [showAssets, setShowAssets] = useState(true)
  const impCache = useRef(new Map<string, ImpactDay>())
  const cache = useRef(new Map<string, DayState>())

  useEffect(() => {
    api.lpMeta().then((m) => {
      setMeta(m)
      const want = location.hash.split('@')[1]
      const k = want ? m.days.indexOf(want) : -1
      setIdx(k >= 0 ? k : m.days.indexOf('2021-09-18'))
      setTimeout(() => setFocus({ x: m.vent.xy[0] - 2500, y: m.vent.xy[1] - 1500, distKm: 22 }), 400)
    })
    api.terrain('lapalma').then(setTerrain)
    api.lpQuakes().then((q) => setQuakes(q.quakes))
  }, [])

  const date = meta?.days[idx]

  useEffect(() => {
    if (!date) return
    const c = cache.current.get(date)
    if (c) { setDay(c); return }
    let alive = true
    api.lpDay(date).then((d) => { cache.current.set(date, d); if (alive) setDay(d) })
    // prefetch the next two days for smooth playback
    meta?.days.slice(idx + 1, idx + 3).forEach((d) => { if (!cache.current.has(d)) api.lpDay(d).then((v) => cache.current.set(d, v)) })
    return () => { alive = false }
  }, [date])

  useEffect(() => { setBrief(null) }, [date])

  useEffect(() => {
    if (!date) return
    const c = impCache.current.get(date)
    if (c) { setImp(c); return }
    let alive = true
    setImpLoading(true)
    api.lpImpact(date).then((d) => { impCache.current.set(date, d); if (alive) setImp(d) }).catch(() => alive && setImp(null)).finally(() => alive && setImpLoading(false))
    return () => { alive = false }
  }, [date])

  const assets: SurfacePoint[] = useMemo(() => (!showAssets || !imp?.buildings_at_risk_xy || imp.date !== date) ? [] :
    [...(imp.watch?.pocket_xy ?? []).map(([x, y]) => ({ x, y, v: -1 })), ...imp.buildings_at_risk_xy.map(([x, y, v]) => ({ x, y, v }))], [imp, showAssets, date])
  const scenarioOverlay = imp && imp.date === date && imp.phase === 'pre-eruptive' ? imp.scenario?.overlay ?? null : null

  useEffect(() => {
    if (!playing || !meta) return
    const t = setTimeout(() => setIdx((i) => (i + 1 < meta.days.length ? i + 1 : (setPlaying(false), i))), 1100)
    return () => clearTimeout(t)
  }, [playing, idx, meta])

  const nowMs = date ? Date.parse(date + 'T23:59:00Z') : 0
  const qpoints: QuakePoint[] = useMemo(() => {
    if (!showQuakes || !date) return []
    const from = cumulative ? Date.parse('2021-09-01T00:00:00Z') : nowMs - 7 * DAY_MS
    return quakes
      .filter((q) => { const t = Date.parse(q.t); return t <= nowMs && t > from && q.depth != null })
      .map((q) => ({ x: q.x, y: q.y, depth: q.depth as number, mag: q.mag ?? 0.5, ageH: (nowMs - Date.parse(q.t)) / 3600000 }))
  }, [quakes, nowMs, showQuakes, cumulative, date])

  const labels: Label[] = useMemo(() => {
    if (!meta || !showLabels) return []
    const main = ['Todoque', 'La Laguna', 'Los Llanos de Aridane', 'Tazacorte', 'Puerto Naos', 'El Paso', 'Los Guirres (Tazacorte)']
    const ls: Label[] = meta.places.filter((p) => main.includes(p.name)).map((p) => ({ x: p.x, y: p.y, text: p.name.replace(' (Tazacorte)', '') }))
    if (date && date >= '2021-09-19') ls.push({ x: meta.vent.xy[0], y: meta.vent.xy[1], text: 'Boca · 19 sep', kind: 'vent' })
    return ls
  }, [meta, showLabels, date])

  const lava = day?.lava
  const eruptive = lava && lava.phase === 'eruptive' ? lava : null
  const seis = day?.seismic
  const milestone = meta?.milestones.find((m) => m.date === date)

  const loadBrief = (regen = false) => {
    if (!date) return
    setBriefLoading(true)
    api.lpBriefing(date, regen).then(setBrief).finally(() => setBriefLoading(false))
  }

  const daysSinceOnset = eruptive ? eruptive.hours_since_onset / 24 : null

  return (
    <div className="view">
      <div className="stage">
        <div className="canvas-wrap">
          <Atlas3D terrain={terrain} overlay={showLava ? day?.overlay ?? scenarioOverlay : null} quakes={qpoints} labels={labels} surfacePoints={assets}
            depthScale={depthScale} terrainOpacity={opacity} focus={focus} />
          <div className="corner tl">La Palma · Cumbre Vieja · relieve previo a 2021 · profundidad ×{depthScale.toString().replace('.', ',')}</div>
          {date && (
            <div className="obs-card">
              <div className="k">{eruptive ? `Día ${Math.floor(daysSinceOnset ?? 0) + 1} de erupción` : 'Fase pre-eruptiva'}</div>
              <div className="v"><span className="dot bad" style={{ background: eruptive ? 'var(--lava)' : 'var(--amber)' }} />{fmt.date(date + 'T12:00:00Z')} · fin del día UTC</div>
            </div>
          )}
          <div className="legend-strip">
            {showQuakes && <div className="item">Sismos IGN bajo la isla · <b style={{ color: '#e23d14' }}>●</b> 24 h <b style={{ color: '#f08a35' }}>●</b> 7 d <b style={{ color: '#8f8577' }}>●</b> anteriores · tamaño = magnitud</div>}
            {showLava && eruptive && <div className="item">Probabilidad de colada (72 h)<span className="grad" />· mancha oscura con borde naranja = colada observada CEMS</div>}
            <div className="item">Reconstrucción con datos reales · usa solo lo disponible ese día</div>
          </div>
          <div className="controls-row">
            <button className="btn" onClick={() => meta && setFocus({ x: meta.vent.xy[0] - 3000, y: meta.vent.xy[1], distKm: 16 })}>Foco erupción</button>
            <button className="btn" onClick={() => terrain && setFocus({ x: terrain.west + terrain.cols * terrain.step / 2, y: terrain.north - terrain.rows * terrain.step / 2, distKm: 50 })}>Isla completa</button>
          </div>
        </div>

        <div className="timeline">
          <div className="tl-buttons">
            <button className="btn" onClick={() => setIdx((i) => Math.max(0, i - 1))}>‹</button>
            <button className="btn primary" onClick={() => setPlaying((p) => !p)}>{playing ? '❚❚' : '▶'}</button>
            <button className="btn" onClick={() => meta && setIdx((i) => Math.min(meta.days.length - 1, i + 1))}>›</button>
          </div>
          <div>
            <div className="tl-date">{date ? fmt.date(date + 'T12:00:00Z') : '—'}</div>
            <div className="tl-sub">{milestone ? milestone.text : 'Tajogaite · 2021'}</div>
          </div>
          <div className="track">
            {meta && <>
              <div className="onset" style={{ left: `${(meta.days.indexOf('2021-09-19') / (meta.days.length - 1)) * 100}%` }} />
              {meta.milestones.map((m) => {
                const k = meta.days.indexOf(m.date)
                return k >= 0 ? <div key={m.date} className="tick major" title={m.text} style={{ left: `${(k / (meta.days.length - 1)) * 100}%` }} /> : null
              })}
              {meta.observations.map((o) => {
                const k = meta.days.indexOf(o.at.slice(0, 10))
                return k >= 0 ? <div key={o.at} className="tick" style={{ left: `${(k / (meta.days.length - 1)) * 100}%` }} /> : null
              })}
              <input type="range" min={0} max={meta.days.length - 1} value={idx} onChange={(e) => { setPlaying(false); setIdx(+e.target.value) }} />
            </>}
          </div>
          <div className="tl-note">Marcas rojas: hitos reales. Marcas grises: cartografías CEMS. No se interpola la colada observada.</div>
        </div>

        <div className="kpis">
          <div className="kpi">
            <div className="k">Sismos 24 h · La Palma</div>
            <div className="v">{fmt.int(seis?.last24h.n)}<small>eventos</small></div>
            <div className="s">Mmáx {fmt.num(seis?.last24h.max_mag)} · prof. mediana {fmt.num(seis?.last24h.depth_median_km)} km</div>
          </div>
          <div className="kpi">
            <div className="k">Índice de actividad anómala</div>
            <div className="v">{seis?.unrest_index == null ? '—' : fmt.num(seis.unrest_index)}<small>/ 10</small></div>
            <div className="s">{seis?.rate_ratio != null ? `×${fmt.int(seis.rate_ratio)} la tasa base` : 'sin línea base suficiente'}{seis?.shallowing_km != null ? ` · ${fmt.num(seis.shallowing_km)} km más somero` : ''}</div>
          </div>
          <div className="kpi">
            <div className="k">Colada observada (CEMS)</div>
            <div className="v">{eruptive?.observation ? fmt.num(eruptive.observation.area_ha, 0) : '—'}<small>ha</small></div>
            <div className="s">{eruptive?.observation ? `frente a ${fmt.num(eruptive.observation.reach_m / 1000)} km de la boca · hace ${fmt.hours(eruptive.observation.age_h)}` : 'sin erupción'}</div>
          </div>
          <div className="kpi">
            <div className="k">Lava al mar · pronóstico</div>
            <div className="v">{eruptive ? (eruptive.sea.observed_reached ? 'Llegó' : fmt.pct(eruptive.sea.p_ever)) : '—'}</div>
            <div className="s">{eruptive && !eruptive.sea.observed_reached && eruptive.sea.eta_h[1] != null
              ? `P50 en ${fmt.hours(eruptive.sea.eta_h[1])} · P10–P90 ${fmt.hours(eruptive.sea.eta_h[0])}–${fmt.hours(eruptive.sea.eta_h[2])}`
              : eruptive?.sea.observed_reached ? 'observado por CEMS' : ''}</div>
          </div>
        </div>
      </div>

      <aside className="side">
        <ImpactPanel imp={imp && imp.date === date ? imp : null} loading={impLoading} />

        <section className="incident">
          <h3>Parte de situación · IA</h3>
          {!brief && <button className="btn olive" disabled={briefLoading || !date} onClick={() => loadBrief()}>{briefLoading ? 'Redactando…' : 'Ver parte de este día'}</button>}
          {brief && <>
            <div className={`brief ${brief.ai ? '' : 'na'}`}>{brief.text}</div>
            <div className="brief-meta">
              <span>{brief.ai ? `${brief.model.provider === 'meta' ? 'Meta' : 'Local'} · ${brief.model.model}` : 'Sin modelo disponible'}</span>
              {brief.ai && <button className="btn" style={{ padding: '2px 8px' }} onClick={() => loadBrief(true)}>Rehacer</button>}
            </div>
            {brief.citations.length > 0 && <div className="note" style={{ marginTop: 6 }}>Fuentes: {brief.citations.map((c) => `[${c.n}] ${c.doc}`).join(' · ')}</div>}
          </>}
        </section>

        <section>
          <h3>Núcleos · probabilidad y llegada</h3>
          {eruptive ? (
            <table className="places">
              <thead><tr><th>Núcleo</th><th>P</th><th>Llegada P50</th></tr></thead>
              <tbody>
                {eruptive.places.filter((p) => p.p_ever > 0.004 || p.observed_reached).slice(0, 8).map((p) => (
                  <tr key={p.name} onClick={() => { const pl = meta?.places.find((q) => q.name === p.name); if (pl) setFocus({ x: pl.x, y: pl.y, distKm: 8 }) }} style={{ cursor: 'pointer' }}>
                    <td>{p.name}</td>
                    <td><span className="pbar" style={{ width: Math.max(2, p.p_ever * 50) }} />{fmt.pct(p.p_ever)}</td>
                    <td>{p.observed_reached ? <span className="reached">ALCANZADO</span> : fmt.hours(p.eta_h[1])}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <div className="note">Antes de la erupción no hay pronóstico de colada: no se sabe dónde abrirá la boca. VolScan muestra la sismicidad y su evolución en profundidad.</div>}
          {eruptive && <div className="note" style={{ marginTop: 8 }}>Conjunto de {eruptive.n_members} recorridos reponderado con {eruptive.observation?.n_observations ?? 0} cartografías (ESS {fmt.int(eruptive.ess)}). {eruptive.observation?.front_stalled && eruptive.observation?.area_growing ? '' : ''}</div>}
          {eruptive?.observation?.front_stalled && eruptive.observation.area_growing && <div className="flag">FRENTE DETENIDO · ÁREA CRECIENDO → POSIBLE DESBORDAMIENTO</div>}
        </section>

        <section>
          <h3>Capas</h3>
          <label className="check"><input type="checkbox" checked={showQuakes} onChange={(e) => setShowQuakes(e.target.checked)} /><span>Sismos en profundidad<span className="hint">IGN · catálogo de terremotos</span></span></label>
          <label className="check"><input type="checkbox" checked={cumulative} onChange={(e) => setCumulative(e.target.checked)} /><span>Acumulado desde el 1 sep<span className="hint">si no, últimos 7 días</span></span></label>
          <label className="check"><input type="checkbox" checked={showLava} onChange={(e) => setShowLava(e.target.checked)} /><span>Pronóstico y colada observada<span className="hint">conjunto VolScan · Copernicus EMS EMSR546</span></span></label>
          <label className="check"><input type="checkbox" checked={showAssets} onChange={(e) => setShowAssets(e.target.checked)} /><span>Edificios en riesgo (72 h)<span className="hint">inventario Copernicus EMS · amarillo→granate = probabilidad · azul = cercado por la colada</span></span></label>
          <label className="check"><input type="checkbox" checked={showLabels} onChange={(e) => setShowLabels(e.target.checked)} /><span>Topónimos<span className="hint">© OpenStreetMap</span></span></label>
          <div className="slider-row"><span>Transparencia del terreno</span><span>{Math.round((1 - opacity) * 100)} %</span></div>
          <input type="range" min={0.3} max={1} step={0.02} value={opacity} onChange={(e) => setOpacity(+e.target.value)} style={{ width: '100%' }} />
          <div className="slider-row"><span>Escala de profundidad</span><span>×{depthScale}</span></div>
          <input type="range" min={0.2} max={1} step={0.1} value={depthScale} onChange={(e) => setDepthScale(+e.target.value)} style={{ width: '100%' }} />
        </section>

        {day?.indicators && <section>
          <h3>Deformación y gases</h3>
          <table className="places">
            <thead><tr><th>GNSS</th><th>Este / Norte / Vertical</th><th>Nivel</th></tr></thead>
            <tbody>{day.indicators.gnss.map((g) => <tr key={g.code}><td>{g.code}<div className="note">{g.place}</div></td>
              <td>{g.disp_mm ? `${fmt.num(g.disp_mm.e)} / ${fmt.num(g.disp_mm.n)} / ${fmt.num(g.disp_mm.u)} mm` : '—'}</td><td><LevelChip level={g.level} /></td></tr>)}</tbody>
          </table>
          <p className="note">Desplazamiento desde el 10 sep 2021 (antes del enjambre). Estaciones públicas a 10–17 km de la boca: ven el hundimiento durante la erupción, pero no la hinchazón previa que midió el IGN junto a la boca (sus estaciones cercanas no son públicas).</p>
          <div className="subh">SO2 por satélite (kt sobre Canarias) · <LevelChip level={day.indicators.so2.level} /></div>
          <So2Bars series={day.indicators.so2_series} threshold={day.indicators.so2.threshold_kt ?? 1} />
        </section>}

        <section>
          <h3>Sismicidad · detalle</h3>
          <div className="kv">
            <span className="k">b-value (7 d)</span><span>{seis?.b_recent ? `${fmt.num(seis.b_recent.b, 2)} ± ${fmt.num(seis.b_recent.sigma, 2)}` : '—'}</span>
            <span className="k">Componente tasa</span><span>{fmt.num(seis?.components.rate ?? null, 2)}</span>
            <span className="k">Componente energía</span><span>{fmt.num(seis?.components.energy ?? null, 2)}</span>
            <span className="k">Componente somerización</span><span>{fmt.num(seis?.components.shallow ?? null, 2)}</span>
          </div>
          <p className="note">El índice compara los últimos 7 días con el año anterior de la zona. No es una probabilidad de erupción. Las alertas oficiales son del PEVOLCA.</p>
        </section>

        <section>
          <h3>Fuentes</h3>
          {meta?.sources.map((s) => <div key={s} className="note">· {s}</div>)}
          <div className="note">· Relieve: {terrain?.attribution}</div>
        </section>
      </aside>
    </div>
  )
}

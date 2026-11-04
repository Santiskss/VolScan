import { useEffect, useMemo, useRef, useState } from 'react'
import { api, fmt, modelLabel, type AgentResponse, type Citation, type DayState, type ImpactDay, type Meta, type Quake, type Sam3Day, type Terrain } from '../api'
import ImpactPanel from './ImpactPanel'
import { LevelChip, So2Bars } from './Indicators'
import Atlas3D, { preloadImage, type Label, type QuakePoint, type SurfacePoint } from '../three/Atlas3D'

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
  const [sam3, setSam3] = useState<Sam3Day | null>(null)
  const [sam3Loading, setSam3Loading] = useState(false)
  const [useSam3Overlay, setUseSam3Overlay] = useState(false)
  const [agentQ, setAgentQ] = useState('')
  const [agentRes, setAgentRes] = useState<AgentResponse | null>(null)
  const [agentLoading, setAgentLoading] = useState(false)
  const [focus, setFocus] = useState<{ x: number; y: number; distKm: number } | null>(null)
  const [imp, setImp] = useState<ImpactDay | null>(null)
  const [impLoading, setImpLoading] = useState(false)
  const [showAssets, setShowAssets] = useState(true)
  const impCache = useRef(new Map<string, ImpactDay>())
  const cache = useRef(new Map<string, DayState>())

  useEffect(() => {
    let alive = true
    api.lpMeta().then((m) => {
      if (!alive) return
      setMeta(m)
      const want = location.hash.split('@')[1]
      const k = want ? m.days.indexOf(want) : -1
      setIdx(k >= 0 ? k : m.days.indexOf('2021-09-18'))
      setTimeout(() => setFocus({ x: m.vent.xy[0] - 2500, y: m.vent.xy[1] - 1500, distKm: 22 }), 400)
      // Pre-warm milestone dates first, then progressively warm all 106 days in small batches
      const milestoneDates = m.milestones.map((ms) => ms.date)
      const ordered = [...new Set([...milestoneDates, ...m.days])]
      let cursor = 0
      const pump = () => {
        if (!alive || cursor >= ordered.length) return
        const batch = ordered.slice(cursor, cursor + 6)
        cursor += 6
        Promise.all(batch.map((dStr) => {
          if (cache.current.has(dStr)) return Promise.resolve()
          return api.lpDay(dStr).then((v) => { preloadImage(v.overlay?.png); cache.current.set(dStr, v) }).catch(() => {})
        })).finally(() => {
          if (alive && cursor < ordered.length) setTimeout(pump, 35)
        })
      }
      setTimeout(pump, 250)
      milestoneDates.forEach((dStr) => {
        if (!impCache.current.has(dStr)) {
          api.lpImpact(dStr).then((v) => { preloadImage(v.scenario?.overlay?.png); impCache.current.set(dStr, v) }).catch(() => {})
        }
      })
    })
    api.terrain('lapalma').then((t) => { preloadImage(t.texture); setTerrain(t) })
    api.lpQuakes().then((q) => setQuakes(q.quakes))
    return () => { alive = false }
  }, [])

  const date = meta?.days[idx]

  useEffect(() => {
    if (!date) return
    let alive = true
    const cDay = cache.current.get(date)
    const cImp = impCache.current.get(date)
    if (cDay) setDay(cDay)
    else {
      api.lpDay(date).then((d) => {
        preloadImage(d.overlay?.png)
        cache.current.set(date, d)
        if (alive) setDay(d)
      }).catch(() => {})
    }
    if (cImp) {
      setImp(cImp)
      setImpLoading(false)
      return () => { alive = false }
    }
    setImpLoading(true)
    const timer = setTimeout(() => {
      if (!alive) return
      api.lpImpact(date)
        .then((d) => { preloadImage(d.scenario?.overlay?.png); impCache.current.set(date, d); if (alive) setImp(d) })
        .catch(() => { if (alive) setImp(null) })
        .finally(() => { if (alive) setImpLoading(false) })
    }, 55)
    return () => { alive = false; clearTimeout(timer) }
  }, [date])

  useEffect(() => { setBrief(null); setSam3(null); setUseSam3Overlay(false) }, [date])

  const assets: SurfacePoint[] = useMemo(() => (!showAssets || !imp?.buildings_at_risk_xy || imp.date !== date) ? [] :
    [...(imp.watch?.pocket_xy ?? []).map(([x, y]) => ({ x, y, v: -1 })), ...imp.buildings_at_risk_xy.map(([x, y, v]) => ({ x, y, v }))], [imp, showAssets, date])
  const scenarioOverlay = imp && imp.date === date && imp.phase === 'pre-eruptive' ? imp.scenario?.overlay ?? null : null
  const activeOverlay = useSam3Overlay && sam3?.overlay ? sam3.overlay : (day?.overlay ?? scenarioOverlay)

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
    if (date && date >= '2021-09-19') ls.push({ x: meta.vent.xy[0], y: meta.vent.xy[1], text: 'Vent · 19 Sep', kind: 'vent' })
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

  const loadSam3 = () => {
    if (!date) return
    setSam3Loading(true)
    api.lpSam3(date).then((res) => { preloadImage(res.overlay?.png); setSam3(res); if (res.available) setUseSam3Overlay(true) }).finally(() => setSam3Loading(false))
  }

  const askAgent = (qText?: string) => {
    const q = (qText ?? agentQ).trim()
    if (!q || !date) return
    setAgentQ(q)
    setAgentLoading(true)
    api.chat(q, `lapalma2021:${date}`).then(setAgentRes).finally(() => setAgentLoading(false))
  }

  const daysSinceOnset = eruptive ? eruptive.hours_since_onset / 24 : null

  return (
    <div className="view">
      <div className="stage">
        <div className="canvas-wrap">
          <Atlas3D terrain={terrain} overlay={showLava ? activeOverlay : null} quakes={qpoints} labels={labels} surfacePoints={assets}
            depthScale={depthScale} terrainOpacity={opacity} focus={focus} />
          <div className="corner tl">La Palma · Cumbre Vieja · pre-2021 terrain · depth ×{depthScale.toString()}</div>
          {date && (
            <div className="obs-card">
              <div className="k">{eruptive ? `Eruption day ${Math.floor(daysSinceOnset ?? 0) + 1}` : 'Pre-eruptive phase'}</div>
              <div className="v"><span className="dot bad" style={{ background: eruptive ? 'var(--lava)' : 'var(--amber)' }} />{fmt.date(date + 'T12:00:00Z')} · end of day UTC</div>
            </div>
          )}
          <div className="legend-strip">
            {showQuakes && <div className="item">IGN earthquakes under the island · <b style={{ color: '#e23d14' }}>●</b> 24 h <b style={{ color: '#f08a35' }}>●</b> 7 d <b style={{ color: '#8f8577' }}>●</b> older · size = magnitude</div>}
            {showLava && eruptive && <div className="item">Lava flow probability (72 h)<span className="grad" />· dark patch with orange edge = {useSam3Overlay ? 'synthetic mask' : 'CEMS observed flow'}</div>}
            <div className="item">Reconstruction from real data · uses only what was available that day</div>
          </div>
          <div className="controls-row">
            <button className="btn" onClick={() => meta && setFocus({ x: meta.vent.xy[0] - 3000, y: meta.vent.xy[1], distKm: 16 })}>Eruption focus</button>
            <button className="btn" onClick={() => terrain && setFocus({ x: terrain.west + terrain.cols * terrain.step / 2, y: terrain.north - terrain.rows * terrain.step / 2, distKm: 50 })}>Whole island</button>
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
          <div className="tl-note">Red marks: real milestones. Grey marks: CEMS maps. The observed flow is never interpolated.</div>
        </div>

        <div className="kpis">
          <div className="kpi">
            <div className="k">Earthquakes 24 h · La Palma</div>
            <div className="v">{fmt.int(seis?.last24h.n)}<small>events</small></div>
            <div className="s">Mmax {fmt.num(seis?.last24h.max_mag)} · median depth {fmt.num(seis?.last24h.depth_median_km)} km</div>
          </div>
          <div className="kpi">
            <div className="k">Unrest index</div>
            <div className="v">{seis?.unrest_index == null ? '—' : fmt.num(seis.unrest_index)}<small>/ 10</small></div>
            <div className="s">{seis?.rate_ratio != null ? `×${fmt.int(seis.rate_ratio)} the baseline rate` : 'not enough baseline'}{seis?.shallowing_km != null ? ` · ${fmt.num(seis.shallowing_km)} km shallower` : ''}</div>
          </div>
          <div className="kpi">
            <div className="k">Observed flow (CEMS)</div>
            <div className="v">{eruptive?.observation ? fmt.num(eruptive.observation.area_ha, 0) : '—'}<small>ha</small></div>
            <div className="s">{eruptive?.observation ? `front ${fmt.num(eruptive.observation.reach_m / 1000)} km from the vent · ${fmt.hours(eruptive.observation.age_h)} ago` : 'no eruption'}</div>
          </div>
          <div className="kpi">
            <div className="k">Lava to the sea · forecast</div>
            <div className="v">{eruptive ? (eruptive.sea.observed_reached ? 'Reached' : fmt.pct(eruptive.sea.p_ever)) : '—'}</div>
            <div className="s">{eruptive && !eruptive.sea.observed_reached && eruptive.sea.eta_h[1] != null
              ? `P50 in ${fmt.hours(eruptive.sea.eta_h[1])} · P10–P90 ${fmt.hours(eruptive.sea.eta_h[0])}–${fmt.hours(eruptive.sea.eta_h[2])}`
              : eruptive?.sea.observed_reached ? 'observed by CEMS' : ''}</div>
          </div>
        </div>
      </div>

      <aside className="side">
        <ImpactPanel imp={imp && imp.date === date ? imp : null} loading={impLoading} />

        {eruptive && (
          <section className="incident">
            <h3>Synthetic segmentation experiment</h3><p className="note">The thermal scenes are generated from the CEMS reference itself. A match does not validate satellite segmentation or any operational lead time. Real inference needs a verified provider.</p>
            {!sam3 && (
              <button className="btn olive" disabled={sam3Loading || !date} onClick={loadSam3}>
                {sam3Loading ? 'Running experiment…' : 'Run synthetic demo'}
              </button>
            )}
            {sam3 && !sam3.available && <div className="note">{sam3.note}</div>}
            {sam3 && sam3.available && sam3.comparison_vs_cems && sam3.assimilated_forecast && (
              <>
                <div className="kv" style={{ marginTop: 4 }}>
                  <span className="k">Hexagonal adapter</span>
                  <span>{sam3.segmentation?.adapter} · {sam3.segmentation?.model}</span>
                  <span className="k">SAM 3.1 vs CEMS area</span>
                  <span><b>{fmt.num(sam3.comparison_vs_cems.sam3_area_ha)} ha</b> vs {fmt.num(sam3.comparison_vs_cems.cems_area_ha)} ha (IoU <b>{fmt.num(sam3.comparison_vs_cems.iou, 3)}</b>)</span>
                  <span className="k">Front reach</span>
                  <span>{fmt.int(sam3.comparison_vs_cems.sam3_reach_m)} m vs {fmt.int(sam3.comparison_vs_cems.cems_reach_m)} m</span>
                  <span className="k">Lead time over CEMS</span>
                  <span>No operational lead time shown; input generated from CEMS.</span>
                  <span className="k">Sea (SAM 3.1 assimilated)</span>
                  <span>{fmt.pct(sam3.assimilated_forecast.sea_p_ever)} (ESS {fmt.num(sam3.assimilated_forecast.ess)})</span>
                </div>
                <label className="check" style={{ marginTop: 8 }}>
                  <input type="checkbox" checked={useSam3Overlay} onChange={(e) => setUseSam3Overlay(e.target.checked)} />
                  <span>Project the SAM 3.1 mask on the 3D terrain<span className="hint">{sam3.segmentation?.n_prompt_points} spatial prompts · {fmt.num(sam3.segmentation?.latency_ms)} ms</span></span>
                </label>
              </>
            )}
          </section>
        )}

        <section className="incident">
          <h3>Situation report · AI</h3>
          {!brief && <button className="btn olive" disabled={briefLoading || !date} onClick={() => loadBrief()}>{briefLoading ? 'Drafting…' : 'View this day’s report'}</button>}
          {brief && <>
            <div className={`brief ${brief.ai ? '' : 'na'}`}>{brief.text}</div>
            <div className="brief-meta">
              <span>{brief.ai ? modelLabel(brief.model.provider, brief.model.model) : 'Deterministic summary without LLM'}</span>
              {brief.ai && <button className="btn" style={{ padding: '2px 8px' }} onClick={() => loadBrief(true)}>Redo</button>}
            </div>
            {brief.citations.length > 0 && <div className="note" style={{ marginTop: 6 }}>Sources: {brief.citations.map((c) => `[${c.n}] ${c.doc}`).join(' · ')}</div>}
          </>}
        </section>

        <section className="incident">
          <h3>Operations agent · Tool calling</h3>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 6 }}>
            <button className="btn" style={{ fontSize: 11, padding: '2px 7px' }} onClick={() => askAgent(`What does Meta SAM 3.1 measure on ${date} compared with Copernicus?`)}>SAM 3.1 today</button>
            <button className="btn" style={{ fontSize: 11, padding: '2px 7px' }} onClick={() => askAgent('Simulate the north-west rift scenario on Tenerife')}>Tenerife NW rift</button>
            <button className="btn" style={{ fontSize: 11, padding: '2px 7px' }} onClick={() => askAgent(`Preview the CAP 1.2 alert for 112 on ${date}`)}>CAP 1.2 · 112</button>
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            <input
              type="text"
              value={agentQ}
              onChange={(e) => setAgentQ(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && askAgent()}
              placeholder="Ask the agent (runs real tools)…"
              style={{ flex: 1, fontSize: 12, padding: '5px 8px', border: '1px solid var(--line)', borderRadius: 4, background: 'var(--bg)' }}
            />
            <button className="btn olive" disabled={agentLoading || !agentQ.trim()} onClick={() => askAgent()}>
              {agentLoading ? '…' : 'Ask'}
            </button>
          </div>
          {agentRes && (
            <div style={{ marginTop: 8 }}>
              {agentRes.tool_calls && agentRes.tool_calls.length > 0 && (
                <div className="note" style={{ marginBottom: 4 }}>
                  <b>Tools executed:</b> {agentRes.tool_calls.map((t) => `${t.name} (${fmt.num(t.duration_ms, 0)} ms)`).join(' · ')}
                </div>
              )}
              <div className={`brief ${agentRes.ai ? '' : 'na'}`}>{agentRes.answer}</div>
              <div className="brief-meta">
                <span>{agentRes.ai ? modelLabel(agentRes.model.provider, agentRes.model.model) : 'Deterministic engine + RAG'}</span>
              </div>
            </div>
          )}
        </section>

        <section>
          <h3>Neighbourhoods · probability and arrival</h3>
          {eruptive ? (
            <table className="places">
              <thead><tr><th>Neighbourhood</th><th>P</th><th>Arrival P50</th></tr></thead>
              <tbody>
                {eruptive.places.filter((p) => p.p_ever > 0.004 || p.observed_reached).slice(0, 8).map((p) => (
                  <tr key={p.name} onClick={() => { const pl = meta?.places.find((q) => q.name === p.name); if (pl) setFocus({ x: pl.x, y: pl.y, distKm: 8 }) }} style={{ cursor: 'pointer' }}>
                    <td>{p.name}</td>
                    <td><span className="pbar" style={{ width: Math.max(2, p.p_ever * 50) }} />{fmt.pct(p.p_ever)}</td>
                    <td>{p.observed_reached ? <span className="reached">REACHED</span> : fmt.hours(p.eta_h[1])}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <div className="note">Before the eruption there is no flow forecast: nobody knows where the vent will open. VolScan shows the seismicity and how it moves at depth.</div>}
          {eruptive && <div className="note" style={{ marginTop: 8 }}>Ensemble of {eruptive.n_members} paths reweighted with {eruptive.observation?.n_observations ?? 0} maps (ESS {fmt.int(eruptive.ess)}). {eruptive.observation?.front_stalled && eruptive.observation?.area_growing ? '' : ''}</div>}
          {eruptive?.observation?.front_stalled && eruptive.observation.area_growing && <div className="flag">FRONT STALLED · AREA GROWING → POSSIBLE OVERFLOW</div>}
        </section>

        <section>
          <h3>Layers</h3>
          <label className="check"><input type="checkbox" checked={showQuakes} onChange={(e) => setShowQuakes(e.target.checked)} /><span>Earthquakes at depth<span className="hint">IGN · earthquake catalogue</span></span></label>
          <label className="check"><input type="checkbox" checked={cumulative} onChange={(e) => setCumulative(e.target.checked)} /><span>Cumulative since 1 Sep<span className="hint">otherwise, last 7 days</span></span></label>
          <label className="check"><input type="checkbox" checked={showLava} onChange={(e) => setShowLava(e.target.checked)} /><span>Forecast and observed flow<span className="hint">VolScan ensemble · Copernicus EMS EMSR546</span></span></label>
          <label className="check"><input type="checkbox" checked={showAssets} onChange={(e) => setShowAssets(e.target.checked)} /><span>Buildings at risk (72 h)<span className="hint">Copernicus EMS inventory · yellow→maroon = probability · blue = hemmed in by the flow</span></span></label>
          <label className="check"><input type="checkbox" checked={showLabels} onChange={(e) => setShowLabels(e.target.checked)} /><span>Place names<span className="hint">© OpenStreetMap</span></span></label>
          <div className="slider-row"><span>Terrain transparency</span><span>{Math.round((1 - opacity) * 100)} %</span></div>
          <input type="range" min={0.3} max={1} step={0.02} value={opacity} onChange={(e) => setOpacity(+e.target.value)} style={{ width: '100%' }} />
          <div className="slider-row"><span>Depth scale</span><span>×{depthScale}</span></div>
          <input type="range" min={0.2} max={1} step={0.1} value={depthScale} onChange={(e) => setDepthScale(+e.target.value)} style={{ width: '100%' }} />
        </section>

        {day?.indicators && <section>
          <h3>Deformation and gas</h3>
          <table className="places">
            <thead><tr><th>GNSS</th><th>East / North / Up</th><th>Level</th></tr></thead>
            <tbody>{day.indicators.gnss.map((g) => <tr key={g.code}><td>{g.code}<div className="note">{g.place}</div></td>
              <td>{g.disp_mm ? `${fmt.num(g.disp_mm.e)} / ${fmt.num(g.disp_mm.n)} / ${fmt.num(g.disp_mm.u)} mm` : '—'}</td><td><LevelChip level={g.level} /></td></tr>)}</tbody>
          </table>
          <p className="note">Displacement since 10 Sep 2021 (before the swarm). Public stations 10–17 km from the vent see the subsidence during the eruption, but not the earlier uplift the IGN measured next to the vent (its nearby stations are not public).</p>
          <div className="subh">Satellite SO2 (kt over the Canaries) · <LevelChip level={day.indicators.so2.level} /></div>
          <So2Bars series={day.indicators.so2_series} threshold={day.indicators.so2.threshold_kt ?? 1} />
        </section>}

        <section>
          <h3>Seismicity · detail</h3>
          <div className="kv">
            <span className="k">b-value (7 d)</span><span>{seis?.b_recent ? `${fmt.num(seis.b_recent.b, 2)} ± ${fmt.num(seis.b_recent.sigma, 2)}` : '—'}</span>
            <span className="k">Rate component</span><span>{fmt.num(seis?.components.rate ?? null, 2)}</span>
            <span className="k">Energy component</span><span>{fmt.num(seis?.components.energy ?? null, 2)}</span>
            <span className="k">Shallowing component</span><span>{fmt.num(seis?.components.shallow ?? null, 2)}</span>
          </div>
          <p className="note">The index compares the last 7 days with the zone’s previous year. It is not an eruption probability. Official alerts come from PEVOLCA.</p>
        </section>

        <section>
          <h3>Sources</h3>
          {meta?.sources.map((s) => <div key={s} className="note">· {s}</div>)}
          <div className="note">· Terrain: {terrain?.attribution}</div>
        </section>
      </aside>
    </div>
  )
}

import { useEffect, useState } from 'react'
import { api, download, fmt, STATIC, type CatastropheReport, type Report } from '../api'
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
      {h != null && <div className="note">Day {h + 1}: {values[h] == null ? 'no data' : `${fmtv(values[h] as number)} ${unit}`}</div>}
    </div>
  )
}

function ProvenanceTag({ kind }: { kind: 'REAL' | 'ESTIMADO' }) {
  const isReal = kind === 'REAL'
  return (
    <span style={{
      display: 'inline-block',
      padding: '2px 7px',
      borderRadius: 4,
      fontSize: 10.5,
      fontWeight: 700,
      letterSpacing: '0.03em',
      background: isReal ? 'rgba(46, 107, 78, 0.14)' : 'rgba(180, 83, 47, 0.15)',
      color: isReal ? '#24583f' : '#9c3d1c',
      border: `1px solid ${isReal ? 'rgba(46, 107, 78, 0.35)' : 'rgba(180, 83, 47, 0.35)'}`,
    }}>
      {isReal ? 'REAL OBSERVED DATA' : 'VOLSCAN ESTIMATE'}
    </span>
  )
}

export default function Reports() {
  const [mode, setMode] = useState<'catastrophe' | 'monthly'>('catastrophe')
  const [catRep, setCatRep] = useState<CatastropheReport | null>(null)
  const [catErr, setCatErr] = useState<string | null>(null)
  const [months, setMonths] = useState<string[]>([])
  const [zones, setZones] = useState<{ key: string; name: string }[]>([])
  const [zone, setZone] = useState('la_palma')
  const [month, setMonth] = useState('2021-09')
  const [rep, setRep] = useState<Report | null>(null)
  const [ai, setAi] = useState<{ text: string | null; error?: string; model?: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const [expErr, setExpErr] = useState<string | null>(null)

  useEffect(() => {
    api.catastropheReport().then(setCatRep).catch((e) => setCatErr(String(e)))
    api.reportMonths().then((m) => {
      setMonths(m.months)
      setZones([...m.zones].sort((a, b) => ZONE_ORDER.indexOf(a.key) - ZONE_ORDER.indexOf(b.key)))
      if (!m.months.includes('2021-09') && m.months.length > 0) setMonth(m.months[0])
    })
  }, [])

  useEffect(() => {
    if (mode === 'monthly' && month) {
      setRep(null)
      setAi(null)
      api.report(zone, month).then(setRep).catch(() => setRep(null))
    }
  }, [mode, zone, month])

  const s = rep?.stats
  const delta = (a: number | null | undefined, b: number | null | undefined) => a == null || b == null ? '' : a > b ? '▲' : a < b ? '▼' : '='

  return (
    <div className="page report">
      <div className="report-bar" style={{ gap: 10, flexWrap: 'wrap' }}>
        <button className={`btn ${mode === 'catastrophe' ? 'primary' : ''}`} onClick={() => setMode('catastrophe')}>
          Disaster dossier · La Palma 2021 (Real vs Forecast)
        </button>
        <button className={`btn ${mode === 'monthly' ? 'primary' : ''}`} onClick={() => setMode('monthly')}>
          Monthly island bulletin (2011–2026 record)
        </button>
        <span style={{ flex: 1 }} />
        {mode === 'monthly' && (
          <>
            <select id="rep-zone" value={zone} onChange={(e) => setZone(e.target.value)}>{zones.map((z) => <option key={z.key} value={z.key}>{z.name}</option>)}</select>
            <select id="rep-month" value={month} onChange={(e) => setMonth(e.target.value)}>{months.map((m) => <option key={m} value={m}>{new Date(m + '-15T12:00:00Z').toLocaleDateString('en-GB', { month: 'long', year: 'numeric', timeZone: 'UTC' })}</option>)}</select>
            {!STATIC && <button className="btn" onClick={() => download(`/api/export/report/${zone}/${month}.pdf`, `volscan_report_${zone}_${month}.pdf`).catch((e) => setExpErr(String(e.message ?? e)))}>Download PDF</button>}
            {!STATIC && <button className="btn" onClick={() => download(`/api/export/report/${zone}/${month}.csv`, `volscan_report_${zone}_${month}.csv`).catch((e) => setExpErr(String(e.message ?? e)))}>CSV</button>}
          </>
        )}
        <button className="btn" onClick={() => window.print()}>Print</button>
        {expErr && <span className="note warn-text">{expErr}</span>}
      </div>

      {mode === 'catastrophe' && (
        <>
          {catErr && <div className="note">Could not load the disaster dossier: {catErr}</div>}
          {!catRep && !catErr && <div className="loading">Building the La Palma 2021 disaster dossier (crossing 63 CEMS maps, IGN earthquakes, rheology and tides)…</div>}
          {catRep && (
            <>
              <div className="report-head">
                <div className="kicker">Special eruption disaster report · Operational audit</div>
                <h2>{catRep.title}</h2>
                <div className="note">{catRep.subtitle}</div>
              </div>

              <div className="kpis kpis-page">
                <div className="kpi">
                  <div className="k"><ProvenanceTag kind="REAL" /> Final area and damage</div>
                  <div className="v">{fmt.int(catRep.summary_kpis.real_area_ha)}<small> ha</small></div>
                  <div className="s">{fmt.int(catRep.summary_kpis.real_buildings_destroyed)} buildings destroyed in {catRep.summary_kpis.eruption_days} days (Copernicus EMSR546)</div>
                </div>
                <div className="kpi">
                  <div className="k"><ProvenanceTag kind="ESTIMADO" /> 72 h forecast accuracy</div>
                  <div className="v">{catRep.summary_kpis.volscan_days_within_p10_p90}<small> / {catRep.summary_kpis.volscan_eval_days} d</small></div>
                  <div className="s">{Math.round((100 * catRep.summary_kpis.volscan_days_within_p10_p90) / catRep.summary_kpis.volscan_eval_days)} % of days inside the P10–P90 range (bias {fmt.num(catRep.summary_kpis.volscan_bias_pct)} %)</div>
                </div>
                <div className="kpi">
                  <div className="k"><ProvenanceTag kind="ESTIMADO" /> Synthetic experiment</div>
                  <div className="v">No external validation</div>
                  <div className="s">No operational lead time shown; scenes generated from CEMS</div>
                </div>
                <div className="kpi">
                  <div className="k"><ProvenanceTag kind="REAL" /> Onset and lunar tide</div>
                  <div className="v">{catRep.tides_crisis ? `${fmt.num(catRep.tides_crisis.onset_lunar_elong_deg, 0)}°` : '—'}</div>
                  <div className="s">19 Sep 14:10 UTC · eve of full moon (syzygy / spring tide)</div>
                </div>
              </div>

              <div className="card" style={{ marginTop: 14 }}>
                <h3>1. Where does each figure come from? (Strict split: real data vs VolScan estimate)</h3>
                <p className="note" style={{ marginBottom: 8 }}>
                  For an emergency room (PEVOLCA / 112) to trust the system, VolScan always keeps instrumental observations measured in the field apart from physical simulations and AI models:
                </p>
                <table className="places">
                  <thead>
                    <tr><th>Layer / Variable</th><th>Nature</th><th>Official source or engine</th><th>Role in VolScan</th></tr>
                  </thead>
                  <tbody>
                    {catRep.provenance.map((p, i) => (
                      <tr key={i}>
                        <td><b>{p.layer}</b></td>
                        <td><ProvenanceTag kind={p.kind} /></td>
                        <td>{p.source}</td>
                        <td className="note">{p.usage}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="card" style={{ marginTop: 14 }}>
                <h3>2. Flow type, lava rheology and evolution by phase (Reality vs Model)</h3>
                <p className="note" style={{ marginBottom: 10 }}>
                  The Tajogaite eruption produced basanite–tephrite lavas whose viscosity and morphology changed from thick clinkery <i>&apos;a&apos;ā</i> fronts to fast channels fed by lava tubes. This is how the physical engine responded in each phase:
                </p>
                <div className="cards">
                  {catRep.rheology_phases.map((ph, i) => (
                    <div key={i} className="card" style={{ background: 'var(--bg)' }}>
                      <div className="kicker">{ph.period}</div>
                      <h3 style={{ marginTop: 2 }}>{ph.phase}</h3>
                      <div className="kv" style={{ marginTop: 6 }}>
                        <span className="k">Lava type</span><span><b>{ph.lava_type}</b></span>
                        <span className="k"><ProvenanceTag kind="REAL" /> Real behaviour</span><span>{ph.rheology_real}</span>
                        <span className="k"><ProvenanceTag kind="ESTIMADO" /> VolScan model</span><span>{ph.rheology_model}</span>
                        <span className="k">Agreement</span><span><b>{ph.coincidence}</b></span>
                        {ph.stats.days > 0 && (
                          <>
                            <span className="k">P10–P90 coverage in phase</span>
                            <span><b>{ph.stats.within} / {ph.stats.days} days ({ph.stats.coverage_pct} %)</b> · mean forecast {ph.stats.pred_mean_72h} vs real {ph.stats.obs_mean_72h} bldg/72 h</span>
                          </>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="card" style={{ marginTop: 14 }}>
                <h3>3. Day by day on key dates: did VolScan’s estimate match what happened?</h3>
                <p className="note" style={{ marginBottom: 8 }}>
                  Timeline comparison between the real data recorded each day and the 72-hour forecast VolScan issued using only information available up to 23:59 UTC that day:
                </p>
                <div style={{ overflowX: 'auto' }}>
                  <table className="places">
                    <thead>
                      <tr>
                        <th>Date / Milestone</th>
                        <th><ProvenanceTag kind="REAL" /> Quakes 24h · CEMS flow · Destroyed</th>
                        <th><ProvenanceTag kind="ESTIMADO" /> VolScan (72 h) · SAM 3.1 · Sea</th>
                        <th>Lunar phase / Tide</th>
                        <th>Agreement verdict</th>
                      </tr>
                    </thead>
                    <tbody>
                      {catRep.timeline.map((row) => (
                        <tr key={row.date}>
                          <td>
                            <b>{fmt.date(row.date + 'T12:00:00Z')}</b>
                            <div className="note">{row.milestone}</div>
                          </td>
                          <td>
                            {row.real.quakes_24h} quakes (med. {fmt.num(row.real.depth_median_km)} km)<br />
                            {row.phase === 'eruptive' ? (
                              <>
                                CEMS area: <b>{fmt.num(row.real.cems_area_ha)} ha</b> · cum. {fmt.int(row.real.lost_buildings_cum)} bldg<br />
                                {row.real.obs_new_buildings_72h != null && <>New in +72 h (real): <b>{row.real.obs_new_buildings_72h} bldg</b></>}
                              </>
                            ) : <span className="note">No surface flow (pre-eruptive)</span>}
                          </td>
                          <td>
                            {row.phase === 'pre-eruptive' ? (
                              <>
                                Unrest index: <b>{fmt.num(row.estimated.unrest_index)}/10</b><br />
                                Shallow vent <b>{fmt.num(row.estimated.nearest_vent_km, 2)} km</b> from the real one<br />
                                30 d scenario: {row.estimated.pred_new_buildings_72h} bldg ({row.estimated.p10_p90?.join('–')})
                              </>
                            ) : (
                              <>
                                Forecast +72 h: <b>{row.estimated.pred_new_buildings_72h} bldg</b> (P10–P90: <b>{row.estimated.p10_p90?.[0]}–{row.estimated.p10_p90?.[1]}</b>)<br />
                                {row.estimated.sam3_area_ha != null && <>SAM 3.1: <b>{fmt.num(row.estimated.sam3_area_ha)} ha</b> (IoU {fmt.num(row.estimated.sam3_iou, 3)}) · </>}
                                Sea: {fmt.pct(row.estimated.sea_prob)}
                              </>
                            )}
                          </td>
                          <td>
                            <span className="note">{row.tide.regime}</span><br />
                            <span className="note">Semidiurnal tide: {fmt.num(row.tide.semidiurnal_deg, 0)}°</span>
                          </td>
                          <td><b>{row.verdict}</b></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {catRep.tides_crisis && (
                <div className="card" style={{ marginTop: 14 }}>
                  <h3>4. Earth tides, the lunar cycle and their link to the La Palma 2021 crisis</h3>
                  <p className="note" style={{ marginBottom: 10 }}>{catRep.tides_crisis.explanation}</p>
                  <div className="cards">
                    <div className="card" style={{ background: 'var(--bg)' }}>
                      <h4>Precursor swarm ({catRep.tides_crisis.swarm_precursor.period})</h4>
                      <div className="kv">
                        <span className="k">Recorded earthquakes (IGN)</span><span>{catRep.tides_crisis.swarm_precursor.n_raw} ({catRep.tides_crisis.swarm_precursor.n_declustered} after declustering)</span>
                        <span className="k">Lunar phase at onset (19 Sep)</span><span><b>{catRep.tides_crisis.onset_regime}</b></span>
                        <span className="k">Semidiurnal tide test (declustered)</span>
                        <span>
                          {catRep.tides_crisis.swarm_precursor.semidiurnal
                            ? `Excess C = ${fmt.num(catRep.tides_crisis.swarm_precursor.semidiurnal.c, 2)} · p = ${fmt.num(catRep.tides_crisis.swarm_precursor.semidiurnal.p_shift, 2)}`
                            : 'Sample too short after declustering'}
                        </span>
                      </div>
                    </div>
                    <div className="card" style={{ background: 'var(--bg)' }}>
                      <h4>Syn-eruptive seismicity ({catRep.tides_crisis.syn_eruptive.period})</h4>
                      <div className="kv">
                        <span className="k">Recorded earthquakes (IGN)</span><span>{catRep.tides_crisis.syn_eruptive.n_raw} ({catRep.tides_crisis.syn_eruptive.n_declustered} independent)</span>
                        <span className="k">Semidiurnal tide modulation (12.4 h)</span>
                        <span>
                          {catRep.tides_crisis.syn_eruptive.semidiurnal
                            ? `p = ${fmt.num(catRep.tides_crisis.syn_eruptive.semidiurnal.p_shift, 2)} (excess ${fmt.num(catRep.tides_crisis.syn_eruptive.semidiurnal.c, 2)})`
                            : '—'}
                        </span>
                        <span className="k">Fortnightly / syzygy modulation (14.8 d)</span>
                        <span>
                          {catRep.tides_crisis.syn_eruptive.fortnightly
                            ? `p = ${fmt.num(catRep.tides_crisis.syn_eruptive.fortnightly.p_shift, 2)} (excess ${fmt.num(catRep.tides_crisis.syn_eruptive.fortnightly.c, 2)})`
                            : '—'}
                        </span>
                      </div>
                    </div>
                  </div>
                  <details className="research" style={{ marginTop: 12 }}>
                    <summary>Open the interactive tide and lunar-phase explorer by zone (2011–2026)</summary>
                    <Solunar />
                  </details>
                </div>
              )}
            </>
          )}
        </>
      )}

      {mode === 'monthly' && (
        <>
          {!rep && <div className="loading">Preparing the monthly bulletin…</div>}
          {rep && s && <>
            <div className="report-head">
              <div className="kicker">Monthly volcano monitoring bulletin · <ProvenanceTag kind="REAL" /> + <ProvenanceTag kind="ESTIMADO" /></div>
              <h2>{rep.title}{rep.partial ? ' (current month)' : ''}</h2>
              <div className="note">Real observations: IGN (earthquakes), NGL (GNSS) and NASA OMPS (SO2) · Indicators computed by VolScan: Mc, b-value, 0–10 index and tide test</div>
            </div>
            <div className="card summary-card">
              <p>{ai?.text ?? rep.summary}</p>
              <div className="brief-meta">
                <span>{ai?.text ? `Drafted with AI (${ai.model}) from the report’s figures` : 'Deterministic automatic summary from the figures'}</span>
                {!ai?.text && <button className="btn" disabled={busy} onClick={() => { setBusy(true); api.reportRewrite(zone, month).then((r) => setAi({ text: r.text, error: r.error, model: r.model.model })).finally(() => setBusy(false)) }}>{busy ? 'Drafting…' : 'Draft with AI'}</button>}
              </div>
              {ai?.error && <div className="note">{ai.error}</div>}
            </div>
            <div className="kpis kpis-page">
              <div className="kpi"><div className="k"><ProvenanceTag kind="REAL" /> Earthquakes (IGN)</div><div className="v">{fmt.int(s.n)}</div><div className="s">{delta(s.n, rep.prev.n)} previous month {fmt.int(rep.prev.n)} · ×{fmt.num(rep.rate_ratio)} the annual rate</div></div>
              <div className="kpi"><div className="k"><ProvenanceTag kind="REAL" /> Maximum magnitude</div><div className="v">{fmt.num(s.max_mag)}</div><div className="s">{s.n_m3} M≥3 · {s.n_m2} M≥2 · {rep.felt} felt</div></div>
              <div className="kpi"><div className="k"><ProvenanceTag kind="REAL" /> Median depth</div><div className="v">{fmt.num(s.depth_median)}<small>km</small></div><div className="s">{delta(rep.prev.depth_median, s.depth_median)} previous {fmt.num(rep.prev.depth_median)} km · {s.shallow_lt5} shallower than 5 km</div></div>
              <div className="kpi"><div className="k"><ProvenanceTag kind="ESTIMADO" /> VolScan index (end)</div><div className="v">{rep.unrest_end.index == null ? '—' : fmt.num(rep.unrest_end.index)}<small>/ 10</small></div><div className="s">{rep.b ? `b-value ${fmt.num(rep.b.b, 2)} ± ${fmt.num(rep.b.sigma, 2)}` : 'b-value: too few data'}</div></div>
            </div>
            <div className="report-charts">
              <Bars values={rep.daily} label="Earthquakes per day (real IGN data)" unit="earthquakes" fmtv={(v) => String(Math.round(v))} />
              <Bars values={rep.daily_depth} label="Median depth per day (km, real IGN data)" unit="km" fmtv={(v) => v.toFixed(0)} />
            </div>
            <div className="cards">
              <div className="card">
                <h3>Most notable earthquakes <ProvenanceTag kind="REAL" /></h3>
                <table className="places">
                  <thead><tr><th>Date UTC</th><th>M</th><th>Depth</th><th>Int.</th></tr></thead>
                  <tbody>{rep.top_events.map((e) => <tr key={e.id} title={e.place}><td>{fmt.dateTime(e.t)}<div className="note">{e.place}</div></td><td>{fmt.num(e.mag)}</td><td>{e.depth == null ? '—' : `${fmt.num(e.depth)} km`}</td><td>{e.int_max ?? '—'}</td></tr>)}</tbody>
                </table>
              </div>
              <div className="card">
                <h3>Monthly comparison</h3>
                <table className="places">
                  <thead><tr><th>Indicator</th><th>This month</th><th>Previous</th></tr></thead>
                  <tbody>
                    <tr><td>Earthquakes</td><td>{fmt.int(s.n)}</td><td>{fmt.int(rep.prev.n)}</td></tr>
                    <tr><td>Maximum magnitude</td><td>{fmt.num(s.max_mag)}</td><td>{fmt.num(rep.prev.max_mag)}</td></tr>
                    <tr><td>M ≥ 3</td><td>{s.n_m3}</td><td>{rep.prev.n_m3}</td></tr>
                    <tr><td>Median depth (km)</td><td>{fmt.num(s.depth_median)}</td><td>{fmt.num(rep.prev.depth_median)}</td></tr>
                    <tr><td>Quakes &lt; 5 km deep</td><td>{s.shallow_lt5}</td><td>{rep.prev.shallow_lt5}</td></tr>
                    <tr><td>Daily mean (previous 12 months)</td><td colSpan={2}>{fmt.num(rep.baseline.rate_day, 2)} earthquakes/day</td></tr>
                  </tbody>
                </table>
                <h3 style={{ marginTop: 14 }}>Tides and Moon this month <ProvenanceTag kind="ESTIMADO" /></h3>
                {rep.tides ? <div className="stat">
                  <span className="k">Semidiurnal tide (excess at maximum)</span><span className={`sig ${rep.tides.semidiurnal.p_shift < 0.05 ? 'yes' : 'no'}`}>p = {rep.tides.semidiurnal.p_shift.toFixed(2)}</span>
                  <span className="k">Spring tides (excess at syzygy)</span><span className={`sig ${rep.tides.fortnightly.p_shift < 0.05 ? 'yes' : 'no'}`}>p = {rep.tides.fortnightly.p_shift.toFixed(2)}</span>
                </div> : <div className="note">Fewer than 30 earthquakes: not computed.</div>}
                <p className="note">Statistical test with a declustered catalogue and 100 time shifts.</p>
              </div>
            </div>
            <div className="cards" style={{ marginTop: 12 }}>
              <div className="card">
                <h3>Deformation (GNSS) <ProvenanceTag kind="REAL" /> {rep.deformation && <LevelChip level={rep.deformation.level} />}</h3>
                {rep.deformation ? <GnssTable stations={rep.deformation.stations} /> : <div className="note">No public GNSS stations with data for this month.</div>}
                <p className="note">Daily GPS series processed by the Nevada Geodetic Laboratory; anomaly computed against the 3-year trend.</p>
              </div>
              <div className="card">
                <h3>Gas (satellite SO2) <ProvenanceTag kind="REAL" /> {rep.so2 && <LevelChip level={rep.so2.days_detected ? 'SO2 detected' : 'no visible SO2'} />}</h3>
                {rep.so2 ? <div className="kv">
                  <span className="k">Days with data</span><span>{rep.so2.days}</span>
                  <span className="k">Days with SO2 ≥ {fmt.num(rep.so2.threshold_kt, 0)} kt</span><span>{rep.so2.days_detected}</span>
                  <span className="k">Daily maximum</span><span>{fmt.num(rep.so2.max_kt, 2)} kt</span>
                </div> : <div className="note">No SO2 data for this month (the daily series covers 2021 and the last two years).</div>}
                <p className="note">NASA OMPS, mid-troposphere, over the archipelago.</p>
              </div>
            </div>
            <p className="note" style={{ marginTop: 10 }}>Sources: {rep.sources.join(' · ')}. VolScan issues no alert levels; the official assessment belongs to PEVOLCA.</p>
          </>}
        </>
      )}
    </div>
  )
}

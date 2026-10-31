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
      {h != null && <div className="note">Día {h + 1}: {values[h] == null ? 'sin dato' : `${fmtv(values[h] as number)} ${unit}`}</div>}
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
      {isReal ? 'DATO REAL OBSERVADO' : 'ESTIMACIÓN VOLSCAN'}
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
          Dossier de Catástrofe · La Palma 2021 (Real vs Estimado)
        </button>
        <button className={`btn ${mode === 'monthly' ? 'primary' : ''}`} onClick={() => setMode('monthly')}>
          Boletín Mensual por Isla (Histórico 2011–2026)
        </button>
        <span style={{ flex: 1 }} />
        {mode === 'monthly' && (
          <>
            <select id="rep-zone" value={zone} onChange={(e) => setZone(e.target.value)}>{zones.map((z) => <option key={z.key} value={z.key}>{z.name}</option>)}</select>
            <select id="rep-month" value={month} onChange={(e) => setMonth(e.target.value)}>{months.map((m) => <option key={m} value={m}>{new Date(m + '-15T12:00:00Z').toLocaleDateString('es-ES', { month: 'long', year: 'numeric', timeZone: 'UTC' })}</option>)}</select>
            {!STATIC && <button className="btn" onClick={() => download(`/api/export/report/${zone}/${month}.pdf`, `volscan_informe_${zone}_${month}.pdf`).catch((e) => setExpErr(String(e.message ?? e)))}>Descargar PDF</button>}
            {!STATIC && <button className="btn" onClick={() => download(`/api/export/report/${zone}/${month}.csv`, `volscan_informe_${zone}_${month}.csv`).catch((e) => setExpErr(String(e.message ?? e)))}>CSV</button>}
          </>
        )}
        <button className="btn" onClick={() => window.print()}>Imprimir</button>
        {expErr && <span className="note warn-text">{expErr}</span>}
      </div>

      {mode === 'catastrophe' && (
        <>
          {catErr && <div className="note">No se pudo cargar el dossier de catástrofe: {catErr}</div>}
          {!catRep && !catErr && <div className="loading">Construyendo dossier de catástrofe de La Palma 2021 (cruzando 63 mapas CEMS, sismos IGN, reología y mareas)…</div>}
          {catRep && (
            <>
              <div className="report-head">
                <div className="kicker">Informe Especial de Catástrofe Eruptiva · Auditoría Operativa</div>
                <h2>{catRep.title}</h2>
                <div className="note">{catRep.subtitle}</div>
              </div>

              <div className="kpis kpis-page">
                <div className="kpi">
                  <div className="k"><ProvenanceTag kind="REAL" /> Superficie y daños finales</div>
                  <div className="v">{fmt.int(catRep.summary_kpis.real_area_ha)}<small> ha</small></div>
                  <div className="s">{fmt.int(catRep.summary_kpis.real_buildings_destroyed)} edificios destruidos en {catRep.summary_kpis.eruption_days} días (Copernicus EMSR546)</div>
                </div>
                <div className="kpi">
                  <div className="k"><ProvenanceTag kind="ESTIMADO" /> Acierto pronóstico 72 h</div>
                  <div className="v">{catRep.summary_kpis.volscan_days_within_p10_p90}<small> / {catRep.summary_kpis.volscan_eval_days} d</small></div>
                  <div className="s">{Math.round((100 * catRep.summary_kpis.volscan_days_within_p10_p90) / catRep.summary_kpis.volscan_eval_days)} % de días dentro del rango P10–P90 (sesgo {fmt.num(catRep.summary_kpis.volscan_bias_pct)} %)</div>
                </div>
                <div className="kpi">
                  <div className="k"><ProvenanceTag kind="ESTIMADO" /> Experimento sintético</div>
                  <div className="v">Sin validación externa</div>
                  <div className="s">Sin adelanto operativo demostrado; escenas generadas desde CEMS</div>
                </div>
                <div className="kpi">
                  <div className="k"><ProvenanceTag kind="REAL" /> Apertura y Marea Lunar</div>
                  <div className="v">{catRep.tides_crisis ? `${fmt.num(catRep.tides_crisis.onset_lunar_elong_deg, 0)}°` : '—'}</div>
                  <div className="s">19 sep 14:10 UTC · víspera de Luna llena (sizigia / marea viva)</div>
                </div>
              </div>

              <div className="card" style={{ marginTop: 14 }}>
                <h3>1. ¿De dónde sale cada dato? (Separación estricta Dato Real vs Estimación VolScan)</h3>
                <p className="note" style={{ marginBottom: 8 }}>
                  Para que una sala de emergencias (PEVOLCA / 112) confíe en el sistema, VolScan separa en todo momento las observaciones instrumentales medidas sobre el terreno de las simulaciones físicas y modelos de IA:
                </p>
                <table className="places">
                  <thead>
                    <tr><th>Capa / Variable</th><th>Naturaleza</th><th>Fuente oficial o motor</th><th>Función en VolScan</th></tr>
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
                <h3>2. Tipo de colada, reología de la lava y evolución por fases (Realidad vs Modelo)</h3>
                <p className="note" style={{ marginBottom: 10 }}>
                  La erupción de Tajogaite emitió lavas basaníticas-tefríticas cuya viscosidad y morfología cambiaron desde frentes escoriáceos <i>&apos;a&apos;ā</i> gruesos hasta canales rápidos alimentados por tubos volcánicos. Así respondió el motor físico en cada fase:
                </p>
                <div className="cards">
                  {catRep.rheology_phases.map((ph, i) => (
                    <div key={i} className="card" style={{ background: 'var(--bg)' }}>
                      <div className="kicker">{ph.period}</div>
                      <h3 style={{ marginTop: 2 }}>{ph.phase}</h3>
                      <div className="kv" style={{ marginTop: 6 }}>
                        <span className="k">Tipo de lava</span><span><b>{ph.lava_type}</b></span>
                        <span className="k"><ProvenanceTag kind="REAL" /> Comportamiento real</span><span>{ph.rheology_real}</span>
                        <span className="k"><ProvenanceTag kind="ESTIMADO" /> Modelo VolScan</span><span>{ph.rheology_model}</span>
                        <span className="k">Grado de coincidencia</span><span><b>{ph.coincidence}</b></span>
                        {ph.stats.days > 0 && (
                          <>
                            <span className="k">Cobertura P10–P90 en fase</span>
                            <span><b>{ph.stats.within} / {ph.stats.days} días ({ph.stats.coverage_pct} %)</b> · media prevista {ph.stats.pred_mean_72h} vs real {ph.stats.obs_mean_72h} edif./72 h</span>
                          </>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="card" style={{ marginTop: 14 }}>
                <h3>3. Evolución día a día en fechas clave: ¿Coincidió lo estimado por VolScan con lo que ocurrió?</h3>
                <p className="note" style={{ marginBottom: 8 }}>
                  Comparativa cronológica entre los datos reales registrados cada día y el pronóstico a 72 horas que emitía VolScan usando exclusivamente la información disponible hasta las 23:59 UTC de esa fecha:
                </p>
                <div style={{ overflowX: 'auto' }}>
                  <table className="places">
                    <thead>
                      <tr>
                        <th>Fecha / Hito</th>
                        <th><ProvenanceTag kind="REAL" /> Sismos 24h · Colada CEMS · Destruidos</th>
                        <th><ProvenanceTag kind="ESTIMADO" /> VolScan (72 h) · SAM 3.1 · Mar</th>
                        <th>Fase Lunar / Marea</th>
                        <th>Veredicto de coincidencia</th>
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
                            {row.real.quakes_24h} sismos (med. {fmt.num(row.real.depth_median_km)} km)<br />
                            {row.phase === 'eruptive' ? (
                              <>
                                Área CEMS: <b>{fmt.num(row.real.cems_area_ha)} ha</b> · acum. {fmt.int(row.real.lost_buildings_cum)} edif.<br />
                                {row.real.obs_new_buildings_72h != null && <>Nuevos en +72 h (real): <b>{row.real.obs_new_buildings_72h} edif.</b></>}
                              </>
                            ) : <span className="note">Sin colada en superficie (pre-eruptivo)</span>}
                          </td>
                          <td>
                            {row.phase === 'pre-eruptive' ? (
                              <>
                                Índice anomalía: <b>{fmt.num(row.estimated.unrest_index)}/10</b><br />
                                Boca somera a <b>{fmt.num(row.estimated.nearest_vent_km, 2)} km</b> de la real<br />
                                Escenario 30d: {row.estimated.pred_new_buildings_72h} edif. ({row.estimated.p10_p90?.join('–')})
                              </>
                            ) : (
                              <>
                                Pronóstico +72 h: <b>{row.estimated.pred_new_buildings_72h} edif.</b> (P10–P90: <b>{row.estimated.p10_p90?.[0]}–{row.estimated.p10_p90?.[1]}</b>)<br />
                                {row.estimated.sam3_area_ha != null && <>SAM 3.1: <b>{fmt.num(row.estimated.sam3_area_ha)} ha</b> (IoU {fmt.num(row.estimated.sam3_iou, 3)}) · </>}
                                Mar: {fmt.pct(row.estimated.sea_prob)}
                              </>
                            )}
                          </td>
                          <td>
                            <span className="note">{row.tide.regime}</span><br />
                            <span className="note">Marea semidiurna: {fmt.num(row.tide.semidiurnal_deg, 0)}°</span>
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
                  <h3>4. Mareas terrestres, ciclo lunar y su relación explícita con la crisis de La Palma 2021</h3>
                  <p className="note" style={{ marginBottom: 10 }}>{catRep.tides_crisis.explanation}</p>
                  <div className="cards">
                    <div className="card" style={{ background: 'var(--bg)' }}>
                      <h4>Enjambre precursor ({catRep.tides_crisis.swarm_precursor.period})</h4>
                      <div className="kv">
                        <span className="k">Sismos registrados (IGN)</span><span>{catRep.tides_crisis.swarm_precursor.n_raw} ({catRep.tides_crisis.swarm_precursor.n_declustered} tras desagrupar)</span>
                        <span className="k">Fase lunar en la apertura (19 sep)</span><span><b>{catRep.tides_crisis.onset_regime}</b></span>
                        <span className="k">Test marea semidiurna (desagrupado)</span>
                        <span>
                          {catRep.tides_crisis.swarm_precursor.semidiurnal
                            ? `Exceso C = ${fmt.num(catRep.tides_crisis.swarm_precursor.semidiurnal.c, 2)} · p = ${fmt.num(catRep.tides_crisis.swarm_precursor.semidiurnal.p_shift, 2)}`
                            : 'Muestra corta tras desagrupado'}
                        </span>
                      </div>
                    </div>
                    <div className="card" style={{ background: 'var(--bg)' }}>
                      <h4>Sismicidad sin-eruptiva ({catRep.tides_crisis.syn_eruptive.period})</h4>
                      <div className="kv">
                        <span className="k">Sismos registrados (IGN)</span><span>{catRep.tides_crisis.syn_eruptive.n_raw} ({catRep.tides_crisis.syn_eruptive.n_declustered} independientes)</span>
                        <span className="k">Modulación marea semidiurna (12,4 h)</span>
                        <span>
                          {catRep.tides_crisis.syn_eruptive.semidiurnal
                            ? `p = ${fmt.num(catRep.tides_crisis.syn_eruptive.semidiurnal.p_shift, 2)} (exceso ${fmt.num(catRep.tides_crisis.syn_eruptive.semidiurnal.c, 2)})`
                            : '—'}
                        </span>
                        <span className="k">Modulación quincenal / sizigia (14,8 d)</span>
                        <span>
                          {catRep.tides_crisis.syn_eruptive.fortnightly
                            ? `p = ${fmt.num(catRep.tides_crisis.syn_eruptive.fortnightly.p_shift, 2)} (exceso ${fmt.num(catRep.tides_crisis.syn_eruptive.fortnightly.c, 2)})`
                            : '—'}
                        </span>
                      </div>
                    </div>
                  </div>
                  <details className="research" style={{ marginTop: 12 }}>
                    <summary>Abrir explorador interactivo de mareas y fase lunar por zona (2011–2026)</summary>
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
          {!rep && <div className="loading">Preparando boletín mensual…</div>}
          {rep && s && <>
            <div className="report-head">
              <div className="kicker">Boletín mensual de vigilancia volcánica · <ProvenanceTag kind="REAL" /> + <ProvenanceTag kind="ESTIMADO" /></div>
              <h2>{rep.title}{rep.partial ? ' (mes en curso)' : ''}</h2>
              <div className="note">Observaciones reales: IGN (sismos), NGL (GNSS) y NASA OMPS (SO2) · Indicadores calculados por VolScan: Mc, b-value, índice 0–10 y test de mareas</div>
            </div>
            <div className="card summary-card">
              <p>{ai?.text ?? rep.summary}</p>
              <div className="brief-meta">
                <span>{ai?.text ? `Redactado con IA (${ai.model}) a partir de las cifras del informe` : 'Resumen automático determinista a partir de las cifras'}</span>
                {!ai?.text && <button className="btn" disabled={busy} onClick={() => { setBusy(true); api.reportRewrite(zone, month).then((r) => setAi({ text: r.text, error: r.error, model: r.model.model })).finally(() => setBusy(false)) }}>{busy ? 'Redactando…' : 'Redactar con IA'}</button>}
              </div>
              {ai?.error && <div className="note">{ai.error}</div>}
            </div>
            <div className="kpis kpis-page">
              <div className="kpi"><div className="k"><ProvenanceTag kind="REAL" /> Terremotos (IGN)</div><div className="v">{fmt.int(s.n)}</div><div className="s">{delta(s.n, rep.prev.n)} mes anterior {fmt.int(rep.prev.n)} · ×{fmt.num(rep.rate_ratio)} la tasa anual</div></div>
              <div className="kpi"><div className="k"><ProvenanceTag kind="REAL" /> Magnitud máxima</div><div className="v">{fmt.num(s.max_mag)}</div><div className="s">{s.n_m3} de M≥3 · {s.n_m2} de M≥2 · {rep.felt} sentidos</div></div>
              <div className="kpi"><div className="k"><ProvenanceTag kind="REAL" /> Profundidad mediana</div><div className="v">{fmt.num(s.depth_median)}<small>km</small></div><div className="s">{delta(rep.prev.depth_median, s.depth_median)} anterior {fmt.num(rep.prev.depth_median)} km · {s.shallow_lt5} a menos de 5 km</div></div>
              <div className="kpi"><div className="k"><ProvenanceTag kind="ESTIMADO" /> Índice VolScan (fin)</div><div className="v">{rep.unrest_end.index == null ? '—' : fmt.num(rep.unrest_end.index)}<small>/ 10</small></div><div className="s">{rep.b ? `b-value ${fmt.num(rep.b.b, 2)} ± ${fmt.num(rep.b.sigma, 2)}` : 'b-value: pocos datos'}</div></div>
            </div>
            <div className="report-charts">
              <Bars values={rep.daily} label="Terremotos por día (dato real IGN)" unit="terremotos" fmtv={(v) => String(Math.round(v))} />
              <Bars values={rep.daily_depth} label="Profundidad mediana por día (km, dato real IGN)" unit="km" fmtv={(v) => v.toFixed(0)} />
            </div>
            <div className="cards">
              <div className="card">
                <h3>Terremotos más destacados <ProvenanceTag kind="REAL" /></h3>
                <table className="places">
                  <thead><tr><th>Fecha UTC</th><th>M</th><th>Prof.</th><th>Int.</th></tr></thead>
                  <tbody>{rep.top_events.map((e) => <tr key={e.id} title={e.place}><td>{fmt.dateTime(e.t)}<div className="note">{e.place}</div></td><td>{fmt.num(e.mag)}</td><td>{e.depth == null ? '—' : `${fmt.num(e.depth)} km`}</td><td>{e.int_max ?? '—'}</td></tr>)}</tbody>
                </table>
              </div>
              <div className="card">
                <h3>Comparación mensual</h3>
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
                <h3 style={{ marginTop: 14 }}>Mareas y Luna este mes <ProvenanceTag kind="ESTIMADO" /></h3>
                {rep.tides ? <div className="stat">
                  <span className="k">Marea semidiurna (exceso en máximo)</span><span className={`sig ${rep.tides.semidiurnal.p_shift < 0.05 ? 'yes' : 'no'}`}>p = {rep.tides.semidiurnal.p_shift.toFixed(2).replace('.', ',')}</span>
                  <span className="k">Mareas vivas (exceso en sizigia)</span><span className={`sig ${rep.tides.fortnightly.p_shift < 0.05 ? 'yes' : 'no'}`}>p = {rep.tides.fortnightly.p_shift.toFixed(2).replace('.', ',')}</span>
                </div> : <div className="note">Menos de 30 terremotos: no se calcula.</div>}
                <p className="note">Prueba estadística con catálogo desagrupado y 100 desplazamientos temporales.</p>
              </div>
            </div>
            <div className="cards" style={{ marginTop: 12 }}>
              <div className="card">
                <h3>Deformación (GNSS) <ProvenanceTag kind="REAL" /> {rep.deformation && <LevelChip level={rep.deformation.level} />}</h3>
                {rep.deformation ? <GnssTable stations={rep.deformation.stations} /> : <div className="note">Sin estaciones GNSS públicas con datos para este mes.</div>}
                <p className="note">Series GPS diarias procesadas por el Nevada Geodetic Laboratory; anomalía calculada frente a la tendencia de 3 años.</p>
              </div>
              <div className="card">
                <h3>Gases (SO2 por satélite) <ProvenanceTag kind="REAL" /> {rep.so2 && <LevelChip level={rep.so2.days_detected ? 'SO2 detectado' : 'sin SO2 visible'} />}</h3>
                {rep.so2 ? <div className="kv">
                  <span className="k">Días con dato</span><span>{rep.so2.days}</span>
                  <span className="k">Días con SO2 ≥ {fmt.num(rep.so2.threshold_kt, 0)} kt</span><span>{rep.so2.days_detected}</span>
                  <span className="k">Máximo diario</span><span>{fmt.num(rep.so2.max_kt, 2)} kt</span>
                </div> : <div className="note">Sin datos de SO2 para este mes (la serie diaria cubre 2021 y los dos últimos años).</div>}
                <p className="note">NASA OMPS, troposfera media, sobre el archipiélago.</p>
              </div>
            </div>
            <p className="note" style={{ marginTop: 10 }}>Fuentes: {rep.sources.join(' · ')}. VolScan no emite niveles de alerta; la valoración oficial corresponde al PEVOLCA.</p>
          </>}
        </>
      )}
    </div>
  )
}

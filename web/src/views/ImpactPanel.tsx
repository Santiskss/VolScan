import { fmt, type ImpactDay } from '../api'
import Exports from './Exports'

const r0 = (v: number | null | undefined) => (v == null ? '—' : Math.round(v).toLocaleString('en-GB'))

/** "Countdown to impact": what will be lost, with what probability and when. Side panel of the atlas. */
export default function ImpactPanel({ imp, loading }: { imp: ImpactDay | null; loading: boolean }) {
  if (loading && !imp) return <section><h3>Expected impact</h3><div className="loading">Computing impact…</div></section>
  if (!imp) return null
  if (imp.phase === 'pre-eruptive') {
    const sc = imp.scenario
    return (
      <section className="impact">
        <h3>Anticipated scenario · before the vent opens</h3>
        {!sc ? <div className="note">Not enough shallow seismicity yet to place likely vents.</div> : <>
          <p className="note" style={{ marginTop: 0 }}>{sc.note}</p>
          <div className="impact-grid">
            <div><div className="k">Candidate vents</div><div className="v">{sc.n_vent_events}</div><div className="s">earthquakes ≤ {fmt.num(sc.shallow_depth_max_km)} km</div></div>
            <div><div className="k">Buildings exposed</div><div className="v">{r0(sc.buildings.expected)}</div><div className="s">P10–P90 {r0(sc.buildings.p10_p90[0])}–{r0(sc.buildings.p10_p90[1])}</div></div>
          </div>
          <table className="places">
            <thead><tr><th>Exposed neighbourhood</th><th>P</th></tr></thead>
            <tbody>{sc.places.slice(0, 8).map((p) => <tr key={p.name}><td>{p.name}</td><td><span className="pbar" style={{ width: Math.max(2, p.p * 120) }} />{fmt.pct(p.p)}</td></tr>)}</tbody>
          </table>
          <div className="note" style={{ marginTop: 6 }}>Validation: the real vent opened {fmt.num(sc.nearest_candidate_to_real_vent_km)} km from the nearest candidate.</div>
        </>}
      </section>
    )
  }
  const c = imp.constrained
  return (
    <section className="impact">
      <h3>Expected impact · next 72 h</h3>
      {!c && <div className="note" style={{ marginTop: 0 }}>No Copernicus map delivered yet: impact comes only from the flow ensemble, not yet fitted to observed growth. Buildings: {r0(imp.buildings?.expected)} (P10–P90 {r0(imp.buildings?.p10_p90[0])}–{r0(imp.buildings?.p10_p90[1])}).</div>}
      {c && <div className="impact-grid">
        <div><div className="k">Buildings</div><div className="v">{r0(c?.buildings.central)}</div><div className="s">{r0(c?.buildings.low)}–{r0(c?.buildings.high)} · already lost {r0(imp.already_lost?.buildings)}</div></div>
        <div><div className="k">Roads</div><div className="v">{fmt.num(c?.road_km.central)}<small> km</small></div><div className="s">{fmt.num(c?.road_km.low)}–{fmt.num(c?.road_km.high)} · already cut {fmt.num(imp.already_lost?.road_km)}</div></div>
      </div>}
      {c && <div className="note" style={{ marginTop: 4 }}>Latest known Copernicus map: {fmt.num(c.map_age_h)} h old (assumed to arrive {fmt.num(imp.map_delay_h)} h after the image).{c.interval ? ` Range calibrated on the real error of ${c.interval.n_past} earlier forecasts.` : ' Range: spread of the recent growth rate (no history to calibrate it yet).'}</div>}
      {imp.watch && <>
        <div className="subh">Watch list · buildings still standing</div>
        <div className="impact-grid">
          <div><div className="k">Reachable in 72 h</div><div className="v">{r0(imp.watch.high)}</div><div className="s">some ensemble member reaches them</div></div>
          <div><div className="k">Hemmed in by the flow</div><div className="v" style={{ color: '#3f5fb0' }}>{r0(imp.watch.pocket)}</div><div className="s">where lateral growth usually goes</div></div>
        </div>
      </>}
      {imp.truth_after && <div className="truth">What happened (Copernicus, {fmt.dateTime(imp.truth_after.at)}): <b>{r0(imp.truth_after.new_buildings)} buildings</b> and {fmt.num(imp.truth_after.new_road_km)} km of new road lost</div>}
      {imp.isolation && imp.isolation.length > 0 && <>
        <div className="subh">Neighbourhoods</div>
        <table className="places">
          <thead><tr><th>Neighbourhood</th><th>Reached</th><th>Isolated</th></tr></thead>
          <tbody>{imp.isolation.slice(0, 7).map((i) => <tr key={i.name}><td>{i.name}</td><td>{fmt.pct(i.p_reached)}</td><td className={i.p_isolated >= 0.2 ? 'warn' : ''}>{fmt.pct(i.p_isolated)}</td></tr>)}</tbody>
        </table>
      </>}
      {imp.facilities && imp.facilities.length > 0 && <>
        <div className="subh">Services</div>
        <table className="places">
          <thead><tr><th>Service</th><th>P</th><th>P50</th></tr></thead>
          <tbody>{imp.facilities.slice(0, 7).map((f, k) => <tr key={k}><td>{f.kind}{f.name !== f.kind ? <span className="note"> · {f.name}</span> : null}</td><td>{f.already_lost ? <span className="reached">LOST</span> : fmt.pct(f.p)}</td><td>{f.already_lost ? '' : fmt.hours(f.eta_h[1] != null ? f.eta_h[1] : null)}</td></tr>)}</tbody>
        </table>
        {imp.ponds && <div className="note">Irrigation ponds: {imp.ponds.already_lost} lost, {fmt.num(imp.ponds.expected)} more expected.</div>}
      </>}
      <p className="note">{imp.method}</p>
      <Exports items={[
        { label: 'PDF report', url: `/api/export/impact/lapalma2021/${imp.date}.pdf`, file: `volscan_impact_${imp.date}.pdf` },
        { label: 'CSV', url: `/api/export/impact/lapalma2021/${imp.date}.csv`, file: `volscan_impact_${imp.date}.csv` },
        ...(c ? [
          { label: 'CAP alert (112)', url: `/api/cap/lapalma2021/${imp.date}.xml`, file: `volscan_cap_${imp.date}.xml`, hint: 'CAP 1.2, status “Exercise”: simulation, not an alert' },
          { label: 'GeoJSON', url: `/ogc/collections/lapalma2021-colada-72h/items?fecha=${imp.date}`, file: `volscan_flow72h_${imp.date}.geojson`, hint: 'Also as OGC API Features at /ogc' },
        ] : []),
      ]} />
    </section>
  )
}

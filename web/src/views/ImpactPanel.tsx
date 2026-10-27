import { fmt, type ImpactDay } from '../api'
import Exports from './Exports'

const r0 = (v: number | null | undefined) => (v == null ? '—' : Math.round(v).toLocaleString('es-ES'))

/** "Countdown to impact": what will be lost, with what probability and when. Side panel of the atlas. */
export default function ImpactPanel({ imp, loading }: { imp: ImpactDay | null; loading: boolean }) {
  if (loading && !imp) return <section><h3>Impacto previsto</h3><div className="loading">Calculando impacto…</div></section>
  if (!imp) return null
  if (imp.phase === 'pre-eruptive') {
    const sc = imp.scenario
    return (
      <section className="impact">
        <h3>Escenario anticipado · antes de la boca</h3>
        {!sc ? <div className="note">Aún no hay sismicidad somera suficiente para situar bocas probables.</div> : <>
          <p className="note" style={{ marginTop: 0 }}>{sc.note}</p>
          <div className="impact-grid">
            <div><div className="k">Bocas candidatas</div><div className="v">{sc.n_vent_events}</div><div className="s">sismos de ≤ {fmt.num(sc.shallow_depth_max_km)} km</div></div>
            <div><div className="k">Edificios expuestos</div><div className="v">{r0(sc.buildings.expected)}</div><div className="s">P10–P90 {r0(sc.buildings.p10_p90[0])}–{r0(sc.buildings.p10_p90[1])}</div></div>
          </div>
          <table className="places">
            <thead><tr><th>Núcleo expuesto</th><th>P</th></tr></thead>
            <tbody>{sc.places.slice(0, 8).map((p) => <tr key={p.name}><td>{p.name}</td><td><span className="pbar" style={{ width: Math.max(2, p.p * 120) }} />{fmt.pct(p.p)}</td></tr>)}</tbody>
          </table>
          <div className="note" style={{ marginTop: 6 }}>Validación: la boca real abrió a {fmt.num(sc.nearest_candidate_to_real_vent_km)} km de la candidata más cercana.</div>
        </>}
      </section>
    )
  }
  const c = imp.constrained
  return (
    <section className="impact">
      <h3>Impacto previsto · próximas 72 h</h3>
      {!c && <div className="note" style={{ marginTop: 0 }}>Aún no se ha entregado ningún mapa de Copernicus: el impacto sale solo del conjunto de coladas, sin ajustar al crecimiento observado. Edificios: {r0(imp.buildings?.expected)} (P10–P90 {r0(imp.buildings?.p10_p90[0])}–{r0(imp.buildings?.p10_p90[1])}).</div>}
      {c && <div className="impact-grid">
        <div><div className="k">Edificios</div><div className="v">{r0(c?.buildings.central)}</div><div className="s">{r0(c?.buildings.low)}–{r0(c?.buildings.high)} · ya perdidos {r0(imp.already_lost?.buildings)}</div></div>
        <div><div className="k">Carreteras</div><div className="v">{fmt.num(c?.road_km.central)}<small> km</small></div><div className="s">{fmt.num(c?.road_km.low)}–{fmt.num(c?.road_km.high)} · ya cortados {fmt.num(imp.already_lost?.road_km)}</div></div>
      </div>}
      {c && <div className="note" style={{ marginTop: 4 }}>Último mapa de Copernicus conocido: de hace {fmt.num(c.map_age_h)} h (se cuenta que llega {fmt.num(imp.map_delay_h)} h después de la imagen).{c.interval ? ` Rango calibrado con el error real de ${c.interval.n_past} pronósticos anteriores.` : ' Rango: dispersión del ritmo de crecimiento reciente (aún sin historial para calibrarlo).'}</div>}
      {imp.watch && <>
        <div className="subh">Lista de vigilancia · edificios en pie</div>
        <div className="impact-grid">
          <div><div className="k">Alcanzables en 72 h</div><div className="v">{r0(imp.watch.high)}</div><div className="s">algún miembro del conjunto llega</div></div>
          <div><div className="k">Cercados por la colada</div><div className="v" style={{ color: '#3f5fb0' }}>{r0(imp.watch.pocket)}</div><div className="s">donde suele ir el crecimiento lateral</div></div>
        </div>
      </>}
      {imp.truth_after && <div className="truth">Lo que pasó (Copernicus, {fmt.dateTime(imp.truth_after.at)}): <b>{r0(imp.truth_after.new_buildings)} edificios</b> y {fmt.num(imp.truth_after.new_road_km)} km nuevos</div>}
      {imp.isolation && imp.isolation.length > 0 && <>
        <div className="subh">Barrios</div>
        <table className="places">
          <thead><tr><th>Núcleo</th><th>Alcanzado</th><th>Aislado</th></tr></thead>
          <tbody>{imp.isolation.slice(0, 7).map((i) => <tr key={i.name}><td>{i.name}</td><td>{fmt.pct(i.p_reached)}</td><td className={i.p_isolated >= 0.2 ? 'warn' : ''}>{fmt.pct(i.p_isolated)}</td></tr>)}</tbody>
        </table>
      </>}
      {imp.facilities && imp.facilities.length > 0 && <>
        <div className="subh">Servicios</div>
        <table className="places">
          <thead><tr><th>Servicio</th><th>P</th><th>P50</th></tr></thead>
          <tbody>{imp.facilities.slice(0, 7).map((f, k) => <tr key={k}><td>{f.kind}{f.name !== f.kind ? <span className="note"> · {f.name}</span> : null}</td><td>{f.already_lost ? <span className="reached">PERDIDO</span> : fmt.pct(f.p)}</td><td>{f.already_lost ? '' : fmt.hours(f.eta_h[1] != null ? f.eta_h[1] : null)}</td></tr>)}</tbody>
        </table>
        {imp.ponds && <div className="note">Estanques de riego: {imp.ponds.already_lost} perdidos, {fmt.num(imp.ponds.expected)} más esperados.</div>}
      </>}
      <p className="note">{imp.method}</p>
      <Exports items={[
        { label: 'Parte PDF', url: `/api/export/impact/lapalma2021/${imp.date}.pdf`, file: `volscan_impacto_${imp.date}.pdf` },
        { label: 'CSV', url: `/api/export/impact/lapalma2021/${imp.date}.csv`, file: `volscan_impacto_${imp.date}.csv` },
        { label: 'Aviso CAP (112)', url: `/api/cap/lapalma2021/${imp.date}.xml`, file: `volscan_cap_${imp.date}.xml`, hint: 'CAP 1.2, estado «Exercise»: simulación, no alerta' },
        { label: 'GeoJSON', url: `/ogc/collections/lapalma2021-colada-72h/items?fecha=${imp.date}`, file: `volscan_colada72h_${imp.date}.geojson`, hint: 'También como OGC API Features en /ogc' },
      ]} />
    </section>
  )
}

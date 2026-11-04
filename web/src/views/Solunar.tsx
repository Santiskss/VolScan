import { useEffect, useState } from 'react'
import { api, fmt } from '../api'

const ZONES = [['la_palma', 'La Palma'], ['el_hierro', 'El Hierro'], ['tenerife', 'Tenerife'], ['gran_canaria', 'Gran Canaria'], ['lanzarote_fuerteventura', 'Lanzarote · Fuerteventura']]

function Rose({ hist, label }: { hist: number[]; label: string }) {
  const max = Math.max(...hist, 1), R = 80, c = 95
  const wedges = hist.map((v, i) => {
    const a0 = (i / 12) * 2 * Math.PI - Math.PI / 2, a1 = ((i + 1) / 12) * 2 * Math.PI - Math.PI / 2
    const r = 14 + (v / max) * (R - 14)
    return `M${c},${c} L${c + r * Math.cos(a0)},${c + r * Math.sin(a0)} A${r},${r} 0 0 1 ${c + r * Math.cos(a1)},${c + r * Math.sin(a1)} Z`
  })
  return (
    <svg width={190} height={200} role="img" aria-label={label}>
      <circle cx={c} cy={c} r={R} fill="none" stroke="var(--line)" />
      <circle cx={c} cy={c} r={R / 2} fill="none" stroke="var(--line)" strokeDasharray="2 3" />
      {wedges.map((d, i) => <path key={i} d={d} fill="var(--accent)" opacity={0.75} />)}
      <text x={c} y={10} textAnchor="middle" fontSize="10" fill="var(--muted)">0° · maximum</text>
      <text x={c} y={c * 2 + 2} textAnchor="middle" fontSize="10" fill="var(--muted)">180° · minimum</text>
    </svg>
  )
}

function Verdict({ p }: { p: number | null }) {
  if (p == null || Number.isNaN(p)) return <span className="sig no">n/d</span>
  return p < 0.05 ? <span className="sig yes">p = {p.toFixed(3)}</span> : <span className="sig no">p = {p.toFixed(2)}</span>
}

export default function Solunar() {
  const [zone, setZone] = useState('la_palma')
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  useEffect(() => { setLoading(true); setData(null); api.solunar(zone).then(setData).finally(() => setLoading(false)) }, [zone])
  const moon = data?.now?.lunar_elongation as number | undefined
  const moonName = moon == null ? '—' : moon < 22 || moon > 338 ? 'New moon' : moon < 158 ? 'Waxing' : moon < 202 ? 'Full moon' : 'Waning'
  return (
    <div className="page">
      <h2>Tides, Moon and earthquakes</h2>
      <p className="lead">Earth tides deform the crust by tens of centimetres a day. For every IGN earthquake since 2011, VolScan computes where in the tide (~12.4 h cycle) and the lunar cycle (spring and neap tides) it happened. That measures whether there is a correlation instead of assuming one. Swarms make classic tests give false positives, so the verdict rests on a robust test: a declustered catalogue and 200 time shifts of the catalogue itself.</p>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 16 }}>
        <select value={zone} onChange={(e) => setZone(e.target.value)}>{ZONES.map(([k, n]) => <option key={k} value={k}>{n}</option>)}</select>
        {loading && <span className="loading">Computing phases for the whole catalogue…</span>}
        {data && <span className="note">{fmt.int(data.n)} earthquakes analysed · now: tide at phase {fmt.int(data.now.tidal_phase)}°, {moonName} ({fmt.int(moon)}°)</span>}
      </div>
      {data && (
        <div className="cards">
          {(['semidiurnal', 'fortnightly'] as const).map((k) => data[k] && (
            <div className="card" key={k}>
              <h3>{k === 'semidiurnal' ? 'Semidiurnal tide (12.4 h)' : 'Spring and neap tides (14.8 d)'}</h3>
              <div style={{ display: 'grid', gridTemplateColumns: '190px 1fr', gap: 12, alignItems: 'center' }}>
                <Rose hist={data[k].hist12} label={k} />
                <div className="stat">
                  <span className="k">Schuster, all earthquakes</span><Verdict p={data[k].raw.p} />
                  <span className="k">Schuster, declustered (n={data[k].declustered.n})</span><Verdict p={data[k].declustered.p} />
                  <span className="k"><b>Robust test</b> (excess at phase 0)</span><Verdict p={data[k].shift_test.p_shift} />
                  <span className="k">Alignment C</span><span>{fmt.num(data[k].shift_test.c, 3)}</span>
                </div>
              </div>
              <p className="note">{data[k].shift_test.p_shift < 0.05
                ? 'The robust test finds an excess of earthquakes near the maximum. It is a correlation to watch, not a cause.'
                : data[k].raw.p < 0.05
                  ? 'The classic test is significant, but it vanishes once swarms are controlled for: an apparent correlation, not a real one.'
                  : 'No detectable modulation with current data.'}</p>
            </div>
          ))}
        </div>
      )}
      <p className="note" style={{ marginTop: 16 }}>Low-precision ephemerides (Astronomical Almanac): ~0.3° for the Moon, checked against published phases. Degree-2 tidal potential at each zone’s centroid. The record grows every day with the IGN catalogue.</p>
    </div>
  )
}

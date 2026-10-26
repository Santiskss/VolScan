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
      <text x={c} y={10} textAnchor="middle" fontSize="10" fill="var(--muted)">0° · máximo</text>
      <text x={c} y={c * 2 + 2} textAnchor="middle" fontSize="10" fill="var(--muted)">180° · mínimo</text>
    </svg>
  )
}

function Verdict({ p }: { p: number | null }) {
  if (p == null || Number.isNaN(p)) return <span className="sig no">n/d</span>
  return p < 0.05 ? <span className="sig yes">p = {p.toFixed(3).replace('.', ',')}</span> : <span className="sig no">p = {p.toFixed(2).replace('.', ',')}</span>
}

export default function Solunar() {
  const [zone, setZone] = useState('la_palma')
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  useEffect(() => { setLoading(true); setData(null); api.solunar(zone).then(setData).finally(() => setLoading(false)) }, [zone])
  const moon = data?.now?.lunar_elongation as number | undefined
  const moonName = moon == null ? '—' : moon < 22 || moon > 338 ? 'Luna nueva' : moon < 158 ? 'Creciente' : moon < 202 ? 'Luna llena' : 'Menguante'
  return (
    <div className="page">
      <h2>Mareas, Luna y sismos</h2>
      <p className="lead">Las mareas terrestres deforman la corteza decenas de centímetros al día. VolScan calcula, para cada sismo del IGN desde 2011, en qué punto de la marea (ciclo de ~12,4 h) y de la Luna (mareas vivas y muertas) ocurrió. Así se mide si hay correlación, sin darla por hecha. Los enjambres hacen que los tests clásicos den «positivo» falso, así que el veredicto se basa en una prueba robusta: catálogo desagrupado y 200 desplazamientos temporales del propio catálogo.</p>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 16 }}>
        <select value={zone} onChange={(e) => setZone(e.target.value)}>{ZONES.map(([k, n]) => <option key={k} value={k}>{n}</option>)}</select>
        {loading && <span className="loading">Calculando fases para todo el catálogo…</span>}
        {data && <span className="note">{fmt.int(data.n)} sismos analizados · ahora: marea en fase {fmt.int(data.now.tidal_phase)}°, {moonName} ({fmt.int(moon)}°)</span>}
      </div>
      {data && (
        <div className="cards">
          {(['semidiurnal', 'fortnightly'] as const).map((k) => data[k] && (
            <div className="card" key={k}>
              <h3>{k === 'semidiurnal' ? 'Marea semidiurna (12,4 h)' : 'Mareas vivas y muertas (14,8 d)'}</h3>
              <div style={{ display: 'grid', gridTemplateColumns: '190px 1fr', gap: 12, alignItems: 'center' }}>
                <Rose hist={data[k].hist12} label={k} />
                <div className="stat">
                  <span className="k">Schuster, todos los sismos</span><Verdict p={data[k].raw.p} />
                  <span className="k">Schuster, desagrupado (n={data[k].declustered.n})</span><Verdict p={data[k].declustered.p} />
                  <span className="k"><b>Prueba robusta</b> (exceso en fase 0)</span><Verdict p={data[k].shift_test.p_shift} />
                  <span className="k">Alineación C</span><span>{fmt.num(data[k].shift_test.c, 3)}</span>
                </div>
              </div>
              <p className="note">{data[k].shift_test.p_shift < 0.05
                ? 'La prueba robusta detecta un exceso de sismos cerca del máximo. Es una correlación que hay que vigilar, no una causa.'
                : data[k].raw.p < 0.05
                  ? 'El test clásico sale significativo, pero desaparece al controlar los enjambres: correlación aparente, no real.'
                  : 'Sin modulación detectable con los datos actuales.'}</p>
            </div>
          ))}
        </div>
      )}
      <p className="note" style={{ marginTop: 16 }}>Efemérides de baja precisión (Astronomical Almanac): ~0,3° para la Luna, validadas con fases publicadas. Potencial de marea de grado 2 en el centroide de cada zona. El historial crece cada día con el catálogo del IGN.</p>
    </div>
  )
}

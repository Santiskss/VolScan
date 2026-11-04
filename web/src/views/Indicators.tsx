import { fmt } from '../api'

export type GnssStation = {
  code: string; place: string; lat: number; lon: number; last: string; evaluated_at?: string; level: string; reason?: string
  anom_e_mm?: number; anom_n_mm?: number; anom_u_mm?: number; vel_u_mm_yr?: number; z_h?: number; z_u?: number
}
export type So2Status = { level: string; max_kt: number | null; max_date?: string; last: string | null; window_days?: number; threshold_kt?: number; citation?: string }

const LEVEL_CLASS: Record<string, string> = {
  'normal': 'ok', 'a vigilar': 'warn', 'anómala': 'bad', 'SO2 detectado': 'bad', 'sin SO2 visible': 'ok',
  'watch': 'warn', 'anomalous': 'bad', 'SO2 detected': 'bad', 'no visible SO2': 'ok',
}

const LEVEL_EN: Record<string, string> = {
  'normal': 'normal', 'a vigilar': 'watch', 'anómala': 'anomalous', 'SO2 detectado': 'SO2 detected', 'sin SO2 visible': 'no visible SO2', 'sin datos': 'no data',
}

export function LevelChip({ level }: { level: string }) {
  return <span className={`lvl ${LEVEL_CLASS[level] ?? 'na'}`}>{LEVEL_EN[level] ?? level}</span>
}

/** Daily SO2 (kt) as thin bars; the dashed line is the detection threshold. */
export function So2Bars({ series, threshold = 1, height = 46 }: { series: { date: string; kt: number }[]; threshold?: number; height?: number }) {
  if (!series.length) return <div className="note">No SO2 data for this period.</div>
  const W = 300, H = height
  const max = Math.max(threshold * 3, ...series.map((s) => s.kt))
  const bw = W / series.length
  const y = (v: number) => H - (v / max) * (H - 2)
  const last = series[series.length - 1]
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: H, display: 'block' }} role="img" aria-label="Daily satellite SO2">
        {series.map((s, i) => <rect key={s.date} x={i * bw} y={y(s.kt)} width={Math.max(0.8, bw - 0.4)} height={H - y(s.kt)} fill={s.kt >= threshold ? 'var(--accent)' : 'var(--muted)'} />)}
        <line x1={0} x2={W} y1={y(threshold)} y2={y(threshold)} stroke="var(--text)" strokeDasharray="3 3" strokeWidth={0.8} opacity={0.6} />
      </svg>
      <div className="note">{series[0].date} → {last.date} · last day {fmt.num(last.kt, 1)} kt · line = threshold {fmt.num(threshold, 0)} kt</div>
    </div>
  )
}

export function GnssTable({ stations }: { stations: GnssStation[] }) {
  const shown = stations.filter((s) => s.level !== 'sin datos' && s.level !== 'no data')
  if (!shown.length) return <div className="note">No public GNSS station with data in this zone.</div>
  return (
    <table className="places">
      <thead><tr><th>Station</th><th>Vertical</th><th>z (h / v)</th><th>Level</th></tr></thead>
      <tbody>{shown.map((s) => (
        <tr key={s.code} title={`Data to ${s.evaluated_at ?? s.last} · background vertical velocity ${fmt.num(s.vel_u_mm_yr ?? null)} mm/yr`}>
          <td>{s.code}<div className="note">{s.place} · {s.evaluated_at ?? s.last}</div></td>
          <td>{s.anom_u_mm == null ? '—' : `${s.anom_u_mm > 0 ? '+' : ''}${fmt.num(s.anom_u_mm)} mm`}</td>
          <td>{s.z_h == null ? '—' : `${fmt.num(s.z_h)} / ${fmt.num(Math.abs(s.z_u ?? 0))}`}</td>
          <td><LevelChip level={s.level} /></td>
        </tr>))}
      </tbody>
    </table>
  )
}

export type Terrain = {
  name: string; west: number; north: number; step: number; rows: number; cols: number;
  heights_i16_b64: string; nodata: number; texture: string; max_elev: number; attribution: string
}
export type Quake = { id: string; t: string; lat: number; lon: number; x: number; y: number; depth: number | null; mag: number | null; mag_type: string; zone: string; place: string }
export type Place = { name: string; lat: number; lon: number; x: number; y: number }
export type Overlay = { png: string; west: number; north: number; step: number; rows: number; cols: number; horizon_h: number; legend: string }
export type PlaceState = { name: string; p_ever: number; observed_reached: boolean; eta_h: (number | null)[] }
export type DayState = {
  date: string; now: string
  seismic: null | { unrest_index: number | null; components: Record<string, number | null>; rate_ratio: number | null; shallowing_km: number | null;
    last24h: { n: number; max_mag: number | null; depth_median_km: number | null }; b_recent: null | { b: number; sigma: number; mc: number; n: number } }
  lava: { phase: 'pre-eruptive' } | {
    phase: 'eruptive'; hours_since_onset: number; ess: number; n_members: number
    observation: null | { observed_at: string; age_h: number; area_ha: number; reach_m: number; front_stalled: boolean | null; area_growing: boolean | null; n_observations: number }
    sea: { p_ever: number; observed_reached: boolean; eta_h: (number | null)[]; real_arrival: string }
    places: PlaceState[]
  }
  overlay?: Overlay
}
export type Meta = {
  onset: string; days: string[]; vent: { lonlat: [number, number]; xy: [number, number] }
  places: Place[]; observations: { at: string; area_ha: number }[]; milestones: { date: string; text: string }[]; sources: string[]
}
export type Zone = {
  key: string; name: string; note: string; centroid: [number, number]; box: number[]; index: number | null
  components: Record<string, number | null>; rate_ratio: number | null; n7: number; n30: number; max_mag30: number | null
  depth_median30: number | null; daily30: number[]; b: null | { b: number; sigma: number; mc: number; n: number }
}
export type Status = {
  version: string; now: string
  llm: { ok: boolean; provider: string; model: string; base?: string; error?: string; models?: string[] }
  catalog: { n_events: number; first: string | null; last: string | null; refresh_error: string | null; citation: string }
}
export type Citation = { n: number; doc: string; section: string; kind: string; excerpt: string }

async function get<T>(url: string): Promise<T> {
  const r = await fetch(url)
  if (!r.ok) throw new Error(`${r.status} ${url}`)
  return r.json() as Promise<T>
}
async function post<T>(url: string, body: unknown): Promise<T> {
  const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  if (!r.ok) throw new Error(`${r.status} ${url}`)
  return r.json() as Promise<T>
}

export const api = {
  status: () => get<Status>('/api/status'),
  terrain: (name: 'lapalma' | 'archipelago') => get<Terrain>(`/api/terrain/${name}`),
  lpMeta: () => get<Meta>('/api/lapalma2021/meta'),
  lpDay: (d: string) => get<DayState>(`/api/lapalma2021/day/${d}`),
  lpQuakes: () => get<{ n: number; quakes: Quake[] }>('/api/lapalma2021/quakes'),
  lpBriefing: (d: string, regenerate = false) =>
    post<{ text: string; ai: boolean; error?: string; model: Status['llm']; citations: Citation[] }>(`/api/lapalma2021/briefing/${d}`, { regenerate }),
  zones: () => get<{ at: string; zones: Zone[]; note: string }>('/api/canarias/zones'),
  quakes: (days = 30) => get<{ n: number; quakes: Quake[]; citation: string }>(`/api/canarias/quakes?days=${days}`),
  refresh: () => post<Status['catalog']>('/api/canarias/refresh', {}),
  solunar: (zone: string, start = '2011-01-01') => get<any>(`/api/solunar?zone=${zone}&start=${start}`),
  chat: (question: string, context?: string) =>
    post<{ answer: string | null; ai: boolean; error?: string; model: Status['llm']; citations: Citation[] }>('/api/chat', { question, context }),
}

export function decodeHeights(t: Terrain): Float32Array {
  const bin = atob(t.heights_i16_b64)
  const buf = new ArrayBuffer(bin.length)
  const u8 = new Uint8Array(buf)
  for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i)
  const i16 = new Int16Array(buf)
  const out = new Float32Array(i16.length)
  for (let i = 0; i < i16.length; i++) out[i] = i16[i] === t.nodata ? NaN : i16[i]
  return out
}

export const fmt = {
  pct: (p: number | null | undefined) => (p == null ? '—' : `${Math.round(p * 100)} %`),
  num: (v: number | null | undefined, d = 1) => (v == null ? '—' : v.toLocaleString('es-ES', { maximumFractionDigits: d, minimumFractionDigits: d })),
  int: (v: number | null | undefined) => (v == null ? '—' : Math.round(v).toLocaleString('es-ES')),
  hours: (h: number | null | undefined) => (h == null ? '—' : h < 48 ? `${Math.round(h)} h` : `${(h / 24).toFixed(1).replace('.', ',')} d`),
  date: (iso: string) => new Date(iso).toLocaleDateString('es-ES', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }),
  dateTime: (iso: string) => new Date(iso).toLocaleString('es-ES', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'UTC' }) + ' UTC',
}

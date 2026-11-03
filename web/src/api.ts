import type { GnssStation, So2Status } from './views/Indicators'
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
  indicators?: { gnss: { code: string; place: string; since: string; disp_mm: null | { e: number; n: number; u: number }; level: string }[]
    so2: So2Status; so2_series: { date: string; kt: number }[] }
}
export type Meta = {
  onset: string; days: string[]; vent: { lonlat: [number, number]; xy: [number, number] }
  places: Place[]; observations: { at: string; area_ha: number }[]; milestones: { date: string; text: string }[]; sources: string[]
}
export type Zone = {
  key: string; name: string; note: string; centroid: [number, number]; bbox: number[]; index: number | null
  components: Record<string, number | null>; rate_ratio: number | null; n7: number; n30: number; max_mag30: number | null
  depth_median30: number | null; daily30: number[]; b: null | { b: number; sigma: number; mc: number; n: number }
  mc: number | null; rate_surprise: number | null; history: string | null
  deformation: { level: string; n_stations: number; evaluated_at: string | null; worst: GnssStation | null }
}
export type TfScenario = {
  key: string; name: string; history: string; horizon_h: number; unavailable?: boolean; note?: string
  vents?: { lonlat: [number, number]; xy: [number, number] }[]; vent_names?: string[]; n_paths?: number; reach_sea?: number
  buildings?: { expected: number; p10_p90: number[] }; road_km?: { expected: number; p10_p90: number[] }
  facilities?: Facility[]; ponds?: number; places?: { name: string; kind: string; p: number; x: number; y: number }[]; isolation?: Isolation[]
  buildings_at_risk_xy?: [number, number, number][]; n_buildings_exposed?: number; overlay?: Overlay; exposure_note?: string
  seismic?: { n_events: number; depth_cut_km: number; n_vents: number; days: number }
}
export type CalibrationRow = { threshold: number; episodes: number; preceded_eruption: number; eruptions: number; lead_days: Record<string, number>
  share_of_time_pct: number; list: { zone: string; start: string; end: string; peak: number; outcome: string }[] }
export type Calibration = { start: string; end: string; table: CalibrationRow[]; eruptions: Record<string, { date: string; name: string }>; series?: [string, number | null][] }
export type Indicators = { zone: string; deformation: { level: string; stations: GnssStation[]; citation: string }; so2: So2Status
  so2_series: { date: string; so2_kt: number }[]; notes: { deformation: string; so2: string } }
export type Status = {
  version: string; now: string
  llm: { ok: boolean; provider: string; model: string; adapter?: string; base?: string; error?: string; models?: string[] }
  vision?: { port: string; adapter: string; family: string; model: string; mode: string; ready: boolean; note: string }
  catalog: { n_events: number; first: string | null; last: string | null; refresh_error: string | null; citation: string
    health?: { level: string; ok: boolean; message: string; last_download_age_h: number | null; last_event_age_h: number | null; backup_events: number } }
}
export type Range3 = { low: number; central: number; high: number }
export type Facility = { name: string; kind: string; lon: number; lat: number; p: number; already_lost: boolean; eta_h: (number | null)[] }
export type Isolation = { name: string; kind: string; lon: number; lat: number; p_isolated: number; p_reached: number }
export type ImpactBlock = {
  horizon_h: number
  already_lost: { buildings: number; road_km: number }
  buildings: { expected: number; p10_p90: number[] }
  road_km: { expected: number; p10_p90: number[] }
  facilities: Facility[]; ponds: { expected: number; already_lost: number }; isolation: Isolation[]
}
export type ImpactDay = { date: string; phase: 'eruptive' | 'pre-eruptive' } & Partial<ImpactBlock> & {
  constrained?: null | { rates_ha_h: number[]; map_age_h: number; area_ha: Range3; buildings: Range3; road_km: Range3
    interval?: { n_past: number; ratio_p10_p90: number[] } }
  watch?: null | { high: number; pocket: number; pocket_xy: [number, number][] }
  map_delay_h?: number
  truth_after?: null | { at: string; new_buildings: number; new_road_km: number }
  buildings_at_risk_xy?: [number, number, number][]
  method?: string
  scenario?: null | (ImpactBlock & { n_vent_events: number; shallow_depth_max_km: number; vent_centroid_xy: [number, number]
    nearest_candidate_to_real_vent_km: number; places: { name: string; p: number }[]; overlay: Overlay; note: string })
}
export type ValidationRow = { date: string; lost_buildings: number; map_age_h: number; pred_24: { expected: number; p10_p90: number[] }; obs_24?: number
  pred_72: { expected: number; p10_p90: number[]; rate_range: number[]; calibrated: boolean }; obs_72?: number
  watch?: { high: number; high_hit: number; pocket: number; pocket_hit: number; lost: number } }
export type WatchTier = { recall: number | null; precision: number | null; median_flagged: number }
export type ValidationSummary = { days: number; within_p10_p90_72h: number; total_pred_72: number; total_obs_72: number; bias_pct: number | null
  mae_72: number | null; first_10_days: { days: number; within: number }; watch: null | { lost: number; high: WatchTier; with_pocket: WatchTier } }
export type ValidationData = { rows: ValidationRow[]; summary: ValidationSummary; truth: string; method: string; map_delay_h: number
  delay_sensitivity: null | Record<string, { days: number; within_p10_p90_72h: number; bias_pct: number | null; mae_72: number | null }> }
export type Report = {
  zone: { key: string; name: string; note: string }; month: string; title: string; partial: boolean; generated_at: string
  stats: { n: number; max_mag: number | null; n_m2: number; n_m3: number; depth_median: number | null; depth_p10: number | null; shallow_lt5: number; energy_j: number }
  prev: Report['stats']; baseline: { rate_day: number; n_365: number }; rate_day: number; rate_ratio: number | null
  daily: number[]; daily_depth: (number | null)[]; b: null | { b: number; sigma: number; mc: number; n: number }
  unrest_end: { index: number | null; components: Record<string, number | null> }
  top_events: { t: string; mag: number | null; mag_type: string; depth: number | null; place: string; int_max: string | null; id: string }[]
  felt: number; tides: null | Record<'semidiurnal' | 'fortnightly', { n: number; c: number; p_shift: number }>; summary: string; sources: string[]
  deformation: null | { level: string; stations: GnssStation[] }
  so2: null | { days: number; days_detected: number; max_kt: number; threshold_kt: number }
}
export type Citation = { n: number; doc: string; section: string; kind: string; excerpt: string }

/** Static snapshot (no server): the API is read from pre-generated JSON next to the page. */
export const STATIC = import.meta.env.VITE_STATIC === '1'

function staticUrl(url: string): string {
  const [path, qs] = url.split('?')
  const q = new URLSearchParams(qs ?? '')
  let p = path.replace(/^\/api\//, 'api/')
  if (p === 'api/canarias/quakes') p += `-${q.get('days') ?? '30'}`
  if (p === 'api/solunar') p += `/${q.get('zone') ?? 'la_palma'}`
  if (p.startsWith('api/lapalma2021/briefing/')) p = p.replace('briefing', 'briefing-static')
  if (p === 'api/reports/monthly') p += `/${q.get('zone')}/${q.get('month')}`
  if (p === 'api/canarias/indicators') p += `/${q.get('zone')}`
  return `${p}.json`
}

// ---- session (only when the server has VOLSCAN_AUTH=on)
const TOKEN_KEY = 'volscan.token'
export function getToken(): string | null { try { return sessionStorage.getItem(TOKEN_KEY) } catch { return null } }
export function setToken(t: string | null) { try { if (t) sessionStorage.setItem(TOKEN_KEY, t); else sessionStorage.removeItem(TOKEN_KEY) } catch { /* private mode */ } }
export const authEvents = new EventTarget()
function authHeaders(): Record<string, string> { const t = getToken(); return t ? { Authorization: `Bearer ${t}` } : {} }
function onStatus(r: Response, url: string) {
  if (r.status === 401) authEvents.dispatchEvent(new Event('unauthorized'))
  if (!r.ok) throw new Error(r.status === 403 ? 'tu rol no permite esta acción' : `${r.status} ${url}`)
}

const GET_CACHE = new Map<string, Promise<unknown>>()
const UNCACHEABLE_PREFIXES = ['/api/status', '/api/auth/config', '/api/audit']

export function clearApiCache() {
  GET_CACHE.clear()
}

async function get<T>(url: string): Promise<T> {
  const canCache = !UNCACHEABLE_PREFIXES.some((p) => url.startsWith(p))
  if (canCache && GET_CACHE.has(url)) {
    return GET_CACHE.get(url) as Promise<T>
  }
  const p = (async () => {
    const r = await fetch(STATIC ? staticUrl(url) : url, STATIC ? undefined : { headers: authHeaders() })
    onStatus(r, url)
    return r.json() as Promise<T>
  })()
  if (canCache) {
    GET_CACHE.set(url, p)
    p.catch(() => GET_CACHE.delete(url))
  }
  return p
}

/** Authenticated download (PDF, CAP, GeoJSON...) saved with the given file name. */
export async function download(url: string, filename: string) {
  const r = await fetch(url, { headers: authHeaders() })
  onStatus(r, url)
  const blob = await r.blob()
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = filename
  document.body.appendChild(a); a.click(); a.remove()
  setTimeout(() => URL.revokeObjectURL(a.href), 2000)
}
async function post<T>(url: string, body: unknown): Promise<T> {
  if (STATIC) {
    if (url.includes('/briefing/')) return get<T>(url)
    if (url === '/api/chat') {
      return { answer: null, ai: false, error: 'esta es una instantánea estática; el asistente con IA funciona en la versión local (VolScan.command)', model: { ok: false, provider: 'local', model: '—' }, citations: [] } as T
    }
    if (url === '/api/canarias/refresh') return get<T>('/api/status').then((s: any) => s.catalog)
    if (url === '/api/reports/rewrite') return { text: null, ai: false, error: 'la redacción con IA funciona en la versión local', model: { ok: false, provider: 'local', model: '—' } } as T
  }
  const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() }, body: JSON.stringify(body) })
  onStatus(r, url)
  return r.json() as Promise<T>
}

export type AuthUser = { name: string; role: 'lector' | 'tecnico' | 'admin' }
export type AuditEntry = { t: string; user: string | null; role: string | null; method: string; path: string; query: string; status: number; ip: string | null; event?: string }

export const api = {
  authConfig: () => STATIC ? Promise.resolve({ enabled: false, user: null as AuthUser | null, roles: [] as string[] }) : get<{ enabled: boolean; user: AuthUser | null; roles: string[] }>('/api/auth/config'),
  login: (name: string, password: string) => { clearApiCache(); return post<{ token: string; user: AuthUser }>('/api/login', { name, password }) },
  logout: () => { clearApiCache(); return post<{ ok: boolean }>('/api/logout', {}) },
  audit: (limit = 200) => get<{ entries: AuditEntry[]; chain: { ok: boolean; lines: number; broken_at?: number }; auth_enabled: boolean }>(`/api/audit?limit=${limit}`),
  status: () => get<Status>('/api/status'),
  terrain: (name: 'lapalma' | 'archipelago' | 'tenerife') => get<Terrain>(`/api/terrain/${name}`),
  lpMeta: () => get<Meta>('/api/lapalma2021/meta'),
  lpDay: (d: string) => get<DayState>(`/api/lapalma2021/day/${d}`),
  lpQuakes: () => get<{ n: number; quakes: Quake[] }>('/api/lapalma2021/quakes'),
  lpBriefing: (d: string, regenerate = false) =>
    post<{ text: string; ai: boolean; error?: string; model: Status['llm']; citations: Citation[] }>(`/api/lapalma2021/briefing/${d}`, { regenerate }),
  zones: () => get<{ at: string; zones: Zone[]; note: string; so2: So2Status }>('/api/canarias/zones'),
  tfScenarios: () => get<{ scenarios: { key: string; name: string; history: string }[]; note: string }>('/api/tenerife/scenarios'),
  tfScenario: (key: string) => get<TfScenario>(`/api/tenerife/scenario/${key}`),
  calibration: () => get<Calibration>('/api/canarias/calibration'),
  indicators: (zone: string) => get<Indicators>(`/api/canarias/indicators?zone=${zone}`),
  quakes: (days = 30) => get<{ n: number; quakes: Quake[]; citation: string }>(`/api/canarias/quakes?days=${days}`),
  refresh: () => { clearApiCache(); return post<Status['catalog']>('/api/canarias/refresh', {}) },
  solunar: (zone: string, start = '2011-01-01') => get<any>(`/api/solunar?zone=${zone}&start=${start}`),
  lpImpact: (d: string) => get<ImpactDay>(`/api/lapalma2021/impact/${d}`),
  lpValidation: () => get<ValidationData>('/api/lapalma2021/validation'),
  lpSam3: (d: string) => get<Sam3Day>(`/api/lapalma2021/sam3/${d}`),
  lpSam3Validation: () => get<Sam3Validation>('/api/lapalma2021/sam3-validation'),
  reportMonths: () => get<{ months: string[]; zones: { key: string; name: string }[] }>('/api/reports/months'),
  report: (zone: string, month: string) => get<Report>(`/api/reports/monthly?zone=${zone}&month=${month}`),
  catastropheReport: () => get<CatastropheReport>('/api/reports/catastrophe/lapalma2021'),
  reportRewrite: (zone: string, month: string) => post<{ text: string | null; ai: boolean; error?: string; model: Status['llm'] }>('/api/reports/rewrite', { zone, month }),
  chat: (question: string, context?: string) =>
    post<AgentResponse>('/api/chat', { question, context }),
}

export type CatastropheReport = {
  title: string; subtitle: string
  summary_kpis: {
    eruption_days: number; real_area_ha: number; real_buildings_destroyed: number; real_quakes_total: number
    volscan_days_within_p10_p90: number; volscan_eval_days: number; volscan_bias_pct: number | null
    sam3_mean_iou: number | null; sam3_lead_gain_h: number | null
  }
  provenance: { layer: string; kind: 'REAL' | 'ESTIMADO'; source: string; usage: string }[]
  rheology_phases: {
    phase: string; period: string; lava_type: string; rheology_real: string; rheology_model: string; coincidence: string
    stats: { days: number; within: number; coverage_pct?: number; pred_mean_72h?: number; obs_mean_72h?: number }
  }[]
  timeline: {
    date: string; milestone: string; phase: 'pre-eruptive' | 'eruptive'
    real: { quakes_24h: number; depth_median_km: number | null; cems_area_ha: number; lost_buildings_cum: number; obs_new_buildings_72h: number | null }
    estimated: { unrest_index: number | null; nearest_vent_km: number | null; pred_new_buildings_72h: number | null; p10_p90: number[] | null; sea_prob: number | null; sea_eta_p50_h?: number | null; sam3_area_ha: number | null; sam3_iou: number | null }
    tide: { lunar_elong_deg: number; regime: string; semidiurnal_deg: number }
    verdict: string
  }[]
  tides_crisis: null | {
    onset_utc: string; onset_lunar_elong_deg: number; onset_regime: string; onset_semidiurnal_deg: number
    swarm_precursor: { period: string; n_raw: number; n_declustered: number; semidiurnal: null | { n: number; c: number; p_shift: number } }
    syn_eruptive: { period: string; n_raw: number; n_declustered: number; semidiurnal: null | { n: number; c: number; p_shift: number }; fortnightly: null | { n: number; c: number; p_shift: number } }
    explanation: string
  }
}

export type Sam3Day = {
  date: string; phase: 'pre-eruptive' | 'eruptive'; available: boolean; note?: string
  observation_index?: number; observed_at?: string; cems_already_delivered_at_now?: boolean; lead_time_advantage_h?: number | null
  segmentation?: { adapter: string; model: string; mode: string; latency_ms: number; area_ha: number; reach_m: number; n_prompt_points: number }
  comparison_vs_cems?: { cems_area_ha: number; sam3_area_ha: number; cems_reach_m: number; sam3_reach_m: number; iou: number; precision: number; recall: number; f1: number }
  assimilated_forecast?: { n_passes_assimilated: number; ess: number; sea_p_ever: number; sea_eta_h: (number | null)[] }
  overlay?: Overlay
  adapter: NonNullable<Status['vision']>
}
export type Sam3Validation = {
  adapter: NonNullable<Status['vision']>; n_scenes: number; note: string
  summary: { mean_iou: number; median_iou: number; min_iou: number; max_iou: number; mean_precision: number; mean_recall: number; mean_f1: number; mean_latency_ms: number; cems_delivery_delay_h: number; sam3_delivery_delay_h: number; lead_time_gain_h: number | null }
  scenes: { k: number; observed_at: string; date: string; cems_area_ha: number; sam3_area_ha: number; cems_reach_m: number; sam3_reach_m: number; latency_ms: number; n_prompts: number; iou: number; precision: number; recall: number; f1: number }[]
}
export type AgentResponse = {
  answer: string | null; ai: boolean; error?: string; model: Status['llm']
  segmentation_adapter?: Status['vision']
  tool_calls?: { name: string; arguments: Record<string, unknown>; duration_ms: number; output: Record<string, unknown> }[]
  citations: Citation[]
}

const HEIGHTS_CACHE = new WeakMap<Terrain, Float32Array>()

export function decodeHeights(t: Terrain): Float32Array {
  const cached = HEIGHTS_CACHE.get(t)
  if (cached) return cached
  const bin = atob(t.heights_i16_b64)
  const buf = new ArrayBuffer(bin.length)
  const u8 = new Uint8Array(buf)
  for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i)
  const i16 = new Int16Array(buf)
  const out = new Float32Array(i16.length)
  for (let i = 0; i < i16.length; i++) out[i] = i16[i] === t.nodata ? NaN : i16[i]
  HEIGHTS_CACHE.set(t, out)
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

/** Human label for the model that answered: Meta API, Meta open weights on this machine, or another local model. */
export function modelLabel(provider?: string, model?: string): string {
  const m = model || '—'
  if (provider === 'meta') return `Meta · ${m}`
  if (provider === 'meta-local' || /glimmer/i.test(m)) return 'Meta Muse Glimmer · local'
  return `Local · ${m}`
}

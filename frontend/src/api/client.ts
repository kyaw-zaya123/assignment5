import axios from 'axios'

const baseURL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8010/api'

export const api = axios.create({
  baseURL,
  timeout: 120_000,
})

export const apiOrigin = baseURL.replace(/\/api\/?$/, '')

function readAccessToken(): string | null {
  const direct = localStorage.getItem('ml_token')
  if (direct) return direct
  try {
    const raw = localStorage.getItem('ml_auth')
    if (!raw) return null
    const auth = JSON.parse(raw) as { access_token?: string }
    if (auth?.access_token) {
      localStorage.setItem('ml_token', auth.access_token)
      return auth.access_token
    }
  } catch {
    /* ignore */
  }
  return null
}

api.interceptors.request.use((config) => {
  const token = readAccessToken()
  if (token) {
    config.headers = config.headers ?? {}
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (res) => res,
  (err) => {
    const status = err?.response?.status
    if (status === 401) {
      const url = String(err?.config?.url || '')
      // Don't wipe session on login failure
      if (!url.includes('/auth/login')) {
        localStorage.removeItem('ml_token')
        const detail = err?.response?.data?.detail
        err.message =
          typeof detail === 'string' && detail
            ? `${detail} — please log in again`
            : 'Not authenticated — please log in again'
      }
    } else if (status === 403) {
      const detail = err?.response?.data?.detail
      err.message =
        typeof detail === 'string' && detail
          ? detail
          : 'Forbidden — your role cannot perform this action'
    }
    return Promise.reject(err)
  },
)

export type WeatherSnapshot = {
  temperature?: number | null
  rainfall?: number | null
  humidity?: number | null
  condition?: string
  storm?: boolean
  flood_risk?: string
  provider?: string
}

export type CityPoint = {
  name: string
  latitude: number
  longitude: number
  region?: string
  weather?: WeatherSnapshot
  is_hub?: boolean
}

export type Gate = {
  id: number
  name: string
  location: string
  latitude?: number | null
  longitude?: number | null
  status: string
  updated_at?: string
}

export type Shipment = {
  id: number
  tracking_number: string
  vehicle_id?: number | null
  trader_id?: number | null
  driver_id?: number | null
  origin: string
  destination: string
  cargo_type?: string | null
  weight?: number | null
  status: string
  latest_risk_level?: string | null
  latest_risk_score?: number | null
  origin_lat?: number | null
  origin_lon?: number | null
  dest_lat?: number | null
  dest_lon?: number | null
}

export type MapOverview = {
  vehicles: Array<{
    vehicle_id: number
    plate_number: string
    latitude: number
    longitude: number
    speed?: number
    status: string
    weather?: WeatherSnapshot
    shipment_id?: string | null
    shipment_status?: string | null
    driver?: string | null
    risk_level?: string | null
  }>
  risk_zones: Array<{
    name: string
    latitude: number
    longitude: number
    radius_km: number
    level: string
  }>
  risk_heatmap?: Array<{
    latitude: number
    longitude: number
    intensity: number
  }>
  cities?: CityPoint[]
  gates?: Gate[]
  corridor_weather?: Array<{ latitude: number; longitude: number; name?: string }>
  weather_layers?: {
    enabled: boolean
    provider: string
    tiles: {
      precipitation: string
      clouds: string
      temp: string
      wind: string
    }
  }
  shipments: Shipment[]
}

export type AiResponse = {
  answer: string
  risk: string
  risk_score: number
  sources: Array<{
    text?: string
    link?: string
    network?: string
    date?: string
    category?: string
  }>
  recommendation?: string
  reasons: string[]
  evidence?: string[]
  evidence_structured?: Array<{ source: string; detail: string }>
  shipment_id?: string
  weather?: Record<string, unknown>
  position?: Record<string, unknown>
  risk_zones?: MapOverview['risk_zones']
  gates?: Gate[]
}

export type AlertItem = {
  id: number
  shipment_id: string | number
  risk_level: string
  risk_score?: number | null
  explanation?: string
  timestamp?: string
}

export type AuthUser = {
  access_token: string
  role: string
  username: string
  user_id: number
}

export async function login(username: string, password: string) {
  const { data } = await api.post<AuthUser>('/auth/login/json', { username, password })
  return data
}

export async function fetchMe() {
  const { data } = await api.get('/auth/me')
  return data
}

export async function fetchOverview() {
  const { data } = await api.get<MapOverview>('/map/overview')
  return data
}

export async function fetchShipments() {
  const { data } = await api.get<Shipment[]>('/shipments')
  return data
}

export async function createShipment(body: Partial<Shipment> & { origin: string; destination: string }) {
  const { data } = await api.post<Shipment>('/shipments', body)
  return data
}

export async function fetchTimeline(id: number) {
  const { data } = await api.get(`/shipments/${id}/timeline`)
  return data
}

export async function fetchAlerts() {
  const { data } = await api.get<AlertItem[]>('/alerts')
  return data
}

export async function askAgent(question: string, tracking_number?: string) {
  const { data } = await api.post<AiResponse>('/ai/query', { question, tracking_number })
  return data
}

export async function fetchShipmentRisk(id: number) {
  const { data } = await api.get(`/shipments/${id}/risk`)
  return data
}

export async function fetchGates() {
  const { data } = await api.get<Gate[]>('/gates')
  return data
}

export type RouteLocation = {
  name: string
  latitude: number
  longitude: number
  kind: 'city' | 'gate'
  region?: string | null
  gate_status?: string | null
  gate_id?: number | null
}

export type RoutePreview = {
  origin: RouteLocation | null
  destination: RouteLocation | null
  resolved: boolean
  gates_on_route: Array<{ name: string; status?: string | null; gate_id?: number | null }>
  warnings: string[]
  route_line: Array<[number, number]> | null
  distance_km?: number | null
  duration_hours?: number | null
  route_source?: string | null
}

export async function fetchLocations() {
  const { data } = await api.get<RouteLocation[]>('/locations')
  return data
}

export async function fetchRoutePreview(origin: string, destination: string) {
  const { data } = await api.get<RoutePreview>('/routes/preview', {
    params: { origin, destination },
  })
  return data
}

export async function fetchRoadPath(
  originLat: number,
  originLon: number,
  destLat: number,
  destLon: number,
) {
  const { data } = await api.get<{
    route_line: Array<[number, number]>
    distance_km?: number
    duration_hours?: number | null
    source?: string
  }>('/routes/path', {
    params: {
      origin_lat: originLat,
      origin_lon: originLon,
      dest_lat: destLat,
      dest_lon: destLon,
    },
  })
  return data
}

export async function updateGate(id: number, status: string) {
  const { data } = await api.patch<GateUpdateResult>(`/gates/${id}`, { status })
  return data
}

export type GateAffectedShipment = {
  id: number
  tracking_number: string
  origin: string
  destination: string
  status: string
  alert_severity?: string | null
  risk_level?: string | null
  risk_score?: number | null
  recommendation?: string | null
  evidence?: unknown[]
  evidence_structured?: Array<{ source: string; detail: string }>
  answer?: string | null
}

export type GateUpdateResult = {
  gate: Gate
  previous_status: string
  new_status: string
  affected_count: number
  ai_ran: boolean
  affected_shipments: GateAffectedShipment[]
  summary: string
}

export async function driverAction(
  shipmentId: number,
  action: string,
  extra?: { latitude?: number; longitude?: number; note?: string; document_name?: string },
) {
  const { data } = await api.post(`/shipments/${shipmentId}/driver-action`, { action, ...extra })
  return data
}

export type DocumentUploadResult = {
  ok: boolean
  shipment: Shipment
  event: {
    id: number
    event_type: string
    description?: string
    document_name?: string
    content_type?: string
    file_size?: number
    document_url?: string
    timestamp?: string
  }
}

export async function uploadShipmentDocument(
  shipmentId: number,
  file: File,
  extra?: { latitude?: number; longitude?: number; note?: string },
) {
  const form = new FormData()
  form.append('file', file)
  if (extra?.latitude != null) form.append('latitude', String(extra.latitude))
  if (extra?.longitude != null) form.append('longitude', String(extra.longitude))
  if (extra?.note) form.append('note', extra.note)
  const { data } = await api.post<DocumentUploadResult>(`/shipments/${shipmentId}/documents`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120_000,
  })
  return data
}

export async function fetchCityWeather(lat: number, lon: number, name?: string) {
  const { data } = await api.get<{ name?: string; weather: WeatherSnapshot }>('/weather/point', {
    params: { lat, lon, name },
  })
  return data
}

export async function fetchWeatherAt(lat: number, lon: number) {
  const { data } = await api.get<{
    name: string
    display_name?: string | null
    latitude: number
    longitude: number
    weather: WeatherSnapshot
  }>('/weather/at', { params: { lat, lon } })
  return data
}

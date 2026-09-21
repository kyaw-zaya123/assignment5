import { type FormEvent, useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import {
  askAgent,
  createShipment,
  fetchAlerts,
  fetchLocations,
  fetchOverview,
  fetchRoutePreview,
  fetchShipments,
  fetchTimeline,
  type AiResponse,
  type AlertItem,
  type MapOverview,
  type RouteLocation,
  type RoutePreview,
  type Shipment,
} from '../api/client'
import { LogisticsMap } from '../components/LogisticsMap'
import { AlertPanel } from '../components/Alerts'
import { ShipmentTable } from '../components/ShipmentTable'
import { EvidencePanel, TimelinePanel } from '../components/EvidenceTimeline'
import { AiPanel } from '../components/AiPanel'
import { LiveBadge } from '../components/LiveBadge'
import { usePolling } from '../hooks/usePolling'

function gateStatusClass(status?: string | null) {
  const s = (status || '').toUpperCase()
  if (s === 'CLOSED') return 'text-rose-700'
  if (s === 'WARNING') return 'text-amber-700'
  if (s === 'OPEN') return 'text-emerald-700'
  return 'text-slate-500'
}

export function TraderPage() {
  const { user, logout } = useAuth()
  const [overview, setOverview] = useState<MapOverview>()
  const [shipments, setShipments] = useState<Shipment[]>([])
  const [alerts, setAlerts] = useState<AlertItem[]>([])
  const [locations, setLocations] = useState<RouteLocation[]>([])
  const [preview, setPreview] = useState<RoutePreview | null>(null)
  const [ai, setAi] = useState<AiResponse | null>(null)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [origin, setOrigin] = useState('')
  const [destination, setDestination] = useState('')
  const [cargo, setCargo] = useState('general')

  const refresh = useCallback(async () => {
    const [ov, sh, al, locs] = await Promise.all([
      fetchOverview(),
      fetchShipments(),
      fetchAlerts(),
      fetchLocations(),
    ])
    setOverview(ov)
    setShipments(sh)
    setAlerts(al)
    setLocations(locs)
    setSelectedId((prev) => prev ?? sh[0]?.id ?? null)
    setOrigin((prev) => prev || locs.find((l) => l.name === 'Yangon')?.name || locs[0]?.name || '')
    setDestination(
      (prev) =>
        prev ||
        locs.find((l) => l.kind === 'gate' && l.name === 'Myawaddy')?.name ||
        locs.find((l) => l.kind === 'gate')?.name ||
        locs[1]?.name ||
        '',
    )
  }, [])

  const { lastUpdated, tick } = usePolling(refresh, 8_000)

  useEffect(() => {
    if (!origin || !destination || origin === destination) {
      setPreview(null)
      return
    }
    let cancelled = false
    void fetchRoutePreview(origin, destination)
      .then((p) => {
        if (!cancelled) setPreview(p)
      })
      .catch(() => {
        if (!cancelled) setPreview(null)
      })
    return () => {
      cancelled = true
    }
  }, [origin, destination])

  const route = useMemo(() => {
    if (preview?.route_line) return preview.route_line
    const s = shipments.find((x) => x.id === selectedId)
    if (!s?.origin_lat || !s.dest_lat) return undefined
    return [
      [s.origin_lat!, s.origin_lon!] as [number, number],
      [s.dest_lat!, s.dest_lon!] as [number, number],
    ]
  }, [preview, shipments, selectedId])

  const cities = useMemo(() => locations.filter((l) => l.kind === 'city'), [locations])
  const gates = useMemo(() => locations.filter((l) => l.kind === 'gate'), [locations])

  async function onCreate(e: FormEvent) {
    e.preventDefault()
    setFormError(null)
    if (!origin || !destination) {
      setFormError('Select origin and destination')
      return
    }
    if (origin === destination) {
      setFormError('Origin and destination must differ')
      return
    }
    setBusy(true)
    try {
      // Coords resolved server-side from cities/gates — do not send client lat/lon
      const created = await createShipment({
        origin,
        destination,
        cargo_type: cargo,
        status: 'CREATED',
      })
      setSelectedId(created.id)
      await refresh()
    } catch (err: unknown) {
      const detail =
        err && typeof err === 'object' && 'response' in err
          ? String((err as { response?: { data?: { detail?: string } } }).response?.data?.detail || '')
          : ''
      setFormError(detail || 'Failed to create shipment')
    } finally {
      setBusy(false)
    }
  }

  async function onAsk(q: string) {
    setBusy(true)
    try {
      const s = shipments.find((x) => x.id === selectedId)
      setAi(await askAgent(q, s?.tracking_number))
      await refresh()
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-dvh flex-col bg-[radial-gradient(ellipse_at_top,_#ecfdf5_0%,_#f1f5f9_45%,_#e2e8f0_100%)] lg:h-dvh lg:overflow-hidden">
      <header className="shrink-0 border-b bg-white/80 backdrop-blur">
        <div className="flex items-center justify-between px-4 py-2.5">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-teal-800">Trader</p>
            <h1 className="font-display text-lg font-bold leading-tight">Cargo Desk</h1>
          </div>
          <div className="flex gap-2 text-sm">
            <LiveBadge lastUpdated={lastUpdated} />
            <span className="text-slate-500">{user?.username}</span>
            {user?.role === 'ADMIN' && (
              <Link className="rounded border px-2 py-1" to="/admin">
                Admin
              </Link>
            )}
            <Link className="rounded border px-2 py-1" to="/login">
              Switch role
            </Link>
            <button className="rounded bg-slate-800 px-2 py-1 text-white" onClick={logout} type="button">
              Logout
            </button>
          </div>
        </div>
      </header>

      <main className="grid min-h-0 flex-1 gap-3 p-3 lg:grid-cols-[minmax(0,1.25fr)_minmax(320px,0.75fr)]">
        <section className="flex h-[55vh] min-h-[320px] flex-col overflow-hidden rounded-2xl border bg-white shadow-sm lg:h-auto lg:min-h-0">
          <div className="shrink-0 border-b px-3 py-2 text-sm font-semibold">Track map</div>
          <div className="min-h-0 flex-1">
            <LogisticsMap overview={overview} route={route} />
          </div>
        </section>

        <div className="grid min-h-0 grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-rows-3">
          <section className="flex min-h-0 flex-col overflow-hidden rounded-xl border bg-white p-2.5 sm:col-span-2 lg:col-span-1">
            <h2 className="mb-1.5 shrink-0 text-sm font-semibold">Create shipment</h2>
            <form onSubmit={onCreate} className="flex min-h-0 flex-1 flex-col gap-1.5 overflow-auto text-xs">
              <label className="block font-medium text-slate-600">
                Origin (city / gate)
                <select
                  className="mt-0.5 w-full rounded border px-2 py-1.5"
                  value={origin}
                  onChange={(e) => setOrigin(e.target.value)}
                  required
                >
                  <option value="" disabled>
                    Select origin…
                  </option>
                  <optgroup label="Cities">
                    {cities.map((c) => (
                      <option key={`o-c-${c.name}`} value={c.name}>
                        {c.name} ({c.region})
                      </option>
                    ))}
                  </optgroup>
                  <optgroup label="Border gates">
                    {gates.map((g) => (
                      <option key={`o-g-${g.name}`} value={g.name}>
                        {g.name} · {g.gate_status || 'OPEN'}
                      </option>
                    ))}
                  </optgroup>
                </select>
              </label>
              <label className="block font-medium text-slate-600">
                Destination (city / gate)
                <select
                  className="mt-0.5 w-full rounded border px-2 py-1.5"
                  value={destination}
                  onChange={(e) => setDestination(e.target.value)}
                  required
                >
                  <option value="" disabled>
                    Select destination…
                  </option>
                  <optgroup label="Border gates">
                    {gates.map((g) => (
                      <option key={`d-g-${g.name}`} value={g.name}>
                        {g.name} · {g.gate_status || 'OPEN'}
                      </option>
                    ))}
                  </optgroup>
                  <optgroup label="Cities">
                    {cities.map((c) => (
                      <option key={`d-c-${c.name}`} value={c.name}>
                        {c.name} ({c.region})
                      </option>
                    ))}
                  </optgroup>
                </select>
              </label>
              <label className="block font-medium text-slate-600">
                Cargo type
                <input
                  className="mt-0.5 w-full rounded border px-2 py-1.5"
                  value={cargo}
                  onChange={(e) => setCargo(e.target.value)}
                  placeholder="Cargo"
                />
              </label>

              {preview?.resolved && (
                <div className="rounded-lg border border-slate-100 bg-slate-50 px-2 py-1.5 text-[11px] text-slate-600">
                  <div>
                    Route: {preview.origin?.name} → {preview.destination?.name}
                    {preview.distance_km != null && (
                      <span className="ml-1 font-semibold text-slate-800">
                        · {preview.distance_km} km
                        {preview.duration_hours != null ? ` · ~${preview.duration_hours}h` : ''}
                        {preview.route_source === 'osrm' ? ' · road' : ''}
                      </span>
                    )}
                  </div>
                  {preview.gates_on_route.length > 0 && (
                    <div className="mt-0.5">
                      Gate:{' '}
                      {preview.gates_on_route.map((g) => (
                        <span key={g.name} className={`mr-2 font-semibold ${gateStatusClass(g.status)}`}>
                          {g.name} {g.status}
                        </span>
                      ))}
                    </div>
                  )}
                  {preview.warnings.map((w) => (
                    <div key={w} className="mt-0.5 font-medium text-amber-800">
                      ⚠ {w}
                    </div>
                  ))}
                </div>
              )}
              {formError && <p className="text-[11px] text-rose-600">{formError}</p>}

              <button
                disabled={busy || !origin || !destination || origin === destination}
                className="mt-auto w-full rounded bg-teal-700 py-1.5 font-semibold text-white disabled:opacity-50"
                type="submit"
              >
                Submit request
              </button>
            </form>
          </section>

          <section className="flex min-h-0 flex-col overflow-hidden rounded-xl border bg-white p-2.5">
            <h2 className="mb-1.5 shrink-0 text-sm font-semibold">AI risk alerts</h2>
            <div className="min-h-0 flex-1 overflow-auto">
              <AlertPanel alerts={alerts} />
            </div>
          </section>

          <section className="flex min-h-0 flex-col overflow-hidden rounded-xl border bg-white p-2.5">
            <h2 className="mb-1.5 shrink-0 text-sm font-semibold">Ask agent</h2>
            <div className="min-h-0 flex-1 overflow-auto">
              <AiPanel onAsk={onAsk} result={ai} loading={busy} error={null} />
            </div>
          </section>

          <section className="flex min-h-0 flex-col overflow-hidden rounded-xl border bg-white p-2.5">
            <h2 className="mb-1.5 shrink-0 text-sm font-semibold">Evidence</h2>
            <div className="min-h-0 flex-1 overflow-auto">
              <EvidencePanel result={ai} />
            </div>
          </section>

          <section className="flex min-h-0 flex-col overflow-hidden rounded-xl border bg-white p-2.5">
            <h2 className="mb-1.5 shrink-0 text-sm font-semibold">My shipments</h2>
            <div className="min-h-0 flex-1 overflow-auto">
              <ShipmentTable
                shipments={shipments}
                busyId={null}
                onAssess={(s) => {
                  setSelectedId(s.id)
                  void onAsk(`Is shipment ${s.tracking_number} safe?`)
                }}
              />
            </div>
          </section>

          <section className="flex min-h-0 flex-col overflow-hidden rounded-xl border bg-white p-2.5 sm:col-span-2">
            <h2 className="mb-1.5 shrink-0 text-sm font-semibold">Timeline + history</h2>
            <div className="min-h-0 flex-1 overflow-auto">
              <TimelinePanel shipmentId={selectedId} loader={fetchTimeline} refreshKey={tick} />
            </div>
          </section>
        </div>
      </main>
    </div>
  )
}

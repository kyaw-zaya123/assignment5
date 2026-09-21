import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import {
  askAgent,
  fetchAlerts,
  fetchGates,
  fetchMe,
  fetchOverview,
  fetchRoadPath,
  fetchShipments,
  fetchTimeline,
  updateGate,
  type AiResponse,
  type AlertItem,
  type Gate,
  type GateAffectedShipment,
  type GateUpdateResult,
  type MapOverview,
  type Shipment,
} from '../api/client'
import { LogisticsMap } from '../components/LogisticsMap'
import { AiPanel } from '../components/AiPanel'
import { AlertPanel } from '../components/Alerts'
import { ShipmentTable } from '../components/ShipmentTable'
import { EvidencePanel, TimelinePanel } from '../components/EvidenceTimeline'
import { LiveBadge } from '../components/LiveBadge'
import { usePolling } from '../hooks/usePolling'

function riskClass(level?: string | null) {
  const v = (level || '').toUpperCase()
  if (v === 'HIGH') return 'bg-rose-100 text-rose-800'
  if (v === 'MEDIUM') return 'bg-amber-100 text-amber-900'
  if (v === 'LOW') return 'bg-emerald-100 text-emerald-800'
  return 'bg-slate-100 text-slate-600'
}

export function AdminPage() {
  const { user, logout } = useAuth()
  const [overview, setOverview] = useState<MapOverview>()
  const [alerts, setAlerts] = useState<AlertItem[]>([])
  const [shipments, setShipments] = useState<Shipment[]>([])
  const [gates, setGates] = useState<Gate[]>([])
  const [ai, setAi] = useState<AiResponse | null>(null)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)
  const [gateImpact, setGateImpact] = useState<GateUpdateResult | null>(null)
  const [focusAffected, setFocusAffected] = useState<GateAffectedShipment | null>(null)
  const [roadRoute, setRoadRoute] = useState<Array<[number, number]> | undefined>()

  const refresh = useCallback(async () => {
    const [ov, al, sh, g] = await Promise.all([
      fetchOverview(),
      fetchAlerts(),
      fetchShipments(),
      fetchGates(),
    ])
    setOverview(ov)
    setAlerts(al)
    setShipments(sh)
    setGates(g)
    setSelectedId((prev) => prev ?? sh[0]?.id ?? null)
  }, [])

  const { lastUpdated, tick } = usePolling(refresh, 8_000)

  useEffect(() => {
    // Gate PATCH needs a valid JWT; surface auth problems early
    void fetchMe().catch(() => {
      setMsg('Session expired or missing token — open Login and sign in as admin again')
    })
  }, [])

  useEffect(() => {
    const s =
      shipments.find((x) => x.id === selectedId) ||
      shipments.find((x) => x.tracking_number === 'SH001')
    if (!s?.origin_lat || !s.origin_lon || !s.dest_lat || !s.dest_lon) {
      setRoadRoute(undefined)
      return
    }
    let cancelled = false
    void fetchRoadPath(s.origin_lat, s.origin_lon, s.dest_lat, s.dest_lon)
      .then((r) => {
        if (!cancelled) setRoadRoute(r.route_line as Array<[number, number]>)
      })
      .catch(() => {
        if (!cancelled) {
          setRoadRoute([
            [s.origin_lat!, s.origin_lon!],
            [s.dest_lat!, s.dest_lon!],
          ])
        }
      })
    return () => {
      cancelled = true
    }
  }, [shipments, selectedId])

  const route = roadRoute

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

  async function onGate(id: number, status: string) {
    setBusy(true)
    setMsg(null)
    try {
      const result = await updateGate(id, status)
      setGateImpact(result)
      setMsg(result.summary)
      if (result.affected_shipments[0]) {
        const first = result.affected_shipments[0]
        setSelectedId(first.id)
        setFocusAffected(first)
        if (first.risk_level) {
          setAi({
            answer: first.answer || first.recommendation || result.summary,
            risk: first.risk_level,
            risk_score: first.risk_score ?? 0,
            sources: [],
            recommendation: first.recommendation || undefined,
            reasons: [],
            evidence: (first.evidence as string[]) || [],
            evidence_structured: first.evidence_structured || [],
            shipment_id: first.tracking_number,
          })
        }
      } else {
        setFocusAffected(null)
      }
      await refresh()
    } catch (e) {
      const ax = e as { response?: { status?: number; data?: { detail?: string } }; message?: string }
      const detail = ax.response?.data?.detail
      if (ax.response?.status === 401) {
        setMsg('Login expired — go to Login and sign in as admin again (admin / Admin123!)')
      } else if (ax.response?.status === 403) {
        setMsg('Admin role required to change gate status')
      } else {
        setMsg(typeof detail === 'string' ? detail : ax.message || 'Gate update failed')
      }
    } finally {
      setBusy(false)
    }
  }

  function selectAffected(row: GateAffectedShipment) {
    setFocusAffected(row)
    setSelectedId(row.id)
    if (row.risk_level) {
      setAi({
        answer: row.answer || row.recommendation || '',
        risk: row.risk_level,
        risk_score: row.risk_score ?? 0,
        sources: [],
        recommendation: row.recommendation || undefined,
        reasons: [],
        evidence: (row.evidence as string[]) || [],
        evidence_structured: row.evidence_structured || [],
        shipment_id: row.tracking_number,
      })
    }
  }

  return (
    <div className="flex min-h-dvh flex-col bg-[radial-gradient(ellipse_at_top,_#ecfdf5_0%,_#f1f5f9_45%,_#e2e8f0_100%)] lg:h-dvh lg:overflow-hidden">
      <header className="shrink-0 border-b border-slate-200/80 bg-white/80 backdrop-blur">
        <div className="flex items-center justify-between gap-4 px-4 py-2.5">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-teal-800">Admin</p>
            <h1 className="font-display text-lg font-bold leading-tight">Command Center</h1>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <LiveBadge lastUpdated={lastUpdated} />
            <span className="text-slate-500">{user?.username}</span>
            <Link className="rounded border px-2 py-1" to="/trader">
              Trader
            </Link>
            <Link className="rounded border px-2 py-1" to="/driver">
              Driver
            </Link>
            <button className="rounded bg-slate-800 px-2 py-1 text-white" onClick={logout} type="button">
              Logout
            </button>
          </div>
        </div>
      </header>

      <main className="grid min-h-0 flex-1 gap-3 p-3 lg:grid-cols-[minmax(0,1.25fr)_minmax(320px,0.75fr)]">
        <section className="flex h-[55vh] min-h-[320px] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm lg:h-auto lg:min-h-0">
          <div className="shrink-0 border-b px-3 py-2">
            <h2 className="text-sm font-semibold">Live map</h2>
            <p className="text-[11px] text-slate-500">Gates · vehicles · routes · weather · cities</p>
          </div>
          <div className="min-h-0 flex-1">
            <LogisticsMap overview={overview} route={route} />
          </div>
        </section>

        <div className="grid min-h-0 grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-rows-3">
          <section className="flex min-h-0 flex-col overflow-hidden rounded-xl border bg-white p-2.5 shadow-sm">
            <h2 className="mb-1.5 shrink-0 text-sm font-semibold">Border gates</h2>
            {msg && <p className="mb-1 shrink-0 text-[11px] text-teal-800">{msg}</p>}
            <ul className="min-h-0 flex-1 space-y-1.5 overflow-auto">
              {gates.map((g) => (
                <li key={g.id} className="rounded-lg border border-slate-100 p-2 text-xs">
                  <div className="flex items-center justify-between gap-1">
                    <div className="min-w-0">
                      <div className="truncate font-semibold">{g.name}</div>
                      <div className="truncate text-[10px] text-slate-500">{g.location}</div>
                    </div>
                    <span
                      className={
                        g.status === 'CLOSED'
                          ? 'shrink-0 text-rose-700'
                          : g.status === 'WARNING'
                            ? 'shrink-0 text-amber-700'
                            : 'shrink-0 text-emerald-700'
                      }
                    >
                      {g.status}
                    </span>
                  </div>
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {(['OPEN', 'WARNING', 'CLOSED'] as const).map((st) => (
                      <button
                        key={st}
                        type="button"
                        disabled={busy || g.status === st}
                        onClick={() => void onGate(g.id, st)}
                        className="rounded border px-1.5 py-0.5 text-[10px] font-semibold disabled:opacity-40"
                      >
                        {st}
                      </button>
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          </section>

          <section className="flex min-h-0 flex-col overflow-hidden rounded-xl border bg-white p-2.5 shadow-sm">
            <div className="mb-1.5 flex shrink-0 items-center justify-between gap-2">
              <h2 className="text-sm font-semibold">Gate impact</h2>
              {gateImpact && (
                <button
                  type="button"
                  className="text-[10px] text-slate-500 underline"
                  onClick={() => {
                    setGateImpact(null)
                    setFocusAffected(null)
                  }}
                >
                  Clear
                </button>
              )}
            </div>
            <div className="min-h-0 flex-1 overflow-auto text-xs">
              {!gateImpact ? (
                <p className="text-slate-500">Change a gate status to see affected shipments + AI risk here.</p>
              ) : (
                <div className="space-y-2">
                  <div
                    className={`rounded-lg border px-2 py-1.5 ${
                      gateImpact.new_status === 'CLOSED'
                        ? 'border-rose-200 bg-rose-50 text-rose-900'
                        : gateImpact.new_status === 'WARNING'
                          ? 'border-amber-200 bg-amber-50 text-amber-950'
                          : 'border-emerald-200 bg-emerald-50 text-emerald-900'
                    }`}
                  >
                    <div className="font-semibold">
                      {gateImpact.gate.name}: {gateImpact.previous_status} → {gateImpact.new_status}
                    </div>
                    <div className="mt-0.5 text-[11px] opacity-90">{gateImpact.summary}</div>
                    <div className="mt-0.5 text-[10px]">
                      Affected: {gateImpact.affected_count}
                      {gateImpact.ai_ran ? ' · AI analysis ran' : ' · no AI (OPEN)'}
                    </div>
                  </div>
                  {gateImpact.affected_shipments.length === 0 && (
                    <p className="text-slate-500">No active shipments on this corridor.</p>
                  )}
                  {gateImpact.affected_shipments.map((s) => (
                    <button
                      key={s.id}
                      type="button"
                      onClick={() => selectAffected(s)}
                      className={`w-full rounded-lg border px-2 py-2 text-left ${
                        focusAffected?.id === s.id
                          ? 'border-teal-600 bg-teal-50'
                          : 'border-slate-100 bg-slate-50 hover:border-slate-200'
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-semibold">{s.tracking_number}</span>
                        <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${riskClass(s.risk_level || s.alert_severity)}`}>
                          {s.risk_level || s.alert_severity || 'n/a'}
                          {s.risk_score != null ? ` ${s.risk_score}` : ''}
                        </span>
                      </div>
                      <div className="mt-0.5 text-[11px] text-slate-600">
                        {s.origin} → {s.destination} · {s.status}
                      </div>
                      {s.recommendation && (
                        <div className="mt-1 text-[11px] text-slate-700 line-clamp-2">{s.recommendation}</div>
                      )}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </section>

          <section className="flex min-h-0 flex-col overflow-hidden rounded-xl border bg-white p-2.5 shadow-sm">
            <h2 className="mb-1.5 shrink-0 text-sm font-semibold">AI agent</h2>
            <div className="min-h-0 flex-1 overflow-auto">
              <AiPanel onAsk={onAsk} result={ai} loading={busy} error={null} />
            </div>
          </section>

          <section className="flex min-h-0 flex-col overflow-hidden rounded-xl border bg-white p-2.5 shadow-sm">
            <h2 className="mb-1.5 shrink-0 text-sm font-semibold">
              Evidence{focusAffected ? ` · ${focusAffected.tracking_number}` : ''}
            </h2>
            <div className="min-h-0 flex-1 overflow-auto">
              <EvidencePanel result={ai} />
            </div>
          </section>

          <section className="flex min-h-0 flex-col overflow-hidden rounded-xl border bg-white p-2.5 shadow-sm">
            <h2 className="mb-1.5 shrink-0 text-sm font-semibold">Alerts</h2>
            <div className="min-h-0 flex-1 overflow-auto">
              <AlertPanel alerts={alerts} />
            </div>
          </section>

          <section className="flex min-h-0 flex-col overflow-hidden rounded-xl border bg-white p-2.5 shadow-sm">
            <h2 className="mb-1.5 shrink-0 text-sm font-semibold">Shipments / action history</h2>
            <div className="min-h-0 flex-1 space-y-2 overflow-auto">
              <ShipmentTable
                shipments={shipments}
                busyId={null}
                onAssess={(s) => {
                  setSelectedId(s.id)
                  void onAsk(`Check risk for shipment ${s.tracking_number}`)
                }}
              />
              <TimelinePanel shipmentId={selectedId} loader={fetchTimeline} refreshKey={tick} />
            </div>
          </section>
        </div>
      </main>

      {busy && (
        <div className="pointer-events-none fixed inset-x-0 bottom-4 z-[2000] flex justify-center">
          <div className="rounded-full bg-slate-900/90 px-4 py-2 text-xs font-semibold text-white shadow-lg">
            Updating gate · running AI on affected shipments…
          </div>
        </div>
      )}
    </div>
  )
}

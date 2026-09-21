import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import {
  driverAction,
  fetchOverview,
  fetchRoadPath,
  fetchShipments,
  fetchTimeline,
  uploadShipmentDocument,
  type MapOverview,
  type Shipment,
} from '../api/client'
import { LogisticsMap } from '../components/LogisticsMap'
import { TimelinePanel } from '../components/EvidenceTimeline'
import { LiveBadge } from '../components/LiveBadge'
import {
  applyLocalAction,
  cacheActiveShipments,
  cacheOverview,
  cacheTimeline,
  clearQueue,
  enqueue,
  getCachedOverview,
  getCachedShipments,
  getCachedTimeline,
  getQueue,
  onlineStatus,
  setQueue,
  type OfflineAction,
} from '../hooks/offlineQueue'
import { useDriverGps } from '../hooks/useDriverGps'
import { usePolling } from '../hooks/usePolling'

const ACTIONS: Array<{ key: string; label: string; tone: 'primary' | 'warn' | 'muted' }> = [
  { key: 'start_trip', label: 'Start Trip', tone: 'primary' },
  { key: 'arrived_checkpoint', label: 'Arrived Checkpoint', tone: 'primary' },
  { key: 'customs_completed', label: 'Customs Completed', tone: 'primary' },
  { key: 'delivered', label: 'Delivered', tone: 'primary' },
  { key: 'report_problem', label: 'Report Problem', tone: 'warn' },
]

/** Recommended next button from current shipment status */
function nextActionForStatus(status?: string | null): string | null {
  const u = (status || '').toUpperCase()
  if (u === 'CREATED' || u === 'LOADING' || !u) return 'start_trip'
  if (u === 'PICKED_UP' || u === 'IN_TRANSIT') return 'arrived_checkpoint'
  if (u === 'CHECKPOINT') return 'customs_completed'
  if (u === 'CUSTOMS') return 'delivered'
  if (u === 'DELAYED') return 'arrived_checkpoint'
  return null
}

function nextHint(status?: string | null): string {
  const key = nextActionForStatus(status)
  if (key === 'start_trip') return 'Next: press Start Trip (ခရီးစတင်)'
  if (key === 'arrived_checkpoint') return 'Next: press Arrived Checkpoint (ဂိတ်/checkpoint ရောက်ပြီ)'
  if (key === 'customs_completed') return 'Next: press Customs Completed (အကောက်ခွန်ပြီး)'
  if (key === 'delivered') return 'Next: press Delivered (ပို့ဆောင်ပြီး)'
  if ((status || '').toUpperCase() === 'DELIVERED') return 'Trip finished — pick another shipment'
  return 'Use the highlighted button for the next step'
}


function statusBadge(status: string) {
  const u = status.toUpperCase()
  if (u === 'DELIVERED') return 'bg-emerald-100 text-emerald-800'
  if (u === 'DELAYED') return 'bg-rose-100 text-rose-800'
  if (u === 'CHECKPOINT' || u === 'CUSTOMS') return 'bg-amber-100 text-amber-900'
  if (u === 'IN_TRANSIT' || u === 'PICKED_UP') return 'bg-sky-100 text-sky-900'
  return 'bg-slate-100 text-slate-700'
}

function syncTone(state: string) {
  if (state === 'ONLINE') return 'bg-emerald-500/15 text-emerald-700 ring-emerald-500/30'
  if (state === 'SYNCING') return 'bg-amber-500/15 text-amber-800 ring-amber-500/30'
  return 'bg-rose-500/15 text-rose-700 ring-rose-500/30'
}

export function DriverPage() {
  const { user, logout } = useAuth()
  const [shipments, setShipments] = useState<Shipment[]>([])
  const [overview, setOverview] = useState<MapOverview>()
  const [selected, setSelected] = useState<Shipment | null>(null)
  const [net, setNet] = useState(onlineStatus())
  const [syncState, setSyncState] = useState<'ONLINE' | 'OFFLINE' | 'SYNCING'>('ONLINE')
  const [msg, setMsg] = useState<string | null>(null)
  const [queueLen, setQueueLen] = useState(0)
  const [busy, setBusy] = useState(false)
  const [lastDoc, setLastDoc] = useState<string | null>(null)
  const [fromCache, setFromCache] = useState(false)
  const [tlTick, setTlTick] = useState(0)
  const [roadRoute, setRoadRoute] = useState<Array<[number, number]> | undefined>()
  const fileRef = useRef<HTMLInputElement>(null)
  const gps = useDriverGps()

  const applyShipmentList = useCallback((sh: Shipment[]) => {
    const active = sh.filter((s) => (s.status || '').toUpperCase() !== 'DELIVERED')
    setShipments(active)
    setSelected((prev) => {
      if (prev) {
        const still = active.find((x) => x.id === prev.id)
        if (still) return still
      }
      return active[0] || null
    })
  }, [])

  const refresh = useCallback(async () => {
    const q = await getQueue()
    setQueueLen(q.length)
    if (!navigator.onLine) {
      const [cachedSh, cachedOv] = await Promise.all([getCachedShipments(), getCachedOverview()])
      applyShipmentList(cachedSh)
      if (cachedOv) setOverview(cachedOv)
      setFromCache(true)
      setSyncState('OFFLINE')
      return
    }
    try {
      const [sh, ov] = await Promise.all([fetchShipments(), fetchOverview()])
      const active = await cacheActiveShipments(sh)
      await cacheOverview(ov)
      for (const s of active.slice(0, 8)) {
        try {
          const tl = await fetchTimeline(s.id)
          await cacheTimeline({ ...tl, cachedAt: new Date().toISOString() })
        } catch {
          /* keep prior timeline cache */
        }
      }
      applyShipmentList(active)
      setOverview(ov)
      setFromCache(false)
      setSyncState(q.length ? 'SYNCING' : 'ONLINE')
      setTlTick((n) => n + 1)
    } catch {
      const [cachedSh, cachedOv] = await Promise.all([getCachedShipments(), getCachedOverview()])
      applyShipmentList(cachedSh)
      if (cachedOv) setOverview(cachedOv)
      setFromCache(true)
      setSyncState('OFFLINE')
      setMsg('Using cached trip (until delivery) — will sync when online')
    }
  }, [applyShipmentList])

  const loadTimeline = useCallback(
    async (id: number) => {
      if (navigator.onLine) {
        try {
          const tl = await fetchTimeline(id)
          if ((tl.status || '').toUpperCase() !== 'DELIVERED') {
            await cacheTimeline({ ...tl, cachedAt: new Date().toISOString() })
          }
          return tl
        } catch {
          /* fall through to cache */
        }
      }
      const cached = await getCachedTimeline(id)
      if (cached) return cached
      throw new Error('Timeline unavailable offline')
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps -- tlTick forces reload after local events
    [tlTick],
  )

  async function queueLocal(shipment: Shipment, action: string, payload: Record<string, unknown>, fileBlob?: Blob) {
    await enqueue({ shipmentId: shipment.id, action, payload, fileBlob })
    const updated = await applyLocalAction(shipment, action, payload)
    const q = await getQueue()
    setQueueLen(q.length)
    setSyncState('OFFLINE')
    setTlTick((n) => n + 1)
    if ((updated.status || '').toUpperCase() === 'DELIVERED') {
      applyShipmentList((await getCachedShipments()).filter((s) => s.id !== shipment.id))
      setMsg('Delivered saved offline — trip cache cleared after delivery; will sync when online')
    } else {
      setShipments((prev) => prev.map((s) => (s.id === updated.id ? updated : s)))
      setSelected((prev) => (prev?.id === updated.id ? updated : prev))
    }
  }

  useEffect(() => {
    const on = () => {
      setNet('ONLINE')
      void flushQueue()
    }
    const off = () => {
      setNet('OFFLINE')
      setSyncState('OFFLINE')
      void refresh()
    }
    window.addEventListener('online', on)
    window.addEventListener('offline', off)
    setSyncState(navigator.onLine ? 'ONLINE' : 'OFFLINE')
    return () => {
      window.removeEventListener('online', on)
      window.removeEventListener('offline', off)
    }
  }, [refresh])

  const { lastUpdated, tick: pollTick } = usePolling(
    refresh,
    8_000,
    net === 'ONLINE',
  )

  // Seed pin from assigned vehicle when shipment selected (no random)
  useEffect(() => {
    if (gps.fix || !selected?.vehicle_id || !overview) return
    const v = overview.vehicles.find((x) => x.vehicle_id === selected.vehicle_id)
    if (v) {
      gps.applyFix(v.latitude, v.longitude, 'manual', null)
      return
    }
    if (selected.origin_lat != null && selected.origin_lon != null) {
      gps.applyFix(selected.origin_lat, selected.origin_lon, 'manual', null)
    }
  }, [selected?.id, selected?.vehicle_id, overview, gps.fix, gps.applyFix, selected?.origin_lat, selected?.origin_lon])

  // Auto-sync GPS while watching (throttle ~12s)
  useEffect(() => {
    if (!gps.watching || !gps.fix || !selected) return
    const t = window.setTimeout(() => {
      void syncGps(false)
    }, 12_000)
    return () => window.clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- sync on fix changes while watching
  }, [gps.fix?.at, gps.watching, selected?.id])

  useEffect(() => {
    if (!selected?.origin_lat || !selected.origin_lon || !selected.dest_lat || !selected.dest_lon) {
      setRoadRoute(undefined)
      return
    }
    let cancelled = false
    void fetchRoadPath(selected.origin_lat, selected.origin_lon, selected.dest_lat, selected.dest_lon)
      .then((r) => {
        if (!cancelled) setRoadRoute(r.route_line as Array<[number, number]>)
      })
      .catch(() => {
        if (!cancelled) {
          setRoadRoute([
            [selected.origin_lat!, selected.origin_lon!],
            [selected.dest_lat!, selected.dest_lon!],
          ])
        }
      })
    return () => {
      cancelled = true
    }
  }, [selected?.id, selected?.origin_lat, selected?.origin_lon, selected?.dest_lat, selected?.dest_lon])

  const route = roadRoute

  const nextKey = nextActionForStatus(selected?.status)
  const hint = selected ? nextHint(selected.status) : 'Select a shipment above first'
  async function flushQueue() {
    const q = await getQueue()
    if (!q.length) {
      setSyncState('ONLINE')
      await refresh()
      return
    }
    setSyncState('SYNCING')
    const remain: OfflineAction[] = []
    for (const item of q) {
      try {
        if (item.action === 'upload_document') {
          let file: File | null = null
          if (item.fileBlob && item.payload.document_name) {
            file = new File([item.fileBlob], String(item.payload.document_name), {
              type: String(item.payload.content_type || 'application/octet-stream'),
            })
          } else if (item.payload.file_base64 && item.payload.document_name) {
            const bin = Uint8Array.from(atob(String(item.payload.file_base64)), (c) => c.charCodeAt(0))
            file = new File([bin], String(item.payload.document_name), {
              type: String(item.payload.content_type || 'application/octet-stream'),
            })
          }
          if (!file) throw new Error('missing file')
          await uploadShipmentDocument(item.shipmentId, file, {
            latitude: item.payload.latitude as number | undefined,
            longitude: item.payload.longitude as number | undefined,
            note: item.payload.note as string | undefined,
          })
        } else {
          await driverAction(item.shipmentId, item.action, item.payload)
        }
      } catch {
        remain.push(item)
      }
    }
    await setQueue(remain)
    setQueueLen(remain.length)
    setSyncState(remain.length ? 'OFFLINE' : 'ONLINE')
    await refresh()
  }

  async function syncGps(showMsg = true) {
    if (!selected || !gps.fix) {
      if (showMsg) setMsg('Set GPS first — click the map or start watchPosition')
      return
    }
    const payload = {
      latitude: gps.fix.latitude,
      longitude: gps.fix.longitude,
      note: `source=${gps.fix.source}`,
    }
    setBusy(true)
    try {
      if (!navigator.onLine) {
        await queueLocal(selected, 'update_location', payload)
        if (showMsg) setMsg('GPS saved offline — will sync when online')
        return
      }
      await driverAction(selected.id, 'update_location', payload)
      if (showMsg) setMsg(`GPS synced (${gps.fix.source})`)
      await refresh()
    } catch {
      await queueLocal(selected, 'update_location', payload)
      if (showMsg) setMsg('GPS queued offline')
    } finally {
      setBusy(false)
    }
  }

  async function runAction(action: string) {
    if (!selected) return
    if (!gps.fix) {
      setMsg('Set your location on the map (or Start GPS) before trip actions')
      return
    }
    setMsg(null)
    setBusy(true)
    const payload: Record<string, unknown> = {
      latitude: gps.fix.latitude,
      longitude: gps.fix.longitude,
      note: action === 'report_problem' ? 'Road delay reported by driver' : undefined,
    }
    try {
      if (!navigator.onLine) {
        await queueLocal(selected, action, payload)
        if ((action || '') !== 'delivered') {
          setMsg('Saved offline — trip stays cached until delivery')
        }
        return
      }
      await driverAction(selected.id, action, payload)
      setMsg(`${ACTIONS.find((a) => a.key === action)?.label || action} synced`)
      await refresh()
    } catch (e) {
      const ax = e as { response?: { status?: number; data?: { detail?: string } }; message?: string }
      if (ax.response?.status === 409) {
        setMsg(ax.response.data?.detail || 'Invalid trip step — follow the lifecycle order')
        return
      }
      await queueLocal(selected, action, payload)
      setMsg('Network error — queued offline')
    } finally {
      setBusy(false)
    }
  }

  function openFilePicker() {
    if (!selected) {
      setMsg('Select a shipment first')
      return
    }
    if (!gps.fix) {
      setMsg('Set GPS pin before uploading a document')
      return
    }
    fileRef.current?.click()
  }

  async function onFilePicked(fileList: FileList | null) {
    const file = fileList?.[0]
    if (!file || !selected || !gps.fix) return
    setMsg(null)
    setBusy(true)
    const meta = {
      latitude: gps.fix.latitude,
      longitude: gps.fix.longitude,
      note: `Driver upload: ${file.name}`,
    }
    try {
      if (!navigator.onLine) {
        await queueLocal(
          selected,
          'upload_document',
          {
            ...meta,
            document_name: file.name,
            content_type: file.type || 'application/octet-stream',
            file_size: file.size,
          },
          file,
        )
        setLastDoc(file.name)
        setMsg(`Queued offline: ${file.name}`)
        return
      }
      const res = await uploadShipmentDocument(selected.id, file, meta)
      setLastDoc(res.event.document_name || file.name)
      setMsg(`Uploaded ${res.event.document_name} (${res.event.file_size || file.size} bytes)`)
      await refresh()
    } catch (e) {
      setMsg(e instanceof Error ? e.message : 'Upload failed')
    } finally {
      setBusy(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  return (
    <div className="flex min-h-dvh flex-col bg-[radial-gradient(ellipse_at_top,_#ecfdf5_0%,_#f1f5f9_40%,_#e2e8f0_100%)] lg:h-dvh lg:overflow-hidden">
      <header className="shrink-0 border-b border-slate-200/80 bg-white/85 backdrop-blur">
        <div className="flex items-center justify-between gap-3 px-4 py-2.5">
          <div className="min-w-0">
            <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-teal-800">Driver</p>
            <h1 className="truncate font-display text-lg font-bold leading-tight">Field Console</h1>
          </div>
          <div className="flex flex-wrap items-center justify-end gap-2 text-sm">
            {net === 'ONLINE' && <LiveBadge lastUpdated={lastUpdated} />}
            <span
              className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold ring-1 ${syncTone(syncState)}`}
            >
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  syncState === 'ONLINE'
                    ? 'bg-emerald-500'
                    : syncState === 'SYNCING'
                      ? 'bg-amber-500'
                      : 'bg-rose-500'
                }`}
              />
              {syncState}
              {queueLen ? ` · ${queueLen}` : ''}
              {fromCache ? ' · cached' : ''}
            </span>
            <span className="hidden text-slate-500 sm:inline">{user?.username}</span>
            <Link className="rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-medium" to="/login">
              Switch role
            </Link>
            <button
              className="rounded-lg bg-slate-800 px-2.5 py-1 text-xs font-semibold text-white"
              onClick={logout}
              type="button"
            >
              Logout
            </button>
          </div>
        </div>
      </header>

      <main className="grid min-h-0 flex-1 gap-3 p-3 lg:grid-cols-[minmax(0,1.2fr)_minmax(360px,0.8fr)]">
        <section className="flex h-[42vh] min-h-[280px] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm lg:h-auto lg:min-h-0">
          <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-3 py-2">
            <div>
              <h2 className="text-sm font-semibold text-slate-800">Track map</h2>
              <p className="text-[11px] text-slate-500">
                {gps.clickMode ? 'Click map to set GPS pin · ' : ''}
                {selected
                  ? `${selected.tracking_number} · ${selected.origin} → ${selected.destination}`
                  : 'Select a shipment'}
                {fromCache ? ' · offline cache until delivery' : ''}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-1.5">
              <button
                type="button"
                onClick={() => gps.setClickMode(!gps.clickMode)}
                className={`rounded-lg px-2 py-1 text-[10px] font-bold uppercase ${
                  gps.clickMode
                    ? 'bg-teal-700 text-white'
                    : 'border border-slate-200 bg-white text-slate-600'
                }`}
              >
                {gps.clickMode ? 'Click pin ON' : 'Click pin OFF'}
              </button>
              {gps.watching ? (
                <button
                  type="button"
                  onClick={gps.stopWatch}
                  className="rounded-lg border border-amber-300 bg-amber-50 px-2 py-1 text-[10px] font-bold uppercase text-amber-900"
                >
                  Stop GPS
                </button>
              ) : (
                <button
                  type="button"
                  onClick={gps.startWatch}
                  className="rounded-lg border border-sky-300 bg-sky-50 px-2 py-1 text-[10px] font-bold uppercase text-sky-900"
                >
                  Start GPS
                </button>
              )}
              <button
                type="button"
                disabled={!selected || !gps.fix || busy}
                onClick={() => void syncGps(true)}
                className="rounded-lg bg-slate-800 px-2 py-1 text-[10px] font-bold uppercase text-white disabled:opacity-40"
              >
                Sync GPS
              </button>
              {selected && (
                <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ${statusBadge(selected.status)}`}>
                  {selected.status}
                </span>
              )}
            </div>
          </div>
          {gps.fix && (
            <div className="shrink-0 border-b border-slate-100 bg-teal-50/80 px-3 py-1.5 text-[11px] text-teal-900">
              Pin {gps.fix.latitude.toFixed(5)}, {gps.fix.longitude.toFixed(5)}
              {' · '}
              source <b>{gps.fix.source}</b>
              {gps.fix.accuracy != null ? ` · ±${Math.round(gps.fix.accuracy)}m` : ''}
              {gps.watching ? ' · watching…' : ''}
            </div>
          )}
          {gps.error && (
            <div className="shrink-0 border-b border-rose-100 bg-rose-50 px-3 py-1.5 text-[11px] text-rose-700">
              {gps.error}
            </div>
          )}
          <div className="min-h-0 flex-1">
            <LogisticsMap
              overview={overview}
              route={route}
              driverPosition={
                gps.fix
                  ? {
                      latitude: gps.fix.latitude,
                      longitude: gps.fix.longitude,
                      source: gps.fix.source,
                    }
                  : null
              }
              clickToSetGps={gps.clickMode}
              onMapClick={gps.setFromMapClick}
            />
          </div>
        </section>

        <div className="grid min-h-0 grid-rows-[auto_minmax(0,1.1fr)_minmax(0,0.9fr)] gap-3">
          <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
            {selected ? (
              <div className="border-b border-slate-100 bg-gradient-to-r from-teal-800 to-teal-700 px-3 py-3 text-white">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-teal-100">Active trip</p>
                    <p className="font-display text-xl font-bold leading-tight">{selected.tracking_number}</p>
                    <p className="mt-0.5 text-sm text-teal-50">
                      {selected.origin} → {selected.destination}
                    </p>
                  </div>
                  <span className="rounded-full bg-white/15 px-2 py-1 text-[10px] font-bold uppercase backdrop-blur">
                    {selected.status}
                  </span>
                </div>
              </div>
            ) : (
              <div className="border-b px-3 py-3">
                <h2 className="text-sm font-semibold">Assigned shipments</h2>
              </div>
            )}
            <div className="max-h-36 space-y-1.5 overflow-auto p-2.5 sm:max-h-40 lg:max-h-28">
              {shipments.map((s) => {
                const active = selected?.id === s.id
                const mine = s.driver_id != null && user?.user_id != null && s.driver_id === user.user_id
                const claimable = s.driver_id == null
                return (
                  <button
                    key={s.id}
                    type="button"
                    onClick={() => {
                      setSelected(s)
                      setMsg(null)
                    }}
                    className={`flex w-full items-center justify-between gap-2 rounded-xl border px-3 py-2 text-left transition ${
                      active
                        ? 'border-teal-600 bg-teal-50 shadow-sm'
                        : 'border-slate-100 bg-slate-50/80 hover:border-slate-200'
                    }`}
                  >
                    <div className="min-w-0">
                      <div className="text-sm font-semibold text-slate-900">{s.tracking_number}</div>
                      <div className="truncate text-[11px] text-slate-500">
                        {s.origin} → {s.destination}
                        {claimable ? ' · unassigned' : mine ? ' · yours' : ''}
                      </div>
                    </div>
                    <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ${statusBadge(s.status)}`}>
                      {s.status}
                    </span>
                  </button>
                )
              })}
              {!shipments.length && (
                <p className="px-2 py-4 text-center text-sm text-slate-500">No assigned shipments</p>
              )}
            </div>
          </section>

          <section className="flex min-h-0 flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white p-3 shadow-sm">
            <div className="mb-2 flex shrink-0 items-center justify-between gap-2">
              <h2 className="text-sm font-semibold text-slate-800">Trip actions</h2>
              <span className="text-[10px] font-medium uppercase tracking-wide text-slate-400">Network {net}</span>
            </div>
            <p className="mb-2 shrink-0 rounded-lg border border-teal-200 bg-teal-50 px-2.5 py-1.5 text-[11px] font-semibold text-teal-900">
              {hint}
              {!gps.fix ? ' · first set GPS pin on the map (left)' : ''}
            </p>
            {msg && (
              <p className="mb-2 shrink-0 rounded-lg bg-slate-50 px-2.5 py-1.5 text-[11px] font-medium text-slate-700">
                {msg}
              </p>
            )}
            <div className="grid min-h-0 flex-1 grid-cols-2 content-start gap-2 overflow-auto">
              {ACTIONS.map((a) => {
                const isNext = a.key === nextKey
                const isPrimary = a.tone === 'primary'
                // Only the next lifecycle step is clickable (server also returns 409 on skips)
                const lifecycleBlocked =
                  isPrimary && !isNext && (selected?.status || '').toUpperCase() !== 'DELAYED'
                const baseDisabled = !selected || busy || !gps.fix || lifecycleBlocked
                return (
                  <button
                    key={a.key}
                    type="button"
                    disabled={baseDisabled}
                    title={
                      lifecycleBlocked
                        ? 'Follow the trip order — only the highlighted next step is allowed'
                        : undefined
                    }
                    onClick={() => void runAction(a.key)}
                    className={
                      a.tone === 'warn'
                        ? 'rounded-xl border border-rose-200 bg-rose-50 px-2 py-3 text-xs font-bold uppercase tracking-wide text-rose-800 disabled:opacity-40'
                        : isNext
                          ? 'rounded-xl bg-teal-700 px-2 py-3 text-xs font-bold uppercase tracking-wide text-white shadow-md ring-2 ring-teal-400 ring-offset-1 hover:bg-teal-800 disabled:opacity-40'
                          : 'rounded-xl border border-slate-200 bg-white px-2 py-3 text-xs font-bold uppercase tracking-wide text-slate-500 disabled:opacity-40'
                    }
                  >
                    {isNext ? `→ ${a.label}` : a.label}
                  </button>
                )
              })}
              <button
                type="button"
                disabled={!selected || busy || !gps.fix}
                onClick={openFilePicker}
                className="rounded-xl border border-slate-200 bg-slate-50 px-2 py-3 text-xs font-bold uppercase tracking-wide text-slate-700 disabled:opacity-40"
              >
                Upload Document
              </button>
              <input
                ref={fileRef}
                type="file"
                accept="image/*,.pdf,.doc,.docx,.png,.jpg,.jpeg"
                className="hidden"
                onChange={(e) => void onFilePicked(e.target.files)}
              />
            </div>
            {lastDoc && (
              <p className="mt-2 shrink-0 text-[11px] text-slate-500">Last file: {lastDoc}</p>
            )}
            {(queueLen > 0 || syncState === 'OFFLINE') && (
              <div className="mt-2 flex shrink-0 gap-2">
                {queueLen > 0 && navigator.onLine && (
                  <button
                    type="button"
                    className="flex-1 rounded-xl border border-amber-300 bg-amber-50 py-2 text-[11px] font-semibold text-amber-900"
                    onClick={() => void flushQueue()}
                  >
                    Sync queue ({queueLen})
                  </button>
                )}
                {queueLen > 0 && (
                  <button
                    type="button"
                    className="rounded-xl border border-slate-200 px-3 py-2 text-[11px] text-slate-500"
                    onClick={() => {
                      void clearQueue().then(async () => {
                        setQueueLen(0)
                        setSyncState(navigator.onLine ? 'ONLINE' : 'OFFLINE')
                      })
                    }}
                  >
                    Clear
                  </button>
                )}
              </div>
            )}
          </section>

          <section className="flex min-h-0 flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white p-3 shadow-sm">
            <h2 className="mb-2 shrink-0 text-sm font-semibold text-slate-800">Status + action history</h2>
            <p className="mb-2 shrink-0 text-[11px] text-slate-500">
              Lifecycle steps above · every Start Trip / Checkpoint / GPS / upload below (newest first)
            </p>
            <div className="min-h-0 flex-1 overflow-auto">
              {selected ? (
                <TimelinePanel shipmentId={selected.id} loader={loadTimeline} refreshKey={tlTick + pollTick} />
              ) : (
                <p className="text-sm text-slate-500">Select a shipment to view history.</p>
              )}
            </div>
          </section>
        </div>
      </main>
    </div>
  )
}

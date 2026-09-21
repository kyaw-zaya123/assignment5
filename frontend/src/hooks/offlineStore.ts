/** IndexedDB offline store — active trips cached until DELIVERED. */

import type { MapOverview, Shipment } from '../api/client'

const DB_NAME = 'ml_driver_offline'
const DB_VERSION = 1
const LS_QUEUE_KEY = 'ml_driver_offline_queue'

export type OfflineAction = {
  id: string
  shipmentId: number
  action: string
  payload: Record<string, unknown>
  createdAt: string
  /** Real file blob when action is upload_document (IndexedDB only). */
  fileBlob?: Blob
}

export type TimelineCache = {
  shipment_id: number
  tracking_number: string
  status: string
  steps: Array<{ step: string; state: string }>
  events: Array<Record<string, unknown>>
  cachedAt: string
}

type StoreName = 'shipments' | 'overview' | 'timelines' | 'queue'

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION)
    req.onupgradeneeded = () => {
      const db = req.result
      if (!db.objectStoreNames.contains('shipments')) {
        db.createObjectStore('shipments', { keyPath: 'id' })
      }
      if (!db.objectStoreNames.contains('overview')) {
        db.createObjectStore('overview', { keyPath: 'key' })
      }
      if (!db.objectStoreNames.contains('timelines')) {
        db.createObjectStore('timelines', { keyPath: 'shipment_id' })
      }
      if (!db.objectStoreNames.contains('queue')) {
        db.createObjectStore('queue', { keyPath: 'id' })
      }
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error || new Error('IndexedDB open failed'))
  })
}

function txDone(tx: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error || new Error('IndexedDB tx failed'))
    tx.onabort = () => reject(tx.error || new Error('IndexedDB tx aborted'))
  })
}

async function withStore<T>(
  store: StoreName,
  mode: IDBTransactionMode,
  fn: (s: IDBObjectStore) => IDBRequest<T> | void,
): Promise<T | undefined> {
  const db = await openDb()
  try {
    const tx = db.transaction(store, mode)
    const s = tx.objectStore(store)
    const req = fn(s)
    if (!req) {
      await txDone(tx)
      return undefined
    }
    const value = await new Promise<T>((resolve, reject) => {
      req.onsuccess = () => resolve(req.result)
      req.onerror = () => reject(req.error)
    })
    await txDone(tx)
    return value
  } finally {
    db.close()
  }
}

async function getAll<T>(store: StoreName): Promise<T[]> {
  return (await withStore<T[]>(store, 'readonly', (s) => s.getAll())) || []
}

/** Migrate legacy localStorage queue once into IndexedDB. */
let migrated = false
async function migrateLegacyQueue(): Promise<void> {
  if (migrated) return
  migrated = true
  try {
    const raw = localStorage.getItem(LS_QUEUE_KEY)
    if (!raw) return
    const items = JSON.parse(raw) as OfflineAction[]
    if (!Array.isArray(items) || !items.length) {
      localStorage.removeItem(LS_QUEUE_KEY)
      return
    }
    const db = await openDb()
    const tx = db.transaction('queue', 'readwrite')
    const store = tx.objectStore('queue')
    for (const item of items) {
      store.put(item)
    }
    await txDone(tx)
    db.close()
    localStorage.removeItem(LS_QUEUE_KEY)
  } catch {
    // keep legacy key if migrate fails
  }
}

const ACTION_STATUS: Record<string, string | null> = {
  start_trip: 'IN_TRANSIT',
  arrived_checkpoint: 'CHECKPOINT',
  customs_completed: 'CUSTOMS',
  delivered: 'DELIVERED',
  report_problem: 'DELAYED',
  upload_document: null,
  update_location: null,
}

const ACTION_EVENT: Record<string, string> = {
  start_trip: 'PICKED_UP',
  arrived_checkpoint: 'CHECKPOINT',
  customs_completed: 'CUSTOMS',
  delivered: 'DELIVERED',
  report_problem: 'DELAYED',
  upload_document: 'DOCUMENT',
  update_location: 'GPS',
}

export function statusForAction(action: string): string | null {
  return ACTION_STATUS[action] ?? null
}

export async function getQueue(): Promise<OfflineAction[]> {
  await migrateLegacyQueue()
  const rows = await getAll<OfflineAction>('queue')
  return rows.sort((a, b) => a.createdAt.localeCompare(b.createdAt))
}

export async function enqueue(
  item: Omit<OfflineAction, 'id' | 'createdAt'> & { fileBlob?: Blob },
): Promise<OfflineAction> {
  await migrateLegacyQueue()
  const row: OfflineAction = {
    ...item,
    id: crypto.randomUUID(),
    createdAt: new Date().toISOString(),
  }
  await withStore('queue', 'readwrite', (s) => s.put(row))
  return row
}

export async function setQueue(q: OfflineAction[]): Promise<void> {
  const db = await openDb()
  const tx = db.transaction('queue', 'readwrite')
  const store = tx.objectStore('queue')
  store.clear()
  for (const item of q) store.put(item)
  await txDone(tx)
  db.close()
}

export async function clearQueue(): Promise<void> {
  await withStore('queue', 'readwrite', (s) => {
    s.clear()
  })
}

export function onlineStatus(): 'ONLINE' | 'OFFLINE' {
  return navigator.onLine ? 'ONLINE' : 'OFFLINE'
}

/** Cache assigned shipments; drop DELIVERED (offline lasts until delivery). */
export async function cacheActiveShipments(shipments: Shipment[]): Promise<Shipment[]> {
  const active = shipments.filter((s) => (s.status || '').toUpperCase() !== 'DELIVERED')
  const db = await openDb()
  const tx = db.transaction('shipments', 'readwrite')
  const store = tx.objectStore('shipments')
  store.clear()
  for (const s of active) store.put(s)
  await txDone(tx)
  db.close()
  return active
}

export async function getCachedShipments(): Promise<Shipment[]> {
  const rows = await getAll<Shipment>('shipments')
  return rows.filter((s) => (s.status || '').toUpperCase() !== 'DELIVERED')
}

export async function upsertCachedShipment(shipment: Shipment): Promise<void> {
  if ((shipment.status || '').toUpperCase() === 'DELIVERED') {
    await removeCachedShipment(shipment.id)
    await removeCachedTimeline(shipment.id)
    return
  }
  await withStore('shipments', 'readwrite', (s) => s.put(shipment))
}

export async function removeCachedShipment(id: number): Promise<void> {
  await withStore('shipments', 'readwrite', (s) => {
    s.delete(id)
  })
}

export async function cacheOverview(overview: MapOverview): Promise<void> {
  await withStore('overview', 'readwrite', (s) => s.put({ key: 'latest', ...overview, cachedAt: new Date().toISOString() }))
}

export async function getCachedOverview(): Promise<MapOverview | null> {
  const row = await withStore<Record<string, unknown>>('overview', 'readonly', (s) => s.get('latest'))
  if (!row) return null
  const { key: _k, cachedAt: _c, ...rest } = row
  return rest as unknown as MapOverview
}

export async function cacheTimeline(data: TimelineCache): Promise<void> {
  if ((data.status || '').toUpperCase() === 'DELIVERED') {
    await removeCachedTimeline(data.shipment_id)
    return
  }
  await withStore('timelines', 'readwrite', (s) =>
    s.put({ ...data, cachedAt: data.cachedAt || new Date().toISOString() }),
  )
}

export async function getCachedTimeline(shipmentId: number): Promise<TimelineCache | null> {
  return (await withStore<TimelineCache>('timelines', 'readonly', (s) => s.get(shipmentId))) || null
}

export async function removeCachedTimeline(shipmentId: number): Promise<void> {
  await withStore('timelines', 'readwrite', (s) => {
    s.delete(shipmentId)
  })
}

/** Apply offline action to local shipment + timeline cache (optimistic). */
export async function applyLocalAction(
  shipment: Shipment,
  action: string,
  payload: Record<string, unknown>,
): Promise<Shipment> {
  const nextStatus = statusForAction(action)
  const updated: Shipment = {
    ...shipment,
    status: nextStatus || shipment.status,
  }

  if ((updated.status || '').toUpperCase() === 'DELIVERED') {
    await removeCachedShipment(updated.id)
    await removeCachedTimeline(updated.id)
    return updated
  }

  await upsertCachedShipment(updated)

  const tl = (await getCachedTimeline(shipment.id)) || {
    shipment_id: shipment.id,
    tracking_number: shipment.tracking_number,
    status: shipment.status,
    steps: [],
    events: [],
    cachedAt: new Date().toISOString(),
  }

  const eventType = ACTION_EVENT[action] || action.toUpperCase()
  const desc =
    action === 'upload_document'
      ? `Queued offline: ${String(payload.document_name || 'document')}`
      : action === 'update_location'
        ? `GPS queued (${payload.latitude}, ${payload.longitude})`
        : String(payload.note || eventType)

  tl.status = updated.status
  tl.events = [
    ...tl.events,
    {
      id: `local-${Date.now()}`,
      event_type: eventType,
      description: desc,
      latitude: payload.latitude,
      longitude: payload.longitude,
      timestamp: new Date().toISOString(),
      document_name: payload.document_name || null,
      file_size: payload.file_size || null,
      document_url: null,
      pending_sync: true,
    },
  ]
  await cacheTimeline(tl)
  return updated
}

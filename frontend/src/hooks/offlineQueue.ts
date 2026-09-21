/** Offline queue — re-exports IndexedDB store (legacy import path). */

export {
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
  removeCachedShipment,
  setQueue,
  statusForAction,
  upsertCachedShipment,
  type OfflineAction,
  type TimelineCache,
} from './offlineStore'

import { useEffect, useRef, useState } from 'react'

/**
 * Poll `fn` on an interval while the tab is visible.
 * Replaces manual page-reload for map / shipments / alerts.
 */
export function usePolling(
  fn: () => void | Promise<void>,
  intervalMs = 8_000,
  enabled = true,
) {
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const [tick, setTick] = useState(0)
  const fnRef = useRef(fn)
  fnRef.current = fn

  useEffect(() => {
    if (!enabled) return
    let cancelled = false

    const run = async () => {
      if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return
      try {
        await fnRef.current()
        if (!cancelled) {
          setLastUpdated(new Date())
          setTick((n) => n + 1)
        }
      } catch {
        /* keep last good data */
      }
    }

    void run()
    const id = window.setInterval(() => void run(), intervalMs)
    const onVis = () => {
      if (document.visibilityState === 'visible') void run()
    }
    document.addEventListener('visibilitychange', onVis)
    return () => {
      cancelled = true
      window.clearInterval(id)
      document.removeEventListener('visibilitychange', onVis)
    }
  }, [intervalMs, enabled])

  return { lastUpdated, tick }
}

export function formatPollAge(at: Date | null): string {
  if (!at) return '…'
  const sec = Math.max(0, Math.round((Date.now() - at.getTime()) / 1000))
  if (sec < 5) return 'just now'
  if (sec < 60) return `${sec}s ago`
  return `${Math.floor(sec / 60)}m ago`
}

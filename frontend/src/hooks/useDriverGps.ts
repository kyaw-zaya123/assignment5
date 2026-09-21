/** Browser GPS (watchPosition) + map-click pin for driver updates. */

import { useCallback, useEffect, useRef, useState } from 'react'

export type GpsSource = 'watch' | 'map' | 'manual'

export type GpsFix = {
  latitude: number
  longitude: number
  accuracy: number | null
  source: GpsSource
  at: string
}

export function useDriverGps() {
  const [fix, setFix] = useState<GpsFix | null>(null)
  const [watching, setWatching] = useState(false)
  const [clickMode, setClickMode] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const watchId = useRef<number | null>(null)

  const applyFix = useCallback((latitude: number, longitude: number, source: GpsSource, accuracy?: number | null) => {
    setFix({
      latitude,
      longitude,
      accuracy: accuracy ?? null,
      source,
      at: new Date().toISOString(),
    })
    setError(null)
  }, [])

  const stopWatch = useCallback(() => {
    if (watchId.current != null && navigator.geolocation) {
      navigator.geolocation.clearWatch(watchId.current)
      watchId.current = null
    }
    setWatching(false)
  }, [])

  const startWatch = useCallback(() => {
    if (!navigator.geolocation) {
      setError('Geolocation not supported in this browser')
      return
    }
    stopWatch()
    setError(null)
    setWatching(true)
    watchId.current = navigator.geolocation.watchPosition(
      (pos) => {
        applyFix(pos.coords.latitude, pos.coords.longitude, 'watch', pos.coords.accuracy)
      },
      (err) => {
        setError(err.message || 'Unable to read GPS')
        setWatching(false)
        watchId.current = null
      },
      {
        enableHighAccuracy: true,
        maximumAge: 5_000,
        timeout: 20_000,
      },
    )
  }, [applyFix, stopWatch])

  const setFromMapClick = useCallback(
    (latitude: number, longitude: number) => {
      applyFix(latitude, longitude, 'map', null)
    },
    [applyFix],
  )

  useEffect(() => () => stopWatch(), [stopWatch])

  return {
    fix,
    watching,
    clickMode,
    setClickMode,
    error,
    startWatch,
    stopWatch,
    setFromMapClick,
    applyFix,
  }
}

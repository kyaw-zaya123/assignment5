/** Leaflet.heat overlay for logistics risk intensity. */

import { useEffect } from 'react'
import { useMap } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet.heat'

export type HeatPoint = {
  latitude: number
  longitude: number
  intensity: number
}

type Props = {
  points: HeatPoint[]
  enabled?: boolean
  radius?: number
  blur?: number
  maxZoom?: number
  minOpacity?: number
}

export function RiskHeatLayer({
  points,
  enabled = true,
  radius = 28,
  blur = 22,
  maxZoom = 12,
  minOpacity = 0.35,
}: Props) {
  const map = useMap()

  useEffect(() => {
    if (!enabled || !points.length) return

    const latlngs: L.HeatLatLngTuple[] = points.map((p) => [
      p.latitude,
      p.longitude,
      Math.min(1, Math.max(0.05, p.intensity)),
    ])

    const heat = L.heatLayer(latlngs, {
      radius,
      blur,
      maxZoom,
      minOpacity,
      max: 1.0,
      gradient: {
        0.2: '#22c55e',
        0.4: '#eab308',
        0.65: '#f97316',
        0.85: '#ef4444',
        1.0: '#9f1239',
      },
    })

    heat.addTo(map)
    return () => {
      map.removeLayer(heat)
    }
  }, [map, points, enabled, radius, blur, maxZoom, minOpacity])

  return null
}

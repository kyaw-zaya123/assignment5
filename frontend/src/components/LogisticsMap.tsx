import { useEffect, useRef, useState } from 'react'
import {
  MapContainer,
  TileLayer,
  Circle,
  Popup,
  Polyline,
  Marker,
  LayersControl,
  GeoJSON,
  useMap,
  useMapEvents,
} from 'react-leaflet'
import L from 'leaflet'
import type { FeatureCollection, GeoJsonObject } from 'geojson'
import { apiOrigin, fetchWeatherAt, type MapOverview, type WeatherSnapshot } from '../api/client'
import { RiskHeatLayer } from './RiskHeatLayer'
import 'leaflet/dist/leaflet.css'

type Props = {
  overview: MapOverview | undefined
  route?: Array<[number, number]>
  /** Live driver pin (map click / watchPosition) */
  driverPosition?: { latitude: number; longitude: number; source?: string } | null
  /** When set, map clicks report lat/lon (driver GPS pin mode) */
  onMapClick?: (latitude: number, longitude: number) => void
  clickToSetGps?: boolean
}

function weatherIcon(wx?: WeatherSnapshot): string {
  const c = (wx?.condition || '').toLowerCase()
  if (wx?.storm || c.includes('thunder')) return '⛈️'
  if (c.includes('rain') || c.includes('drizzle') || (wx?.rainfall || 0) > 1) return '🌧️'
  if (c.includes('cloud')) return '☁️'
  if (c.includes('clear') || c.includes('sun')) return '☀️'
  if (c.includes('mist') || c.includes('fog') || c.includes('haze')) return '🌫️'
  return '🌤️'
}

function floodColor(risk?: string): string {
  if (risk === 'high') return '#be123c'
  if (risk === 'medium') return '#c2410c'
  return '#0f766e'
}

function vehicleDivIcon(plate: string, wx?: WeatherSnapshot, risk?: string | null) {
  const icon = weatherIcon(wx)
  const border =
    risk === 'HIGH' ? '#be123c' : risk === 'MEDIUM' ? '#c2410c' : floodColor(wx?.flood_risk)
  const temp =
    wx?.temperature != null && Number.isFinite(wx.temperature)
      ? `${Math.round(Number(wx.temperature))}°`
      : ''
  return L.divIcon({
    className: 'ml-vehicle-marker',
    html: `<div style="
      display:flex;flex-direction:column;align-items:center;gap:2px;
      transform:translate(-50%,-80%);
    ">
      <div style="
        background:#0f172a;color:#fff;font:600 10px/1 Source Sans 3,sans-serif;
        padding:3px 6px;border-radius:999px;white-space:nowrap;box-shadow:0 2px 8px rgba(15,23,42,.25);
      ">${plate}${temp ? ` · ${temp}` : ''}</div>
      <div style="
        width:36px;height:36px;border-radius:50%;background:#fff;
        border:3px solid ${border};display:grid;place-items:center;
        font-size:18px;box-shadow:0 4px 14px rgba(15,23,42,.28);
      ">${icon}</div>
    </div>`,
    iconSize: [0, 0],
    iconAnchor: [0, 0],
  })
}

function gateIcon(name: string, status: string) {
  const color = status === 'CLOSED' ? '#be123c' : status === 'WARNING' ? '#d97706' : '#059669'
  const safe = String(name || 'Gate').replace(/[<>&]/g, '')
  return L.divIcon({
    className: 'ml-gate-marker',
    html: `<div style="
      transform:translate(-50%,-90%);
      display:flex;flex-direction:column;align-items:center;gap:2px;
    ">
      <div style="
        background:#0f172a;color:#fff;font:700 10px/1.2 Source Sans 3,sans-serif;
        padding:3px 7px;border-radius:6px;white-space:nowrap;
        border:2px solid ${color};box-shadow:0 2px 8px rgba(15,23,42,.3);
      ">🛂 ${safe} · ${status}</div>
      <div style="
        width:12px;height:12px;border-radius:3px;background:${color};
        border:2px solid #fff;box-shadow:0 1px 6px rgba(0,0,0,.35);
      "></div>
    </div>`,
    iconSize: [0, 0],
    iconAnchor: [0, 0],
  })
}

function FitBounds({
  overview,
  route,
  border,
}: Props & { border: FeatureCollection | null }) {
  const map = useMap()
  useEffect(() => {
    const pts: L.LatLngExpression[] = []
    overview?.vehicles.forEach((v) => pts.push([v.latitude, v.longitude]))
    overview?.gates?.forEach((g) => {
      if (g.latitude != null && g.longitude != null) pts.push([g.latitude, g.longitude])
    })
    route?.forEach((p) => pts.push(p))
    if (pts.length >= 2) {
      map.fitBounds(L.latLngBounds(pts), { padding: [40, 40], maxZoom: 7 })
      return
    }
    if (pts.length === 1) {
      map.setView(pts[0], 7)
      return
    }
    if (border) {
      const layer = L.geoJSON(border as GeoJsonObject)
      const b = layer.getBounds()
      if (b.isValid()) {
        map.fitBounds(b, { padding: [28, 28], maxZoom: 7 })
      }
    }
  }, [map, overview, route, border])
  return null
}

function driverPinIcon() {
  return L.divIcon({
    className: 'ml-vehicle-marker',
    html: `<div style="
      width:18px;height:18px;border-radius:50%;
      background:#0f766e;border:3px solid #fff;
      box-shadow:0 0 0 2px #0f766e,0 2px 8px rgba(15,23,42,.35);
    "></div>`,
    iconSize: [18, 18],
    iconAnchor: [9, 9],
  })
}

function MapClickHandler({
  enabled,
  onMapClick,
}: {
  enabled?: boolean
  onMapClick?: (latitude: number, longitude: number) => void
}) {
  useMapEvents({
    click(e) {
      if (!enabled || !onMapClick) return
      onMapClick(e.latlng.lat, e.latlng.lng)
    },
  })
  return null
}

function clickPinIcon() {
  return L.divIcon({
    className: 'ml-weather-click',
    html: `<div style="
      width:14px;height:14px;border-radius:50%;
      background:#0369a1;border:2px solid #fff;
      box-shadow:0 1px 6px rgba(3,105,161,.45);
    "></div>`,
    iconSize: [14, 14],
    iconAnchor: [7, 7],
  })
}

/** Click any map location (including OSM-labelled towns) → reverse geocode + live weather */
function ClickAnywhereWeather({ enabled }: { enabled: boolean }) {
  const markerRef = useRef<L.Marker | null>(null)
  const [pin, setPin] = useState<{
    lat: number
    lon: number
    name?: string
    display?: string | null
    wx?: WeatherSnapshot
    loading?: boolean
    error?: string | null
  } | null>(null)

  useMapEvents({
    click(e) {
      if (!enabled) return
      const lat = e.latlng.lat
      const lon = e.latlng.lng
      setPin({ lat, lon, loading: true, error: null })
      void fetchWeatherAt(lat, lon)
        .then((data) => {
          setPin({
            lat,
            lon,
            name: data.name,
            display: data.display_name,
            wx: data.weather,
            loading: false,
            error: null,
          })
        })
        .catch((err) => {
          setPin({
            lat,
            lon,
            loading: false,
            error: err instanceof Error ? err.message : 'Weather lookup failed',
          })
        })
    },
  })

  useEffect(() => {
    if (!pin) return
    const t = window.setTimeout(() => {
      markerRef.current?.openPopup()
    }, 50)
    return () => window.clearTimeout(t)
  }, [pin?.lat, pin?.lon, pin?.loading, pin?.name, pin?.wx?.temperature])

  if (!pin) return null
  return (
    <Marker
      ref={markerRef}
      position={[pin.lat, pin.lon]}
      icon={clickPinIcon()}
      zIndexOffset={850}
    >
      <Popup>
        <div style={{ minWidth: 210 }}>
          <strong>{pin.name || 'Selected place'}</strong>
          {pin.display && (
            <div style={{ color: '#64748b', fontSize: 11, marginTop: 2 }}>{pin.display}</div>
          )}
          <div style={{ color: '#94a3b8', fontSize: 10, marginTop: 2 }}>
            {pin.lat.toFixed(4)}, {pin.lon.toFixed(4)}
          </div>
          {pin.loading && <p style={{ marginTop: 8, fontSize: 13 }}>Loading weather API…</p>}
          {pin.error && <p style={{ marginTop: 8, fontSize: 13, color: '#e11d48' }}>{pin.error}</p>}
          {!pin.loading && !pin.error && pin.wx && (
            <div style={{ marginTop: 8, fontSize: 13, lineHeight: 1.45 }}>
              <div>
                {weatherIcon(pin.wx)} <b>{pin.wx.condition || '—'}</b>
              </div>
              <div>
                Temp:{' '}
                {pin.wx.temperature != null ? `${Number(pin.wx.temperature).toFixed(1)}°C` : '—'}
              </div>
              <div>Rain: {pin.wx.rainfall != null ? `${pin.wx.rainfall} mm` : '—'}</div>
              <div>Humidity: {pin.wx.humidity != null ? `${pin.wx.humidity}%` : '—'}</div>
              <div>
                Flood risk:{' '}
                <strong style={{ color: floodColor(pin.wx.flood_risk) }}>
                  {pin.wx.flood_risk || '—'}
                </strong>
              </div>
              <div style={{ color: '#94a3b8', fontSize: 11, marginTop: 4 }}>
                via {pin.wx.provider || 'api'}
              </div>
            </div>
          )}
        </div>
      </Popup>
    </Marker>
  )
}

function PanToDriver({
  position,
}: {
  position?: { latitude: number; longitude: number } | null
}) {
  const map = useMap()
  useEffect(() => {
    if (!position) return
    map.panTo([position.latitude, position.longitude], { animate: true })
  }, [map, position?.latitude, position?.longitude])
  return null
}

function InvalidateOnResize() {
  const map = useMap()
  useEffect(() => {
    const el = map.getContainer()
    const refresh = () => map.invalidateSize()
    refresh()
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(refresh) : null
    ro?.observe(el)
    window.addEventListener('resize', refresh)
    return () => {
      ro?.disconnect()
      window.removeEventListener('resize', refresh)
    }
  }, [map])
  return null
}

function WeatherPopup({
  title,
  subtitle,
  wx,
}: {
  title: string
  subtitle?: string
  wx?: WeatherSnapshot
}) {
  if (!wx) {
    return (
      <div>
        <strong>{title}</strong>
        {subtitle && <div>{subtitle}</div>}
      </div>
    )
  }
  return (
    <div style={{ minWidth: 180 }}>
      <strong>{title}</strong>
      {subtitle && <div style={{ color: '#64748b', fontSize: 12 }}>{subtitle}</div>}
      <div style={{ marginTop: 8, fontSize: 13, lineHeight: 1.45 }}>
        <div>
          {weatherIcon(wx)} {wx.condition || '—'}
        </div>
        <div>Temp: {wx.temperature != null ? `${Number(wx.temperature).toFixed(1)}°C` : '—'}</div>
        <div>Rain: {wx.rainfall != null ? `${wx.rainfall} mm` : '—'}</div>
        <div>Humidity: {wx.humidity != null ? `${wx.humidity}%` : '—'}</div>
        <div>
          Flood risk: <strong style={{ color: floodColor(wx.flood_risk) }}>{wx.flood_risk}</strong>
        </div>
        <div style={{ color: '#94a3b8', fontSize: 11, marginTop: 4 }}>via {wx.provider}</div>
      </div>
    </div>
  )
}

function tileUrl(pathTemplate: string | undefined, fallbackLayer: string): string {
  if (pathTemplate?.startsWith('http')) {
    return pathTemplate
  }
  if (pathTemplate?.startsWith('/')) {
    return `${apiOrigin}${pathTemplate}`
  }
  return `${apiOrigin}/api/weather/tiles/${fallbackLayer}/{z}/{x}/{y}.png`
}

export function LogisticsMap({
  overview,
  route,
  driverPosition,
  onMapClick,
  clickToSetGps,
}: Props) {
  const center: [number, number] = driverPosition
    ? [driverPosition.latitude, driverPosition.longitude]
    : overview?.vehicles[0]
      ? [overview.vehicles[0].latitude, overview.vehicles[0].longitude]
      : [19.7, 96.1]

  const layersEnabled = overview?.weather_layers?.enabled ?? false
  const weatherProvider = overview?.weather_layers?.provider || 'stub'
  const tiles = overview?.weather_layers?.tiles
  const [border, setBorder] = useState<FeatureCollection | null>(null)
  const [showHeat, setShowHeat] = useState(false)

  useEffect(() => {
    let cancelled = false
    void fetch('/myanmar-border.geojson')
      .then((r) => {
        if (!r.ok) throw new Error('border fetch failed')
        return r.json()
      })
      .then((data: FeatureCollection) => {
        if (!cancelled) setBorder(data)
      })
      .catch(() => {
        if (!cancelled) setBorder(null)
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className={`relative h-full w-full ${clickToSetGps ? 'cursor-crosshair' : ''}`}>
      <MapContainer
        center={center}
        zoom={6}
        className="h-full w-full rounded-xl"
        scrollWheelZoom
      >
        <FitBounds overview={overview} route={route} border={border} />
        <InvalidateOnResize />
        <MapClickHandler enabled={!!clickToSetGps} onMapClick={onMapClick} />
        {/* When not pinning GPS, any map click looks up place name + live weather */}
        <ClickAnywhereWeather enabled={!clickToSetGps} />
        <PanToDriver position={driverPosition} />

        <LayersControl position="topright">
          <LayersControl.BaseLayer checked name="Streets">
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              maxZoom={19}
            />
          </LayersControl.BaseLayer>
          <LayersControl.BaseLayer name="Light">
            <TileLayer
              attribution="Tiles &copy; Esri"
              url="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}"
              maxZoom={16}
            />
          </LayersControl.BaseLayer>
          <LayersControl.BaseLayer name="Topographic">
            <TileLayer
              attribution='&copy; <a href="https://opentopomap.org">OpenTopoMap</a> (&copy; OSM, SRTM)'
              url="https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png"
              maxZoom={17}
            />
          </LayersControl.BaseLayer>
          <LayersControl.BaseLayer name="Satellite">
            <TileLayer
              attribution="Tiles &copy; Esri"
              url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
              maxZoom={19}
            />
          </LayersControl.BaseLayer>
          <LayersControl.BaseLayer name="Esri Streets">
            <TileLayer
              attribution="Tiles &copy; Esri"
              url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}"
              maxZoom={19}
            />
          </LayersControl.BaseLayer>

          {layersEnabled && (
            <>
              <LayersControl.Overlay checked name="Precipitation (OWM)">
                <TileLayer
                  url={tileUrl(tiles?.precipitation, 'precipitation_new')}
                  opacity={0.55}
                  zIndex={400}
                  attribution="OpenWeatherMap"
                />
              </LayersControl.Overlay>
              <LayersControl.Overlay name="Clouds (OWM)">
                <TileLayer
                  url={tileUrl(tiles?.clouds, 'clouds_new')}
                  opacity={0.45}
                  zIndex={401}
                  attribution="OpenWeatherMap"
                />
              </LayersControl.Overlay>
              <LayersControl.Overlay name="Temperature (OWM)">
                <TileLayer
                  url={tileUrl(tiles?.temp, 'temp_new')}
                  opacity={0.4}
                  zIndex={402}
                  attribution="OpenWeatherMap"
                />
              </LayersControl.Overlay>
              <LayersControl.Overlay name="Wind (OWM)">
                <TileLayer
                  url={tileUrl(tiles?.wind, 'wind_new')}
                  opacity={0.45}
                  zIndex={403}
                  attribution="OpenWeatherMap"
                />
              </LayersControl.Overlay>
            </>
          )}
        </LayersControl>

        <RiskHeatLayer
          points={overview?.risk_heatmap || []}
          enabled={showHeat}
          radius={22}
          blur={18}
          minOpacity={0.22}
        />

        {border && (
          <GeoJSON
            key="myanmar-border-ne10m"
            data={border}
            style={() => ({
              color: '#0f766e',
              weight: 2,
              opacity: 0.85,
              fillColor: '#14b8a6',
              fillOpacity: 0.03,
            })}
            interactive={false}
          />
        )}

        {overview?.risk_zones.map((z, i) => (
          <Circle
            key={`${z.name}-${i}`}
            center={[z.latitude, z.longitude]}
            radius={z.radius_km * 1000}
            pathOptions={{
              color: z.level === 'elevated' ? '#c2410c' : '#ca8a04',
              fillColor: z.level === 'elevated' ? '#fb923c' : '#facc15',
              fillOpacity: 0.1,
              weight: 1.5,
            }}
          >
            <Popup>
              Risk zone: {z.name} ({z.level})
            </Popup>
          </Circle>
        ))}

        {route && route.length > 1 && (
          <Polyline
            positions={route}
            pathOptions={{ color: '#1d4ed8', weight: 5, opacity: 0.92, lineJoin: 'round', lineCap: 'round' }}
          />
        )}

        {overview?.gates?.map((g) =>
          g.latitude != null && g.longitude != null ? (
            <Marker
              key={`gate-${g.id}`}
              position={[g.latitude, g.longitude]}
              icon={gateIcon(g.name, g.status)}
              zIndexOffset={700}
            >
              <Popup>
                <strong>{g.name}</strong>
                <div>{g.location}</div>
                <div>
                  Status: <b>{g.status}</b>
                </div>
                <div style={{ fontSize: 11, color: '#64748b', marginTop: 4 }}>Border gate</div>
              </Popup>
            </Marker>
          ) : null,
        )}

        {/* Hardcoded city badges removed — click OSM place names / any map point for live weather */}

        {overview?.vehicles.map((v) => (
          <Marker
            key={v.vehicle_id}
            position={[v.latitude, v.longitude]}
            icon={vehicleDivIcon(v.plate_number, v.weather, v.risk_level)}
            zIndexOffset={600}
          >
            <Popup>
              <div style={{ minWidth: 180 }}>
                <strong>{v.plate_number}</strong>
                <div>Shipment: {v.shipment_id || '—'}</div>
                <div>Driver: {v.driver || '—'}</div>
                <div>Status: {v.shipment_status || v.status}</div>
                <div>Risk: {v.risk_level || 'n/a'}</div>
                <WeatherPopup title="Weather" wx={v.weather} />
              </div>
            </Popup>
          </Marker>
        ))}

        {driverPosition && (
          <Marker
            position={[driverPosition.latitude, driverPosition.longitude]}
            icon={driverPinIcon()}
            zIndexOffset={900}
          >
            <Popup>
              <strong>Your GPS pin</strong>
              <div>
                {driverPosition.latitude.toFixed(5)}, {driverPosition.longitude.toFixed(5)}
              </div>
              {driverPosition.source && <div>Source: {driverPosition.source}</div>}
              <div style={{ fontSize: 11, color: '#64748b' }}>
                {clickToSetGps ? 'Click map to move pin' : 'Enable click-to-pin to relocate'}
              </div>
            </Popup>
          </Marker>
        )}
      </MapContainer>

      <div className="pointer-events-none absolute bottom-3 left-3 z-[1000] max-w-[240px] rounded-lg border border-slate-200/80 bg-white/95 px-3 py-2 text-[11px] shadow-md backdrop-blur">
        <div className="mb-1 font-semibold text-slate-800">Map legend</div>
        <div className="text-slate-600">Border gates labeled · vehicles · road route</div>
        <div className="text-slate-600">
          Cities: OSM names — <b>click anywhere</b> for live weather
        </div>
        <div className="mt-1 text-slate-500">
          {(overview?.gates || []).length} gates · {(overview?.risk_heatmap || []).length} heat pts
        </div>
        {!layersEnabled && weatherProvider === 'openweather' && (
          <div className="mt-1 text-amber-700">OWM tiles need OPENWEATHER_API_KEY</div>
        )}
        <div className="mt-2 flex flex-wrap gap-1.5">
          <button
            type="button"
            className="pointer-events-auto rounded border border-slate-200 bg-white px-2 py-1 text-[10px] font-semibold text-slate-700 hover:bg-slate-50"
            onClick={() => setShowHeat((v) => !v)}
          >
            {showHeat ? 'Hide heatmap' : 'Show heatmap'}
          </button>
        </div>
      </div>
    </div>
  )
}

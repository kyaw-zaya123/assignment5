import type { Shipment } from '../api/client'

type Props = {
  shipments: Shipment[]
  onAssess: (s: Shipment) => void
  busyId?: number | null
}

function riskClass(level?: string | null) {
  const v = (level || '').toUpperCase()
  if (v === 'HIGH') return 'text-rose-700 bg-rose-50'
  if (v === 'MEDIUM') return 'text-amber-800 bg-amber-50'
  if (v === 'LOW') return 'text-emerald-800 bg-emerald-50'
  return 'text-slate-600 bg-slate-100'
}

export function ShipmentTable({ shipments, onAssess, busyId }: Props) {
  return (
    <div className="overflow-auto">
      <table className="min-w-full text-sm">
        <thead className="text-left text-slate-500 border-b border-slate-200">
          <tr>
            <th className="py-2 pr-3 font-medium">Tracking</th>
            <th className="py-2 pr-3 font-medium">Vehicle</th>
            <th className="py-2 pr-3 font-medium">Route</th>
            <th className="py-2 pr-3 font-medium">Status</th>
            <th className="py-2 pr-3 font-medium">Risk</th>
            <th className="py-2 font-medium" />
          </tr>
        </thead>
        <tbody>
          {shipments.map((s) => (
            <tr key={s.id} className="border-b border-slate-100 align-top">
              <td className="py-2.5 pr-3 font-semibold text-slate-800">{s.tracking_number}</td>
              <td className="py-2.5 pr-3">{s.vehicle_id ?? '—'}</td>
              <td className="py-2.5 pr-3">
                {s.origin} → {s.destination}
              </td>
              <td className="py-2.5 pr-3 capitalize">{s.status.replace('_', ' ')}</td>
              <td className="py-2.5 pr-3">
                <span className={`px-2 py-0.5 rounded text-xs font-semibold ${riskClass(s.latest_risk_level)}`}>
                  {s.latest_risk_level ?? 'n/a'}
                  {s.latest_risk_score != null ? ` (${s.latest_risk_score})` : ''}
                </span>
              </td>
              <td className="py-2.5">
                <button
                  type="button"
                  disabled={busyId === s.id}
                  onClick={() => onAssess(s)}
                  className="text-xs font-semibold text-teal-800 hover:underline disabled:opacity-50"
                >
                  {busyId === s.id ? 'Assessing…' : 'Assess'}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

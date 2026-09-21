import type { AlertItem } from '../api/client'

type Props = {
  alerts: AlertItem[]
}

export function AlertPanel({ alerts }: Props) {
  if (!alerts.length) {
    return <p className="text-sm text-slate-500">No risk alerts yet. Run an assessment on SH001.</p>
  }
  return (
    <ul className="space-y-2 overflow-auto">
      {alerts.map((a) => (
        <li key={a.id} className="rounded-lg border border-slate-200 bg-white p-3 text-sm">
          <div className="flex items-center justify-between gap-2">
            <span className="font-semibold text-slate-800">{a.shipment_id}</span>
            <span className="text-xs font-bold uppercase text-rose-700">{a.risk_level}</span>
          </div>
          <p className="mt-1 text-slate-600 line-clamp-3">{a.explanation}</p>
          <p className="mt-1 text-xs text-slate-400">{a.timestamp}</p>
        </li>
      ))}
    </ul>
  )
}

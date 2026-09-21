import { useEffect, useState } from 'react'
import { apiOrigin, type AiResponse } from '../api/client'

type Props = {
  result: AiResponse | null
}

export function EvidencePanel({ result }: Props) {
  if (!result) {
    return <p className="text-sm text-slate-500">Run an AI risk query to see evidence sources.</p>
  }
  const structured = result.evidence_structured || []
  const flat = result.evidence || []
  return (
    <div className="space-y-3 text-sm">
      <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
        <div className="flex items-center justify-between gap-2">
          <span className="font-semibold">{result.shipment_id}</span>
          <span className="text-xs font-bold uppercase text-teal-800">
            {result.risk} · {result.risk_score}
          </span>
        </div>
        <p className="mt-2 text-slate-700 whitespace-pre-wrap">{result.answer}</p>
        {result.recommendation && (
          <p className="mt-2">
            <span className="font-semibold">Recommendation:</span> {result.recommendation}
          </p>
        )}
      </div>
      <div>
        <h3 className="mb-2 font-semibold text-slate-800">Evidence</h3>
        <ul className="space-y-2">
          {structured.length > 0
            ? structured.map((e, i) => (
                <li key={i} className="rounded border border-slate-100 bg-white p-2">
                  <div className="text-xs font-semibold uppercase text-teal-800">{e.source}</div>
                  <div className="text-slate-600">{e.detail}</div>
                </li>
              ))
            : flat.map((e, i) => (
                <li key={i} className="rounded border border-slate-100 bg-white p-2 text-slate-600">
                  {String(e)}
                </li>
              ))}
        </ul>
      </div>
      {result.sources?.length > 0 && (
        <div>
          <h3 className="mb-2 font-semibold text-slate-800">OSINT sources</h3>
          <ul className="space-y-2">
            {result.sources.slice(0, 4).map((s, i) => (
              <li key={i} className="rounded border border-slate-100 bg-white p-2 text-xs text-slate-600">
                <div className="text-slate-400">
                  {s.network} · {s.date}
                </div>
                <div>{s.text}</div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

type TimelineEvent = {
  id: number
  event_type: string
  description?: string
  location?: string | null
  latitude?: number | null
  longitude?: number | null
  timestamp?: string | null
  document_name?: string | null
  content_type?: string | null
  file_size?: number | null
  document_url?: string | null
}

function formatWhen(ts?: string | null): string {
  if (!ts) return ''
  try {
    const d = new Date(ts)
    if (Number.isNaN(d.getTime())) return ts
    return d.toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  } catch {
    return ts
  }
}

function eventTone(type: string): string {
  const u = (type || '').toUpperCase()
  if (u === 'DELAYED' || u.includes('PROBLEM')) return 'border-rose-200 bg-rose-50/80'
  if (u === 'DELIVERED') return 'border-emerald-200 bg-emerald-50/80'
  if (u === 'GPS' || u === 'DOCUMENT') return 'border-sky-200 bg-sky-50/70'
  if (u === 'CHECKPOINT' || u === 'CUSTOMS') return 'border-amber-200 bg-amber-50/70'
  return 'border-slate-100 bg-slate-50/80'
}

export function TimelinePanel({
  shipmentId,
  loader,
  refreshKey = 0,
  showHistory = true,
}: {
  shipmentId: number | null
  loader: (id: number) => Promise<any>
  refreshKey?: number
  /** Show reverse-chronological action history (default true) */
  showHistory?: boolean
}) {
  const [data, setData] = useState<any>(null)

  useEffect(() => {
    if (!shipmentId) return
    void loader(shipmentId).then(setData).catch(() => setData(null))
  }, [shipmentId, loader, refreshKey])

  if (!shipmentId) return <p className="text-sm text-slate-500">Select a shipment for timeline.</p>
  if (!data) return <p className="text-sm text-slate-500">Loading timeline…</p>

  const events: TimelineEvent[] = Array.isArray(data.events) ? data.events : []
  // Newest first for action history
  const history = [...events].reverse()

  return (
    <div className="text-sm">
      <div className="mb-3 font-semibold">
        {data.tracking_number} · {data.status}
      </div>
      <ol className="space-y-2">
        {(data.steps || []).map((s: any) => (
          <li key={s.step} className="flex items-center gap-2">
            <span
              className={
                s.state === 'done'
                  ? 'text-emerald-600'
                  : s.state === 'current'
                    ? 'text-amber-600'
                    : 'text-slate-300'
              }
            >
              {s.state === 'done' ? '✓' : s.state === 'current' ? '●' : '○'}
            </span>
            <span className={s.state === 'todo' ? 'text-slate-400' : 'text-slate-800'}>{s.step}</span>
          </li>
        ))}
      </ol>

      {showHistory && (
        <div className="mt-4 border-t border-slate-100 pt-3">
          <div className="mb-2 flex items-center justify-between gap-2">
            <h3 className="text-xs font-bold uppercase tracking-wide text-slate-700">Action history</h3>
            <span className="text-[10px] text-slate-400">{history.length} events</span>
          </div>
          {history.length === 0 ? (
            <p className="text-xs text-slate-500">No actions yet — Start Trip to begin.</p>
          ) : (
            <ul className="space-y-2 text-xs text-slate-600">
              {history.map((e) => (
                <li key={e.id} className={`rounded-lg border px-2.5 py-2 ${eventTone(e.event_type)}`}>
                  <div className="flex flex-wrap items-baseline justify-between gap-x-2 gap-y-0.5">
                    <span className="font-bold uppercase tracking-wide text-slate-800">{e.event_type}</span>
                    {e.timestamp && (
                      <time className="text-[10px] font-medium text-slate-500" dateTime={e.timestamp}>
                        {formatWhen(e.timestamp)}
                      </time>
                    )}
                  </div>
                  {e.description && <p className="mt-0.5 text-slate-700">{e.description}</p>}
                  <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[10px] text-slate-500">
                    {e.location && <span>📍 {e.location}</span>}
                    {e.latitude != null && e.longitude != null && (
                      <span>
                        GPS {Number(e.latitude).toFixed(4)}, {Number(e.longitude).toFixed(4)}
                      </span>
                    )}
                  </div>
                  {e.document_name && (
                    <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[11px]">
                      <span className="rounded bg-white px-1.5 py-0.5 font-medium text-teal-800">
                        📎 {e.document_name}
                        {e.file_size != null ? ` · ${e.file_size} B` : ''}
                      </span>
                      {e.document_url && (
                        <a
                          className="font-semibold text-teal-700 underline"
                          href={`${apiOrigin}${e.document_url}`}
                          target="_blank"
                          rel="noreferrer"
                        >
                          Open / download
                        </a>
                      )}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

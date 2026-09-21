import { type FormEvent, useState } from 'react'
import type { AiResponse } from '../api/client'

type Props = {
  onAsk: (question: string) => Promise<void>
  result: AiResponse | null
  loading: boolean
  error: string | null
}

export function AiPanel({ onAsk, result, loading, error }: Props) {
  const [q, setQ] = useState('Is shipment SH001 safe?')

  async function submit(e: FormEvent) {
    e.preventDefault()
    await onAsk(q)
  }

  return (
    <div className="flex h-full flex-col gap-3">
      <form onSubmit={submit} className="flex flex-col gap-2">
        <textarea
          value={q}
          onChange={(e) => setQ(e.target.value)}
          rows={2}
          className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-teal-600"
          placeholder="Ask the logistics decision agent…"
        />
        <button
          type="submit"
          disabled={loading || !q.trim()}
          className="rounded-lg bg-teal-700 px-3 py-2 text-sm font-semibold text-white hover:bg-teal-800 disabled:opacity-50"
        >
          {loading ? 'Thinking…' : 'Ask agent'}
        </button>
      </form>
      {error && <p className="text-sm text-rose-600">{error}</p>}
      {result && (
        <div className="space-y-2 overflow-auto text-sm">
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
            <div className="mb-1 flex items-center justify-between gap-2">
              <span className="font-semibold text-slate-800">{result.shipment_id}</span>
              <span className="text-xs font-bold uppercase tracking-wide text-teal-800">
                {result.risk} · {result.risk_score}
              </span>
            </div>
            <p className="text-slate-700 whitespace-pre-wrap">{result.answer}</p>
            {result.recommendation && (
              <p className="mt-2 text-slate-800">
                <span className="font-semibold">Recommendation:</span> {result.recommendation}
              </p>
            )}
          </div>
          {result.reasons?.length > 0 && (
            <ul className="list-disc pl-5 text-slate-600">
              {result.reasons.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          )}
          {result.sources?.length > 0 && (
            <div>
              <p className="mb-1 font-semibold text-slate-700">OSINT sources</p>
              <ul className="space-y-2">
                {result.sources.map((s, i) => (
                  <li key={i} className="rounded border border-slate-100 bg-white p-2 text-xs text-slate-600">
                    <div className="mb-1 text-slate-500">
                      {s.network} · {s.date} · {s.category}
                    </div>
                    <div>{s.text}</div>
                    {s.link && (
                      <a className="text-teal-700 underline" href={s.link} target="_blank" rel="noreferrer">
                        source
                      </a>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

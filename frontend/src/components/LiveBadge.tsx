import { formatPollAge } from '../hooks/usePolling'

/** Compact live-polling indicator for dashboard headers. */
export function LiveBadge({
  lastUpdated,
  intervalSec = 8,
}: {
  lastUpdated: Date | null
  intervalSec?: number
}) {
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/10 px-2.5 py-1 text-[11px] font-semibold text-emerald-800 ring-1 ring-emerald-500/25"
      title={`Auto-refresh every ${intervalSec}s while this tab is open`}
    >
      <span className="relative flex h-1.5 w-1.5">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
        <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-500" />
      </span>
      Live · {formatPollAge(lastUpdated)}
    </span>
  )
}

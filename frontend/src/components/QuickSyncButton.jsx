import { useEffect, useRef, useState } from 'react'
import { runSync } from '../api'

// One click, no options - runs the exact same default incremental live
// sync (no --days/--full override, the fixed 7-day lookback window
// scripts/sync-google-health.php already treats as its normal "routine
// sync" mode) that the full Sync page's own "Live sync" button runs by
// default. There's no true "time of last successful sync" tracked in this
// app - this fixed window, with its already-built dedup/cross-source
// rules, IS the established "since last sync" behavior today. The full
// Sync page (menu -> Sync) is still there for anyone who wants --full,
// --days=N, a replay, or the detailed output log.
export default function QuickSyncButton() {
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState(null) // { ok: boolean, message: string } | null
  const timeoutRef = useRef(null)

  useEffect(() => () => clearTimeout(timeoutRef.current), [])

  async function handleClick() {
    if (busy) return
    setBusy(true)
    setStatus(null)
    clearTimeout(timeoutRef.current)
    try {
      const result = await runSync({ mode: 'live' })
      setStatus(result.success ? { ok: true, message: 'Synced' } : { ok: false, message: `Sync failed (exit ${result.exitCode})` })
    } catch (err) {
      setStatus({ ok: false, message: err.message })
    } finally {
      setBusy(false)
      timeoutRef.current = setTimeout(() => setStatus(null), 5000)
    }
  }

  return (
    <span className="quick-sync">
      <button
        type="button"
        className={busy ? 'quick-sync-button busy' : 'quick-sync-button'}
        onClick={handleClick}
        disabled={busy}
        aria-label="Quick sync"
        title="Sync new data since last sync"
      >
        <svg viewBox="0 0 16 16" width="18" height="18" aria-hidden="true">
          <path
            d="M13.5 8a5.5 5.5 0 0 1-9.16 4.1M2.5 8a5.5 5.5 0 0 1 9.16-4.1"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.6"
          />
          <path d="M11 2.5v3.4h-3.4" fill="none" stroke="currentColor" strokeWidth="1.6" />
          <path d="M5 13.5v-3.4h3.4" fill="none" stroke="currentColor" strokeWidth="1.6" />
        </svg>
      </button>
      {status && <span className={status.ok ? 'quick-sync-status ok' : 'quick-sync-status error'}>{status.message}</span>}
    </span>
  )
}

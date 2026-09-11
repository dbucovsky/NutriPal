import { useEffect, useRef, useState } from 'react'
import { runSync } from '../api'

// One click, no options - runs mode: 'quick' (scripts/sync-google-health.php
// --quick, see its own docblock), which windows each category off
// users.last_sync_completed_at instead of a flat "last 7 days" every time -
// nutrition/weight get a 4-day lookback, everything else 4 hours, widened
// to 7 days across the board for the first quick sync after a login. The
// full Sync page (menu -> Sync) is still there for anyone who wants --full,
// --days=N, a replay, or the detailed output log - that page's own default
// "Live sync" button is untouched by this and still runs the old flat
// incremental window.
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
      const result = await runSync({ mode: 'quick' })
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

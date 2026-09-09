import { useEffect, useRef, useState } from 'react'
import { runSync, getSyncRuns, getSyncProgress, importHealthConnect } from '../api'

function formatDuration(seconds) {
  if (seconds == null) return null
  if (seconds < 60) return `${Math.round(seconds)}s`
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  return `${m}m ${s}s`
}

function formatRunLabel(run) {
  const started = run.startedAt ? new Date(run.startedAt).toLocaleString() : run.runId
  const duration = formatDuration(run.durationSeconds)
  return `${started} — ${run.window}${duration ? ` — took ${duration}` : ''}`
}

// Ticks a client-side elapsed-time counter while a synchronous run-sync.php/
// import-hc.php request is in flight. Deliberately not backed by polling a
// progress endpoint: PHP's built-in dev server (php -S, what
// start-services.ps1 runs) is single-threaded, so it can't serve any other
// request while it's still busy with the blocking one - confirmed directly
// (a request sent mid-import just queued for the entire run and only
// returned once it finished). The one-time "how long did this take last
// time" estimate is instead fetched up front, before the blocking request
// fires - see handleLiveSync/handleReplay/handleImport below.
function useElapsedTimer(active) {
  const [elapsed, setElapsed] = useState(0)
  const startRef = useRef(null)

  useEffect(() => {
    if (!active) {
      setElapsed(0)
      startRef.current = null
      return
    }
    startRef.current = Date.now()
    const timer = setInterval(() => {
      setElapsed((Date.now() - startRef.current) / 1000)
    }, 1000)
    return () => clearInterval(timer)
  }, [active])

  return elapsed
}

function ProgressPanel({ active, estimatedSeconds }) {
  const elapsed = useElapsedTimer(active)
  if (!active) return null

  const pct = estimatedSeconds ? Math.min(95, (elapsed / estimatedSeconds) * 100) : null

  return (
    <div className="sync-progress">
      <div className="sync-progress-bar-track">
        <div
          className={pct === null ? 'sync-progress-bar indeterminate' : 'sync-progress-bar'}
          style={pct !== null ? { width: `${pct}%` } : undefined}
        />
      </div>
      <p className="text-muted">
        Elapsed {formatDuration(elapsed)}
        {estimatedSeconds != null
          ? ` — last similar run took ${formatDuration(estimatedSeconds)} (rough estimate, not exact)`
          : ' — no estimate available yet'}
      </p>
    </div>
  )
}

export default function Sync() {
  const [runs, setRuns] = useState([])
  const [replayRunId, setReplayRunId] = useState('')
  const [days, setDays] = useState(7)
  const [full, setFull] = useState(false)
  const [debug, setDebug] = useState(false)
  const [hcPath, setHcPath] = useState('')

  const [busy, setBusy] = useState(null) // 'live' | 'replay' | 'import' | null
  const [result, setResult] = useState(null) // { success, exitCode, output }
  const [error, setError] = useState(null)
  const [estimatedSeconds, setEstimatedSeconds] = useState(null)

  async function fetchEstimate(progressType) {
    try {
      const data = await getSyncProgress(progressType)
      setEstimatedSeconds(data.estimatedSeconds)
    } catch {
      setEstimatedSeconds(null)
    }
  }

  useEffect(() => {
    getSyncRuns()
      .then(setRuns)
      .catch(() => {
        // Non-fatal: replay dropdown just stays empty.
      })
  }, [result])

  async function handleLiveSync() {
    setBusy('live')
    setError(null)
    setResult(null)
    await fetchEstimate('sync')
    try {
      const body = { mode: 'live', debug }
      if (full) {
        body.full = true
      } else {
        body.days = Number(days)
      }
      setResult(await runSync(body))
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(null)
    }
  }

  async function handleReplay() {
    if (!replayRunId) return
    setBusy('replay')
    setError(null)
    setResult(null)
    await fetchEstimate('sync')
    try {
      setResult(await runSync({ mode: 'replay', replayRunId, debug }))
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(null)
    }
  }

  async function handleImport() {
    if (!hcPath.trim()) return
    setBusy('import')
    setError(null)
    setResult(null)
    await fetchEstimate('import')
    try {
      setResult(await importHealthConnect(hcPath.trim()))
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(null)
    }
  }

  const anyBusy = busy !== null

  return (
    <div className="sync">
      <section className="sync-section">
        <h3>Live sync</h3>
        <label>
          <input
            type="checkbox"
            checked={full}
            onChange={(e) => setFull(e.target.checked)}
            disabled={anyBusy}
          />
          Full history
        </label>
        {!full && (
          <label>
            Days:{' '}
            <input
              type="number"
              min="1"
              max="3650"
              value={days}
              onChange={(e) => setDays(e.target.value)}
              disabled={anyBusy}
            />
          </label>
        )}
        <label>
          <input
            type="checkbox"
            checked={debug}
            onChange={(e) => setDebug(e.target.checked)}
            disabled={anyBusy}
          />
          Debug trace
        </label>
        <button onClick={handleLiveSync} disabled={anyBusy}>
          {busy === 'live' ? 'Syncing…' : 'Run live sync'}
        </button>
        <ProgressPanel active={busy === 'live'} estimatedSeconds={estimatedSeconds} />
      </section>

      <section className="sync-section">
        <h3>Replay a prior run</h3>
        <select
          value={replayRunId}
          onChange={(e) => setReplayRunId(e.target.value)}
          disabled={anyBusy}
          className="sync-replay-select"
        >
          <option value="">Select a run…</option>
          {runs.map((run) => (
            <option key={run.runId} value={run.runId}>
              {formatRunLabel(run)}
            </option>
          ))}
        </select>
        <button onClick={handleReplay} disabled={anyBusy || !replayRunId}>
          {busy === 'replay' ? 'Replaying…' : 'Run replay'}
        </button>
        <ProgressPanel active={busy === 'replay'} estimatedSeconds={estimatedSeconds} />
      </section>

      <section className="sync-section">
        <h3>Import Health Connect export</h3>
        <input
          type="text"
          placeholder="Path to health_connect_export.db on this machine"
          value={hcPath}
          onChange={(e) => setHcPath(e.target.value)}
          disabled={anyBusy}
          className="sync-path-input"
        />
        <button onClick={handleImport} disabled={anyBusy || !hcPath.trim()}>
          {busy === 'import' ? 'Importing…' : 'Run import'}
        </button>
        <ProgressPanel active={busy === 'import'} estimatedSeconds={estimatedSeconds} />
      </section>

      {error && <p className="login-error">{error}</p>}

      {result && (
        <section className="sync-section">
          <h3>{result.success ? 'Done' : `Failed (exit ${result.exitCode})`}</h3>
          <pre className="sync-output">{result.output}</pre>
        </section>
      )}
    </div>
  )
}

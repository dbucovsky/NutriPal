import { useEffect, useState } from 'react'
import { getSleep } from '../api'
import { formatLocalTime, formatHoursMinutes } from '../dateUtils'
import MultiDay from './MultiDay'

const STAGE_COLORS = {
  AWAKE: '#d9822b',
  LIGHT: '#7fb3d5',
  DEEP: '#2f5f8f',
  REM: '#8e5fb3',
  ASLEEP: '#5fa5a0',
  RESTLESS: '#c9a227',
  UNSPECIFIED: '#999',
}

// The user's own target bands for REM/Deep sleep - only these two stages
// have a meaningful "was this enough" answer; the others don't get a badge.
const QUALITY_STAGES = new Set(['REM', 'DEEP'])

function sleepQuality(stageType, totalMinutes) {
  if (!QUALITY_STAGES.has(stageType)) return null
  if (totalMinutes < 60) return { label: 'bad', className: 'quality-bad' }
  if (totalMinutes < 75) return { label: 'adequate', className: 'quality-adequate' }
  if (totalMinutes < 90) return { label: 'ok', className: 'quality-ok' }
  return { label: 'good', className: 'quality-good' }
}

function DayBody({ sessions }) {
  return (
    <>
      {sessions.map((session) => {
        const totalMinutes =
          session.stage_totals.reduce((sum, s) => sum + s.minutes, 0) || session.duration_minutes
        return (
          <section key={session.id} className="sleep-session">
            <div className="sleep-session-header">
              <strong>{formatHoursMinutes(session.duration_minutes)}</strong>
              <span className="text-muted">
                {formatLocalTime(session.start_time)} – {formatLocalTime(session.end_time)}
              </span>
              {session.sleep_type && <span className="text-muted">{session.sleep_type}</span>}
              {session.main_sleep === true && <span className="text-muted">main sleep</span>}
            </div>

            {session.stages.length > 0 && (
              <>
                {/* Segments in chronological order (not merged by type) so
                    the bar shows the actual progression through the
                    night's sleep cycles, not just total time per stage. */}
                <div className="stage-bar">
                  {session.stages.map((s, i) => (
                    <div
                      key={i}
                      className="stage-segment"
                      style={{
                        width: `${(s.minutes / totalMinutes) * 100}%`,
                        backgroundColor: STAGE_COLORS[s.stage_type] || '#999',
                      }}
                      title={`${formatLocalTime(s.start_time)} ${s.stage_type}: ${formatHoursMinutes(s.minutes)}`}
                    />
                  ))}
                </div>
                <ol className="stage-segment-list">
                  {session.stages.map((s, i) => (
                    <li key={i}>
                      <span
                        className="stage-swatch"
                        style={{ backgroundColor: STAGE_COLORS[s.stage_type] || '#999' }}
                      />
                      <span className="text-muted">{formatLocalTime(s.start_time)}</span> {s.stage_type}{' '}
                      <span className="text-muted">{formatHoursMinutes(s.minutes)}</span>
                    </li>
                  ))}
                </ol>
                <div className="stage-legend">
                  {session.stage_totals.map((s) => {
                    const quality = sleepQuality(s.stage_type, s.minutes)
                    return (
                      <span key={s.stage_type} className="stage-legend-item">
                        <span
                          className="stage-swatch"
                          style={{ backgroundColor: STAGE_COLORS[s.stage_type] || '#999' }}
                        />
                        {s.stage_type} {formatHoursMinutes(s.minutes)}
                        {quality && <span className={`quality-badge ${quality.className}`}>{quality.label}</span>}
                      </span>
                    )
                  })}
                </div>
              </>
            )}
          </section>
        )
      })}
    </>
  )
}

export default function Sleep({ userId, view }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getSleep(userId, view)
      .then((result) => {
        if (!cancelled) setData(result)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [userId, view.type, view.date, view.endDate])

  return (
    <div className="sleep">
      <p className="page-note">Showing sleep that ended on this day.</p>

      {loading && <p>Loading…</p>}
      {error && <p className="login-error">{error}</p>}

      {data && !loading && (
        <>
          {data.days.length === 0 && <p>No sleep logged for this period.</p>}
          <MultiDay days={data.days} renderDay={(day) => <DayBody key={day.date} {...day} />} />
        </>
      )}
    </div>
  )
}

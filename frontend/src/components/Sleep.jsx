import { useEffect, useState } from 'react'
import { getSleep } from '../api'
import { todayLocal, formatLocalTime } from '../dateUtils'
import DateNav from './DateNav'

const STAGE_COLORS = {
  AWAKE: '#d9822b',
  LIGHT: '#7fb3d5',
  DEEP: '#2f5f8f',
  REM: '#8e5fb3',
  ASLEEP: '#5fa5a0',
  RESTLESS: '#c9a227',
  UNSPECIFIED: '#999',
}

function formatDuration(minutes) {
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return `${h}h ${m}m`
}

export default function Sleep({ userId }) {
  const [date, setDate] = useState(todayLocal())
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getSleep(userId, date)
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
  }, [userId, date])

  return (
    <div className="sleep">
      <DateNav date={date} onChange={setDate} />
      <p className="page-note">Showing sleep that ended on this day.</p>

      {loading && <p>Loading…</p>}
      {error && <p className="login-error">{error}</p>}

      {data && !loading && (
        <>
          {data.sessions.length === 0 && <p>No sleep logged for this day.</p>}

          {data.sessions.map((session) => {
            const totalMinutes = session.stages.reduce((sum, s) => sum + s.minutes, 0) || session.duration_minutes
            return (
              <section key={session.id} className="sleep-session">
                <div className="sleep-session-header">
                  <strong>{formatDuration(session.duration_minutes)}</strong>
                  <span className="text-muted">
                    {formatLocalTime(session.start_time)} – {formatLocalTime(session.end_time)}
                  </span>
                  {session.sleep_type && <span className="text-muted">{session.sleep_type}</span>}
                  {session.main_sleep === true && <span className="text-muted">main sleep</span>}
                </div>

                {session.stages.length > 0 && (
                  <>
                    <div className="stage-bar">
                      {session.stages.map((s) => (
                        <div
                          key={s.stage_type}
                          className="stage-segment"
                          style={{
                            width: `${(s.minutes / totalMinutes) * 100}%`,
                            backgroundColor: STAGE_COLORS[s.stage_type] || '#999',
                          }}
                          title={`${s.stage_type}: ${s.minutes}m`}
                        />
                      ))}
                    </div>
                    <div className="stage-legend">
                      {session.stages.map((s) => (
                        <span key={s.stage_type} className="stage-legend-item">
                          <span
                            className="stage-swatch"
                            style={{ backgroundColor: STAGE_COLORS[s.stage_type] || '#999' }}
                          />
                          {s.stage_type} {s.minutes}m
                        </span>
                      ))}
                    </div>
                  </>
                )}
              </section>
            )
          })}
        </>
      )}
    </div>
  )
}

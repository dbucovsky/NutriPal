import { useEffect, useState } from 'react'
import { getExercise } from '../api'
import { formatLocalTime } from '../dateUtils'

function stat(value, unit = '') {
  return value === null || value === undefined ? '—' : `${value}${unit}`
}

export default function Exercise({ userId, date }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getExercise(userId, date)
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
    <div className="exercise">
      {loading && <p>Loading…</p>}
      {error && <p className="login-error">{error}</p>}

      {data && !loading && (
        <>
          {data.sessions.length === 0 && <p>No exercise logged this day.</p>}

          <ul className="exercise-list">
            {data.sessions.map((session) => (
              <li key={session.id} className="exercise-entry">
                <div className="exercise-entry-header">
                  <strong>{session.activity_name || session.activity_type || 'Activity'}</strong>
                  <span className="text-muted">
                    {formatLocalTime(session.start_time)} – {formatLocalTime(session.end_time)}
                  </span>
                </div>
                <div className="exercise-entry-stats">
                  {stat(session.duration_minutes, ' min')} · {stat(session.calories, ' kcal')} ·{' '}
                  {session.distance !== null
                    ? `${stat(session.distance)} ${session.distance_unit ?? ''}`
                    : '—'}{' '}
                  · {stat(session.steps, ' steps')} · avg HR {stat(session.average_heart_rate, ' bpm')}
                  {session.has_gps && ' · GPS'}
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}

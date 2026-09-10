import { useEffect, useState } from 'react'
import { getExercise } from '../api'
import { formatLocalTime } from '../dateUtils'
import MultiDay from './MultiDay'

function stat(value, unit = '') {
  return value === null || value === undefined ? '—' : `${value}${unit}`
}

function daySummary(day) {
  const count = day.sessions.length
  const totalMinutes = day.sessions.reduce((sum, s) => sum + (s.duration_minutes || 0), 0)
  const totalCalories = day.sessions.reduce((sum, s) => sum + (s.calories || 0), 0)
  const sessionWord = count === 1 ? 'session' : 'sessions'
  return `${count} ${sessionWord} · ${totalMinutes} min · ${totalCalories} kcal`
}

function DayBody({ sessions }) {
  return (
    <ul className="exercise-list">
      {sessions.map((session) => (
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
  )
}

export default function Exercise({ userId, view }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getExercise(userId, view)
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
    <div className="exercise">
      {loading && <p>Loading…</p>}
      {error && <p className="login-error">{error}</p>}

      {data && !loading && (
        <>
          {data.days.length === 0 && <p>No exercise logged for this period.</p>}
          <MultiDay
            days={data.days}
            renderDay={(day) => <DayBody key={day.date} {...day} />}
            renderSummary={daySummary}
          />
        </>
      )}
    </div>
  )
}

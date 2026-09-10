import { useEffect, useState } from 'react'
import { getWeight } from '../api'
import { formatLocalTime } from '../dateUtils'
import MultiDay from './MultiDay'

function DayBody({ readings }) {
  return (
    <ul className="weight-list">
      {readings.map((reading) => (
        <li key={reading.id} className="weight-entry">
          <strong>{reading.value_lb} lb</strong>
          <span className="text-muted">{formatLocalTime(reading.reading_time)}</span>
        </li>
      ))}
    </ul>
  )
}

export default function Weight({ userId, view }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getWeight(userId, view)
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
    <div className="weight">
      {loading && <p>Loading…</p>}
      {error && <p className="login-error">{error}</p>}

      {data && !loading && (
        <>
          {data.days.length === 0 && <p>No weight logged for this period.</p>}
          <MultiDay days={data.days} renderDay={(day) => <DayBody key={day.date} {...day} />} />
        </>
      )}
    </div>
  )
}

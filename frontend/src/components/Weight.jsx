import { useEffect, useState } from 'react'
import { Chart as ChartJS, LinearScale, PointElement, LineElement, Tooltip } from 'chart.js'
import { Line } from 'react-chartjs-2'
import { getWeight } from '../api'
import { formatLocalTime } from '../dateUtils'
import MultiDay from './MultiDay'

ChartJS.register(LinearScale, PointElement, LineElement, Tooltip)

// API datetimes are UTC with no 'Z' suffix - same parsing trick as
// formatLocalTime, but returning an epoch for charting on a linear axis.
function readingTimestamp(utcDateTimeStr) {
  return new Date(utcDateTimeStr.replace(' ', 'T') + 'Z').getTime()
}

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

  // Flattened across every day in range, regardless of MultiDay's
  // collapsible per-day grouping below - the trend line is one continuous
  // series, not something that should reset per collapsible section.
  const points = data
    ? data.days.flatMap((day) => day.readings.map((r) => ({ x: readingTimestamp(r.reading_time), y: r.value_lb })))
    : []

  const chartData = {
    datasets: [
      {
        label: 'lb',
        data: points,
        borderColor: '#2f7d4f',
        backgroundColor: '#2f7d4f',
        pointRadius: 3,
        borderWidth: 1.5,
        tension: 0.2,
      },
    ],
  }

  const chartOptions = {
    responsive: true,
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          title: (items) => new Date(items[0].parsed.x).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }),
          label: (item) => `${item.parsed.y} lb`,
        },
      },
    },
    scales: {
      x: {
        type: 'linear',
        ticks: {
          callback: (value) => new Date(value).toLocaleDateString([], { month: 'short', day: 'numeric' }),
        },
      },
      y: { title: { display: true, text: 'lb' } },
    },
  }

  return (
    <div className="weight">
      {loading && <p>Loading…</p>}
      {error && <p className="login-error">{error}</p>}

      {data && !loading && (
        <>
          {data.days.length === 0 && <p>No weight logged for this period.</p>}

          {points.length > 1 && (
            <div className="chart-wrap">
              <Line data={chartData} options={chartOptions} />
            </div>
          )}

          <MultiDay days={data.days} renderDay={(day) => <DayBody key={day.date} {...day} />} />
        </>
      )}
    </div>
  )
}

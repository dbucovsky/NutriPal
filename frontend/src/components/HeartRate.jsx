import { useEffect, useState } from 'react'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
} from 'chart.js'
import { Line } from 'react-chartjs-2'
import { getHeartRate } from '../api'
import { todayLocal } from '../dateUtils'
import DateNav from './DateNav'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip)

function stat(value, unit = '') {
  return value === null || value === undefined ? '—' : `${value}${unit}`
}

export default function HeartRate({ userId }) {
  const [date, setDate] = useState(todayLocal())
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getHeartRate(userId, date)
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

  const chartData = data && {
    labels: data.series.map((p) => p.time),
    datasets: [
      {
        data: data.series.map((p) => p.avg_bpm),
        borderColor: '#2f7d4f',
        backgroundColor: '#2f7d4f',
        pointRadius: 0,
        borderWidth: 1.5,
        tension: 0.3,
      },
    ],
  }

  const chartOptions = {
    responsive: true,
    plugins: { legend: { display: false } },
    scales: {
      x: { ticks: { maxTicksLimit: 8 } },
      y: { title: { display: true, text: 'bpm' } },
    },
  }

  return (
    <div className="heart-rate">
      <DateNav date={date} onChange={setDate} />

      {loading && <p>Loading…</p>}
      {error && <p className="login-error">{error}</p>}

      {data && !loading && (
        <>
          <div className="stat-row">
            <div className="stat">
              <span className="stat-label">Resting</span>
              <span className="stat-value">{stat(data.summary.resting_bpm, ' bpm')}</span>
            </div>
            <div className="stat">
              <span className="stat-label">Avg</span>
              <span className="stat-value">{stat(data.summary.avg_bpm, ' bpm')}</span>
            </div>
            <div className="stat">
              <span className="stat-label">Min / Max</span>
              <span className="stat-value">
                {stat(data.summary.min_bpm)} / {stat(data.summary.max_bpm)} bpm
              </span>
            </div>
            <div className="stat">
              <span className="stat-label">Avg HRV</span>
              <span className="stat-value">{stat(data.summary.avg_hrv_ms, ' ms')}</span>
            </div>
          </div>

          {data.series.length > 0 ? (
            <div className="chart-wrap">
              <Line data={chartData} options={chartOptions} />
            </div>
          ) : (
            <p>No heart rate readings this day.</p>
          )}
        </>
      )}
    </div>
  )
}

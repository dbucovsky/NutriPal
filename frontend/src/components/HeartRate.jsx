import { useEffect, useState } from 'react'
import {
  Chart as ChartJS,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
} from 'chart.js'
import annotationPlugin from 'chartjs-plugin-annotation'
import { Line } from 'react-chartjs-2'
import { getHeartRate } from '../api'
import { todayLocal } from '../dateUtils'
import DateNav from './DateNav'

ChartJS.register(LinearScale, PointElement, LineElement, Tooltip, annotationPlugin)

const EXERCISE_COLOR = 'rgba(217, 130, 43, 0.18)'
const SLEEP_COLOR = 'rgba(47, 95, 143, 0.15)'

function stat(value, unit = '') {
  return value === null || value === undefined ? '—' : `${value}${unit}`
}

function minutesToLabel(minutes) {
  const h = Math.floor(minutes / 60)
  const m = Math.round(minutes % 60)
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
}

function periodsToAnnotations(periods, color, prefix) {
  const annotations = {}
  periods.forEach((p, i) => {
    annotations[`${prefix}${i}`] = {
      type: 'box',
      xMin: p.start_minute,
      xMax: p.end_minute,
      backgroundColor: color,
      borderWidth: 0,
    }
  })
  return annotations
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
    datasets: [
      {
        label: 'bpm',
        data: data.series.map((p) => ({ x: p.minute, y: p.avg_bpm })),
        borderColor: '#2f7d4f',
        backgroundColor: '#2f7d4f',
        pointRadius: 0,
        borderWidth: 1.5,
        tension: 0.3,
      },
    ],
  }

  const chartOptions = data && {
    responsive: true,
    plugins: {
      legend: { display: false },
      annotation: {
        annotations: {
          ...periodsToAnnotations(data.sleep_periods, SLEEP_COLOR, 'sleep'),
          ...periodsToAnnotations(data.exercise_periods, EXERCISE_COLOR, 'exercise'),
        },
      },
    },
    scales: {
      x: {
        type: 'linear',
        min: 0,
        max: 1440,
        ticks: { stepSize: 120, callback: (value) => minutesToLabel(value) },
      },
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

          {(data.sleep_periods.length > 0 || data.exercise_periods.length > 0) && (
            <div className="stage-legend chart-legend">
              <span className="stage-legend-item">
                <span className="stage-swatch" style={{ backgroundColor: SLEEP_COLOR }} />
                Sleep
              </span>
              <span className="stage-legend-item">
                <span className="stage-swatch" style={{ backgroundColor: EXERCISE_COLOR }} />
                Exercise
              </span>
            </div>
          )}

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

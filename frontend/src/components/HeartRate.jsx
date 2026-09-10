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
import { formatLocalTime } from '../dateUtils'
import MultiDay from './MultiDay'
import SessionHrPopup from './SessionHrPopup'

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

function daySummary(day) {
  if (day.summary.reading_count === 0) return 'No bpm readings'
  return `avg ${day.summary.avg_bpm} bpm · resting ${stat(day.summary.resting_bpm, ' bpm')}`
}

function DayBody({
  userId,
  summary,
  series,
  exercise_periods: exercisePeriods,
  sleep_periods: sleepPeriods,
  seriesIncluded,
}) {
  const chartData = {
    datasets: [
      {
        label: 'bpm',
        data: series.map((p) => ({ x: p.minute, y: p.avg_bpm })),
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
    plugins: {
      legend: { display: false },
      annotation: {
        annotations: {
          ...periodsToAnnotations(sleepPeriods, SLEEP_COLOR, 'sleep'),
          ...periodsToAnnotations(exercisePeriods, EXERCISE_COLOR, 'exercise'),
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
    <>
      <div className="stat-row">
        <div className="stat">
          <span className="stat-label">Resting</span>
          <span className="stat-value">{stat(summary.resting_bpm, ' bpm')}</span>
        </div>
        <div className="stat">
          <span className="stat-label">Avg</span>
          <span className="stat-value">{stat(summary.avg_bpm, ' bpm')}</span>
        </div>
        <div className="stat">
          <span className="stat-label">Min / Max</span>
          <span className="stat-value">
            {stat(summary.min_bpm)} / {stat(summary.max_bpm)} bpm
          </span>
        </div>
        <div className="stat">
          <span className="stat-label">Avg HRV</span>
          <span className="stat-value">{stat(summary.avg_hrv_ms, ' ms')}</span>
        </div>
      </div>

      {(sleepPeriods.length > 0 || exercisePeriods.length > 0) && (
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

      {series.length > 0 ? (
        <div className="chart-wrap">
          <Line data={chartData} options={chartOptions} />
        </div>
      ) : seriesIncluded ? (
        <p>No heart rate readings this day.</p>
      ) : (
        <p className="text-muted">Chart hidden for Month/Year/long Custom views — switch to Day or Week to see it.</p>
      )}

      {exercisePeriods.length > 0 && (
        <ul className="exercise-list">
          {exercisePeriods.map((period) => (
            <li key={period.id} className="exercise-entry">
              <div className="exercise-entry-header">
                <strong>{period.label}</strong>
                <span className="text-muted entry-time-with-icon">
                  {formatLocalTime(period.start_time)} – {formatLocalTime(period.end_time)}
                  <SessionHrPopup userId={userId} startTime={period.start_time} endTime={period.end_time} label={period.label} />
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </>
  )
}

export default function HeartRate({ userId, view }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getHeartRate(userId, view)
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
    <div className="heart-rate">
      {loading && <p>Loading…</p>}
      {error && <p className="login-error">{error}</p>}

      {data && !loading && (
        <>
          {data.days.length === 0 && <p>No heart rate readings this period.</p>}
          <MultiDay
            days={data.days}
            renderDay={(day) => <DayBody key={day.date} userId={userId} {...day} seriesIncluded={data.series_included} />}
            renderSummary={daySummary}
          />
        </>
      )}
    </div>
  )
}

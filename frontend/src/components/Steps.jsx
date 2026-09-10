import { useEffect, useState } from 'react'
import { Chart as ChartJS, CategoryScale, LinearScale, BarElement, Tooltip } from 'chart.js'
import { Bar } from 'react-chartjs-2'
import { getSteps } from '../api'
import { formatDisplayDate } from '../dateUtils'
import MultiDay from './MultiDay'

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip)

function daySummary(day) {
  return `${day.steps.toLocaleString()} steps · ${day.source}`
}

function DayBody({ steps, source, other_sources: otherSources }) {
  return (
    <div className="steps-day-detail">
      <div className="steps-day-total">{steps.toLocaleString()} steps</div>
      <div className="text-muted">Source: {source}</div>
      {otherSources.length > 0 && (
        <div className="text-muted steps-other-sources">
          Not counted (other source reported the same day): {otherSources.map((o) => `${o.name} ${o.steps.toLocaleString()}`).join(', ')}
        </div>
      )}
    </div>
  )
}

export default function Steps({ userId, view }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getSteps(userId, view)
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

  const chartData = data && {
    labels: data.days.map((d) => formatDisplayDate(d.date)),
    datasets: [
      {
        label: 'steps',
        data: data.days.map((d) => d.steps),
        backgroundColor: '#2f7d4f',
      },
    ],
  }

  const chartOptions = {
    responsive: true,
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          afterLabel: (item) => `Source: ${data.days[item.dataIndex].source}`,
        },
      },
    },
    scales: {
      y: { title: { display: true, text: 'steps' }, beginAtZero: true },
    },
  }

  return (
    <div className="steps">
      <p className="page-note">
        Each day shows its single highest-reporting source, not a sum across sources - see Known limitations in
        CHANGELOG.md.
      </p>

      {loading && <p>Loading…</p>}
      {error && <p className="login-error">{error}</p>}

      {data && !loading && (
        <>
          {data.days.length === 0 && <p>No steps logged for this period.</p>}

          {data.days.length > 1 && (
            <div className="chart-wrap">
              <Bar data={chartData} options={chartOptions} />
            </div>
          )}

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

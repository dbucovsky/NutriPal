import { useState } from 'react'
import { Chart as ChartJS, LinearScale, PointElement, LineElement, Tooltip } from 'chart.js'
import annotationPlugin from 'chartjs-plugin-annotation'
import { Line } from 'react-chartjs-2'
import { getHeartRateRange } from '../api'
import { zoneBandAnnotations } from '../hrZones'
import Popup from './Popup'
import ZoneLegend from './ZoneLegend'

ChartJS.register(LinearScale, PointElement, LineElement, Tooltip, annotationPlugin)

// A single neutral line color, not one of the zone colors themselves (green
// used to double as both "the line" and "Zone 2", making Zone 2 and
// below-Zone-1 segments hard to tell apart) - zones are shown as background
// bands behind the line instead (see zoneBandAnnotations), so the line only
// needs to read clearly against any of them.
const LINE_COLOR = '#26314a'

// Same "UTC string with no Z suffix" parsing trick used throughout this
// app - see dateUtils.js's formatLocalTime.
function toEpochMs(utcDateTimeStr) {
  return new Date(utcDateTimeStr.replace(' ', 'T') + 'Z').getTime()
}

// Small chart-icon button that, on click, pops open that exact time
// window's heart rate curve - fetched on demand, not upfront, since most
// sessions are never opened. Plain inline SVG, not an emoji icon.
export default function SessionHrPopup({ userId, startTime, endTime, label, maxHr }) {
  const [open, setOpen] = useState(false)
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  function handleOpen(e) {
    e.stopPropagation()
    e.preventDefault()
    setOpen(true)
    if (data || loading) return
    setLoading(true)
    setError(null)
    getHeartRateRange(userId, startTime, endTime)
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }

  const startMs = toEpochMs(startTime)
  const points = data ? data.readings.map((r) => ({ x: (toEpochMs(r.reading_time) - startMs) / 60000, y: r.bpm })) : []

  const chartData = {
    datasets: [
      {
        label: 'bpm',
        data: points,
        borderColor: LINE_COLOR,
        backgroundColor: LINE_COLOR,
        pointRadius: 0,
        borderWidth: 2,
        tension: 0.3,
      },
    ],
  }

  const chartOptions = {
    responsive: true,
    plugins: {
      legend: { display: false },
      annotation: { annotations: maxHr ? zoneBandAnnotations(maxHr) : {} },
    },
    scales: {
      x: { type: 'linear', title: { display: true, text: 'minutes' } },
      y: { title: { display: true, text: 'bpm' } },
    },
  }

  return (
    <>
      <button type="button" className="chart-icon-button" onClick={handleOpen} aria-label={`View heart rate during ${label}`}>
        <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
          <rect x="1" y="9" width="3" height="6" fill="currentColor" />
          <rect x="6.5" y="5" width="3" height="10" fill="currentColor" />
          <rect x="12" y="2" width="3" height="13" fill="currentColor" />
        </svg>
      </button>

      {open && (
        <Popup title={`Heart rate — ${label}`} onClose={() => setOpen(false)}>
          {loading && <p>Loading…</p>}
          {error && <p className="login-error">{error}</p>}
          {data && !loading && (
            <div className="chart-wrap">
              {points.length > 0 ? (
                <>
                  <Line data={chartData} options={chartOptions} />
                  {maxHr && <ZoneLegend maxHr={maxHr} />}
                </>
              ) : (
                <p>No heart rate readings during this session.</p>
              )}
            </div>
          )}
        </Popup>
      )}
    </>
  )
}

import { useEffect, useMemo, useState } from 'react'
import {
  Chart as ChartJS,
  LinearScale,
  CategoryScale,
  PointElement,
  LineElement,
  BarElement,
  Tooltip,
} from 'chart.js'
import annotationPlugin from 'chartjs-plugin-annotation'
import { Line, Bar } from 'react-chartjs-2'
import { getHeartRate, getHeartRateRange } from '../api'
import {
  formatDisplayDate,
  formatWeekNumberLabel,
  formatMonthLabel,
  formatQuarterLabel,
  formatYearLabel,
  weekKey,
  monthKey,
  yearKey,
} from '../dateUtils'
import RangeTree, { buildTree, enumerateNodeKeys } from './RangeTree'
import QuickToolbar from './QuickToolbar'
import Popup from './Popup'

ChartJS.register(LinearScale, CategoryScale, PointElement, LineElement, BarElement, Tooltip, annotationPlugin)

const EXERCISE_COLOR = 'rgba(217, 130, 43, 0.18)'
const SLEEP_COLOR = 'rgba(47, 95, 143, 0.15)'
const BAR_COLOR = '#2f7d4f'

const METRIC_LABELS = {
  avg_bpm: 'Avg bpm',
  resting_bpm: 'Resting bpm',
  avg_hrv_ms: 'Avg HRV',
}

// Toolbar levels, coarsest first - same idea as Food's toolbar, minus the
// meal-equivalent leaf level (nothing sits below a day here).
const TOOLBAR_LEVELS = [
  { level: 'year', badge: 'Y', title: 'Collapse to year' },
  { level: 'quarter', badge: 'Q', title: 'Collapse to quarter' },
  { level: 'month', badge: 'M', title: 'Collapse to month' },
  { level: 'week', badge: 'W', title: 'Collapse to week' },
  { level: 'day', badge: 'D', title: 'Collapse to day' },
]
const LEVEL_ORDER = TOOLBAR_LEVELS.map((l) => l.level)

function round1(value) {
  return Math.round(value * 10) / 10
}

function stat(value, unit = '') {
  return value === null || value === undefined ? '—' : `${value}${unit}`
}

function minutesToLabel(minutes) {
  const h = Math.floor(minutes / 60)
  const m = Math.round(minutes % 60)
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
}

function sleepAnnotations(periods) {
  const annotations = {}
  periods.forEach((p, i) => {
    annotations[`sleep${i}`] = {
      type: 'box',
      xMin: p.start_minute,
      xMax: p.end_minute,
      backgroundColor: SLEEP_COLOR,
      borderWidth: 0,
    }
  })
  return annotations
}

// Exercise bands double as an interactive element: hovering reveals what
// the activity was (a floating label, hidden until `enter`) instead of the
// old below-chart list, and clicking opens that exact session's own
// bpm-curve popup - the same drill-down the list's icon used to offer.
function exerciseAnnotations(periods, onOpenSession) {
  const annotations = {}
  periods.forEach((p, i) => {
    annotations[`exercise${i}`] = {
      type: 'box',
      xMin: p.start_minute,
      xMax: p.end_minute,
      backgroundColor: EXERCISE_COLOR,
      borderWidth: 0,
      label: {
        content: p.label,
        display: false,
        position: 'center',
        font: { size: 11, weight: 'bold' },
        color: '#fff',
        backgroundColor: 'rgba(0, 0, 0, 0.8)',
        padding: 4,
        z: 100,
      },
      enter({ element }) {
        element.label.options.display = true
        return true
      },
      leave({ element }) {
        element.label.options.display = false
        return true
      },
      click: () => onOpenSession(p),
    }
  })
  return annotations
}

function daySummary(day) {
  if (day.summary.reading_count === 0) return 'No bpm readings'
  return `avg ${day.summary.avg_bpm} bpm · resting ${stat(day.summary.resting_bpm, ' bpm')}`
}

// Right-aligned, fixed-column-width row for avg/resting/HRV - shares the
// Food macro grid's cell/button styling (`.hr-stat-grid` mirrors
// `.macro-grid`'s column approach with 3 fields instead of 4).
function HrStatRow({ avgBpm, restingBpm, avgHrv, onClickMetric }) {
  function cell(value, unit, metric) {
    const content = stat(value, unit)
    if (!onClickMetric) {
      return <span className="macro-cell-value">{content}</span>
    }
    return (
      <button
        type="button"
        className="macro-cell-value macro-cell-clickable"
        onClick={(e) => {
          e.stopPropagation()
          e.preventDefault()
          onClickMetric(metric)
        }}
      >
        {content}
      </button>
    )
  }

  return (
    <span className="hr-stat-grid">
      <span className="macro-cell-label">Avg</span>
      {cell(avgBpm, ' bpm', 'avg_bpm')}
      <span className="macro-cell-label">Resting</span>
      {cell(restingBpm, ' bpm', 'resting_bpm')}
      <span className="macro-cell-label">HRV</span>
      {cell(avgHrv, ' ms', 'avg_hrv_ms')}
    </span>
  )
}

// Average of each day's own value per field, skipping days where that
// particular field is null (unlike Food's day totals, a day can have
// exercise/sleep logged with zero bpm readings - see heart-rate.php - so
// avg_bpm/resting_bpm/avg_hrv_ms are each nullable independently).
function averageHrStats(days) {
  const sums = { avg_bpm: 0, resting_bpm: 0, avg_hrv_ms: 0 }
  const counts = { avg_bpm: 0, resting_bpm: 0, avg_hrv_ms: 0 }
  for (const day of days) {
    for (const key of Object.keys(sums)) {
      const value = day.summary[key]
      if (value !== null && value !== undefined) {
        sums[key] += value
        counts[key] += 1
      }
    }
  }
  const avg = {}
  for (const key of Object.keys(sums)) {
    avg[key] = counts[key] > 0 ? round1(sums[key] / counts[key]) : null
  }
  return avg
}

// Week/Month/Quarter breakdown: one bar per day in the group, chronological
// (not sorted by value - this is a trend, not a composition). Days missing
// that particular metric are skipped rather than shown as zero.
function barDataByDay(days, metric) {
  return days
    .filter((day) => day.summary[metric] !== null && day.summary[metric] !== undefined)
    .map((day) => ({ label: formatDisplayDate(day.date), value: day.summary[metric] }))
}

// Year breakdown: one bar per month, averaging that month's own days for
// the metric (a sum wouldn't mean anything for bpm/HRV).
function barDataByMonth(days, metric) {
  const byMonth = new Map()
  for (const day of days) {
    const value = day.summary[metric]
    if (value === null || value === undefined) continue
    const key = day.date.slice(0, 7)
    if (!byMonth.has(key)) byMonth.set(key, { sum: 0, count: 0 })
    const entry = byMonth.get(key)
    entry.sum += value
    entry.count += 1
  }
  return [...byMonth.entries()].map(([key, { sum, count }]) => ({
    label: formatMonthLabel(`${key}-01`),
    value: round1(sum / count),
  }))
}

function BarBreakdownPopup({ title, items, onClose }) {
  const chartData = {
    labels: items.map((i) => i.label),
    datasets: [{ data: items.map((i) => i.value), backgroundColor: BAR_COLOR }],
  }

  return (
    <Popup title={title} onClose={onClose}>
      {items.length > 0 ? (
        <div className="chart-wrap">
          <Bar data={chartData} options={{ plugins: { legend: { display: false } }, scales: { y: { beginAtZero: false } } }} />
        </div>
      ) : (
        <p>No data for this period.</p>
      )}
    </Popup>
  )
}

function SessionPopup({ userId, period, onClose }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getHeartRateRange(userId, period.start_time, period.end_time)
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
  }, [userId, period.start_time, period.end_time])

  const startMs = new Date(period.start_time.replace(' ', 'T') + 'Z').getTime()
  const points = data
    ? data.readings.map((r) => ({ x: (new Date(r.reading_time.replace(' ', 'T') + 'Z').getTime() - startMs) / 60000, y: r.bpm }))
    : []

  const chartData = {
    datasets: [
      {
        label: 'bpm',
        data: points,
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
      x: { type: 'linear', title: { display: true, text: 'minutes' } },
      y: { title: { display: true, text: 'bpm' } },
    },
  }

  return (
    <Popup title={`Heart rate — ${period.label}`} onClose={onClose}>
      {loading && <p>Loading…</p>}
      {error && <p className="login-error">{error}</p>}
      {data && !loading && (
        <div className="chart-wrap">
          {points.length > 0 ? <Line data={chartData} options={chartOptions} /> : <p>No heart rate readings during this session.</p>}
        </div>
      )}
    </Popup>
  )
}

function DayBody({ summary, series, exercise_periods: exercisePeriods, sleep_periods: sleepPeriods, seriesIncluded, onOpenSession }) {
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
          ...sleepAnnotations(sleepPeriods),
          ...exerciseAnnotations(exercisePeriods, onOpenSession),
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
            Exercise (hover for activity, click for its bpm curve)
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
    </>
  )
}

function groupLabel(level, key) {
  switch (level) {
    case 'year':
      return formatYearLabel(`${key}-01-01`)
    case 'quarter':
      return formatQuarterLabel(key)
    case 'month':
      return formatMonthLabel(`${key}-01`)
    case 'week':
      return formatWeekNumberLabel(key)
    default:
      return key
  }
}

export default function HeartRate({ userId, view }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [barRequest, setBarRequest] = useState(null)
  const [sessionRequest, setSessionRequest] = useState(null)
  const [openState, setOpenState] = useState({})

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getHeartRate(userId, view)
      .then((result) => {
        if (!cancelled) {
          setData(result)
          setOpenState({})
        }
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

  const tree = useMemo(() => (data ? buildTree(data.days) : []), [data])
  const nodeKeys = useMemo(() => enumerateNodeKeys(tree), [tree])
  const availableLevels = useMemo(() => new Set(nodeKeys.map((k) => k.level)), [nodeKeys])

  const topHeader = useMemo(() => {
    if (!data || data.days.length === 0) return null
    switch (view.type) {
      case 'week':
        return { level: 'week', key: weekKey(data.start_date) }
      case 'month':
        return { level: 'month', key: monthKey(data.start_date) }
      case 'year':
        return { level: 'year', key: yearKey(data.start_date) }
      default:
        return null
    }
  }, [data, view.type])

  function handleToggle(key, isOpen) {
    setOpenState((prev) => ({ ...prev, [key]: isOpen }))
  }

  function handleExpandAll() {
    setOpenState(Object.fromEntries(nodeKeys.map(({ key }) => [key, true])))
  }

  function handleCollapseAll() {
    setOpenState(Object.fromEntries(nodeKeys.map(({ key }) => [key, false])))
  }

  function handleCollapseTo(targetLevel) {
    const targetIndex = LEVEL_ORDER.indexOf(targetLevel)
    setOpenState(Object.fromEntries(nodeKeys.map(({ key, level }) => [key, LEVEL_ORDER.indexOf(level) < targetIndex])))
  }

  function handleReset() {
    setOpenState({})
  }

  function renderGroupSummary(level, key, days) {
    const avg = averageHrStats(days)
    const onClickMetric = (metric) => {
      const label = groupLabel(level, key)
      if (level === 'year') {
        setBarRequest({ title: `${METRIC_LABELS[metric]} — ${label} (by month)`, items: barDataByMonth(days, metric) })
      } else {
        setBarRequest({ title: `${METRIC_LABELS[metric]} — ${label} (by day)`, items: barDataByDay(days, metric) })
      }
    }
    return <HrStatRow avgBpm={avg.avg_bpm} restingBpm={avg.resting_bpm} avgHrv={avg.avg_hrv_ms} onClickMetric={onClickMetric} />
  }

  function renderDaySummary(day) {
    return daySummary(day)
  }

  function renderDayBody(day) {
    return (
      <DayBody
        key={day.date}
        {...day}
        seriesIncluded={data.series_included}
        onOpenSession={(period) => setSessionRequest(period)}
      />
    )
  }

  return (
    <div className="heart-rate">
      <QuickToolbar
        levels={TOOLBAR_LEVELS}
        availableLevels={availableLevels}
        onExpandAll={handleExpandAll}
        onCollapseAll={handleCollapseAll}
        onCollapseTo={handleCollapseTo}
        onReset={handleReset}
      />

      {loading && <p>Loading…</p>}
      {error && <p className="login-error">{error}</p>}

      {data && !loading && (
        <>
          {data.days.length === 0 && <p>No heart rate readings this period.</p>}
          {topHeader && (
            <div className="daily-totals">
              <strong>{groupLabel(topHeader.level, topHeader.key)}:</strong>{' '}
              <span className="day-section-summary">{renderGroupSummary(topHeader.level, topHeader.key, data.days)}</span>
            </div>
          )}
          <RangeTree
            tree={tree}
            openState={openState}
            onToggle={handleToggle}
            renderGroupSummary={renderGroupSummary}
            renderDaySummary={renderDaySummary}
            renderDayBody={renderDayBody}
          />
        </>
      )}

      {barRequest && <BarBreakdownPopup title={barRequest.title} items={barRequest.items} onClose={() => setBarRequest(null)} />}
      {sessionRequest && <SessionPopup userId={userId} period={sessionRequest} onClose={() => setSessionRequest(null)} />}
    </div>
  )
}

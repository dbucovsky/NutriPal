import { useEffect, useMemo, useState } from 'react'
import { Chart as ChartJS, CategoryScale, LinearScale, BarElement, Tooltip } from 'chart.js'
import { Bar } from 'react-chartjs-2'
import { getSteps } from '../api'
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

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip)

const BAR_COLOR = '#2f7d4f'

const METRIC_LABELS = {
  steps: 'Avg steps',
}

// Toolbar levels, coarsest first - same idea as Heart Rate/Sleep/Exercise's
// toolbar, minus the meal-equivalent leaf level (nothing sits below a day
// here).
const TOOLBAR_LEVELS = [
  { level: 'year', badge: 'Y', title: 'Collapse to year' },
  { level: 'quarter', badge: 'Q', title: 'Collapse to quarter' },
  { level: 'month', badge: 'M', title: 'Collapse to month' },
  { level: 'week', badge: 'W', title: 'Collapse to week' },
  { level: 'day', badge: 'D', title: 'Collapse to day' },
]
const LEVEL_ORDER = TOOLBAR_LEVELS.map((l) => l.level)

const OTHER_SOURCES_LABEL = {
  Fitbit: 'Not counted (Fitbit was tracking fine all day)',
  Phone: "Not counted (Fitbit wasn't tracking - Phone filled in the whole day)",
  Mixed: "Each source's own whole-day total, for comparison",
}

// < goal = bad, >= goal = good, >= goal*2 = great - a plain 3-tier read on
// a day's (or a group average's) own step count against the user's own
// configurable daily target (Settings, defaults to 10,000 - see
// src/StepsGoal.php).
function stepsQuality(steps, goal) {
  if (!goal) return null
  if (steps >= goal * 2) return { label: 'Great', className: 'quality-great' }
  if (steps >= goal) return { label: 'Good', className: 'quality-good' }
  return { label: 'Bad', className: 'quality-bad' }
}

function QualityBadge({ steps, goal }) {
  const quality = stepsQuality(steps, goal)
  if (!quality) return null
  return <span className={`quality-badge ${quality.className}`}>{quality.label}</span>
}

function formatHourLabel(hour) {
  return `${String(hour).padStart(2, '0')}:00`
}

function stat(value, unit = '') {
  return value === null || value === undefined ? '—' : `${value}${unit}`
}

// A day is never null (a day with no readings at all is still reported as
// {steps: 0, source: null} by steps.php, through today - see its own
// docblock), so averaging can just divide by every day in the group with
// no null-skipping needed, unlike Heart Rate's per-field nullability.
function averageStepsStats(days, goal) {
  const totalDays = days.length
  const sumSteps = days.reduce((sum, d) => sum + d.steps, 0)
  const avgSteps = totalDays > 0 ? Math.round(sumSteps / totalDays) : null
  const goodDays = days.filter((d) => d.steps >= goal).length
  const greatDays = days.filter((d) => d.steps >= goal * 2).length
  return { avgSteps, totalDays, goodDays, greatDays }
}

// Week/Month/Quarter breakdown: one bar per day in the group, chronological
// (not sorted by value - this is a trend, not a ranking).
function barDataByDay(days) {
  return days.map((day) => ({ label: formatDisplayDate(day.date), value: day.steps }))
}

// Year breakdown: one bar per month, averaging that month's own days (a sum
// of a month's steps reads as "how many steps that month," which isn't
// what this page is about - matches Exercise/Heart Rate's own convention
// of averaging rather than summing per-month bars).
function barDataByMonth(days) {
  const byMonth = new Map()
  for (const day of days) {
    const key = day.date.slice(0, 7)
    if (!byMonth.has(key)) byMonth.set(key, { sum: 0, count: 0 })
    const entry = byMonth.get(key)
    entry.sum += day.steps
    entry.count += 1
  }
  return [...byMonth.entries()].map(([key, { sum, count }]) => ({
    label: formatMonthLabel(`${key}-01`),
    value: Math.round(sum / count),
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

// Plain "·"-joined line shared by the day summary and the group averages -
// same style as Exercise's own stats line. `onOpenBar` is only given at
// group levels (Week/Month/Quarter/Year), which have something to break
// down further into a bar chart; a single day's own line just shows text.
function StepsStatsLine({ steps, goal, extra, onOpenBar }) {
  function piece(text) {
    if (!onOpenBar) return text
    return (
      <button
        type="button"
        className="inline-link-button"
        onClick={(e) => {
          e.stopPropagation()
          e.preventDefault()
          onOpenBar()
        }}
      >
        {text}
      </button>
    )
  }

  return (
    <span>
      {piece(`${steps.toLocaleString()} steps`)}
      <QualityBadge steps={steps} goal={goal} />
      {extra && <> · {extra}</>}
    </span>
  )
}

function DayBody({ userId, date, steps, source, other_sources: otherSources, series, goal, seriesIncluded }) {
  // Month/Year views never fetch every day's hourly breakdown upfront (see
  // steps.php's MAX_SERIES_DAYS, same idea as Heart Rate's own day chart) -
  // a button fetches THIS one day's series on demand instead.
  const [manualSeries, setManualSeries] = useState(null)
  const [loadingSeries, setLoadingSeries] = useState(false)
  const [seriesError, setSeriesError] = useState(null)

  function handleShowChart() {
    setLoadingSeries(true)
    setSeriesError(null)
    getSteps(userId, { type: 'day', date })
      .then((result) => {
        setManualSeries(result.days[0] ? result.days[0].series : [])
      })
      .catch((err) => setSeriesError(err.message))
      .finally(() => setLoadingSeries(false))
  }

  const effectiveSeries = series.length > 0 ? series : manualSeries || []
  const hasChartData = effectiveSeries.some((p) => p.steps > 0)

  const chartData = {
    labels: effectiveSeries.map((p) => formatHourLabel(p.hour)),
    datasets: [{ label: 'steps', data: effectiveSeries.map((p) => p.steps), backgroundColor: BAR_COLOR }],
  }

  const chartOptions = {
    responsive: true,
    plugins: { legend: { display: false } },
    scales: { y: { title: { display: true, text: 'steps' }, beginAtZero: true } },
  }

  return (
    <>
      <div className="stat-row">
        <div className="stat">
          <span className="stat-label">Steps</span>
          <span className="stat-value">
            {steps.toLocaleString()} <QualityBadge steps={steps} goal={goal} />
          </span>
        </div>
        <div className="stat">
          <span className="stat-label">Source</span>
          <span className="stat-value">{stat(source ?? 'None')}</span>
        </div>
      </div>

      {otherSources.length > 0 && (
        <p className="text-muted steps-other-sources">
          {OTHER_SOURCES_LABEL[source]}: {otherSources.map((o) => `${o.name} ${o.steps.toLocaleString()}`).join(', ')}
        </p>
      )}

      {hasChartData ? (
        <div className="chart-wrap">
          <Bar data={chartData} options={chartOptions} />
        </div>
      ) : seriesIncluded || manualSeries !== null ? (
        <p>No steps logged this day.</p>
      ) : (
        <div>
          <button type="button" onClick={handleShowChart} disabled={loadingSeries}>
            {loadingSeries ? 'Loading…' : 'Show chart for this day'}
          </button>
          {seriesError && <p className="login-error">{seriesError}</p>}
        </div>
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

export default function Steps({ userId, view }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [barRequest, setBarRequest] = useState(null)
  const [openState, setOpenState] = useState({})

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getSteps(userId, view)
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
    const avg = averageStepsStats(days, data.goal)
    function onOpenBar() {
      const label = groupLabel(level, key)
      if (level === 'year') {
        setBarRequest({ title: `${METRIC_LABELS.steps} — ${label} (by month)`, items: barDataByMonth(days) })
      } else {
        setBarRequest({ title: `${METRIC_LABELS.steps} — ${label} (by day)`, items: barDataByDay(days) })
      }
    }
    if (avg.avgSteps === null) return null
    return (
      <StepsStatsLine
        steps={avg.avgSteps}
        goal={data.goal}
        extra={`${avg.goodDays}/${avg.totalDays} days ≥ ${data.goal.toLocaleString()}${avg.greatDays > 0 ? ` · ${avg.greatDays} great` : ''}`}
        onOpenBar={onOpenBar}
      />
    )
  }

  function renderDaySummary(day) {
    return <StepsStatsLine steps={day.steps} goal={data.goal} extra={day.source ?? 'None'} />
  }

  function renderDayBody(day) {
    return <DayBody key={day.date} userId={userId} {...day} goal={data.goal} seriesIncluded={data.series_included} />
  }

  return (
    <div className="steps">
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
          {data.days.length === 0 && <p>No days in this period yet.</p>}
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
    </div>
  )
}

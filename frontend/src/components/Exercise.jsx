import { useEffect, useMemo, useState } from 'react'
import { Chart as ChartJS, LinearScale, CategoryScale, BarElement, Tooltip } from 'chart.js'
import { Bar } from 'react-chartjs-2'
import { getExercise } from '../api'
import {
  formatDisplayDate,
  formatLocalTime,
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
import SessionHrPopup from './SessionHrPopup'
import Popup from './Popup'
import { hrZone } from '../hrZones'

ChartJS.register(LinearScale, CategoryScale, BarElement, Tooltip)

const BAR_COLOR = '#d9822b'

const METRIC_LABELS = {
  totalMinutes: 'Duration',
  totalCalories: 'Calories',
  avgHr: 'Avg HR',
}

// Toolbar levels, coarsest first - same idea as Food/Heart Rate/Sleep's
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

function ZoneBadge({ bpm, maxHr }) {
  const zone = hrZone(bpm, maxHr)
  if (!zone) return null
  return (
    <span className={`quality-badge ${zone.className}`} title={zone.label}>
      Z{zone.key}
    </span>
  )
}

function stat(value, unit = '') {
  return value === null || value === undefined ? '—' : `${value}${unit}`
}

// A day's own headline numbers - single source of truth reused for the day
// summary, the group averages, and the bar-chart breakdowns. avgHr is null
// (not 0) when no session that day recorded one, so averaging elsewhere can
// skip it rather than dragging the average down with a false zero. maxHr is
// this day's own historically-accurate Max HR (from the API, per-day - see
// exercise.php), not today's - it's what actually applied on that date.
function dayStats(day) {
  const totalMinutes = day.sessions.reduce((sum, s) => sum + (s.duration_minutes || 0), 0)
  const totalCalories = day.sessions.reduce((sum, s) => sum + (s.calories || 0), 0)
  const hrValues = day.sessions.map((s) => s.average_heart_rate).filter((v) => v !== null && v !== undefined)
  const avgHr = hrValues.length > 0 ? Math.round(hrValues.reduce((a, b) => a + b, 0) / hrValues.length) : null
  return { totalMinutes, totalCalories, avgHr, maxHr: day.max_heart_rate ?? null, sessionCount: day.sessions.length }
}

// Average of each day's own value per field, skipping days where that
// particular field is null (a day with no HR-tracked session contributes
// to neither day-count for avgHr's average, but still counts for the
// duration/calories ones). maxHr is averaged the same way - a group
// spanning days with different historical Max HR estimates (most likely
// with "observed" selected, since that one actually drifts day to day)
// gets one representative number for its own zone badge, consistent with
// how avgHr itself is already an average rather than any single day's value.
function averageExerciseStats(days) {
  const sums = { totalMinutes: 0, totalCalories: 0, avgHr: 0, maxHr: 0 }
  const counts = { totalMinutes: 0, totalCalories: 0, avgHr: 0, maxHr: 0 }
  for (const day of days) {
    const stats = dayStats(day)
    for (const key of Object.keys(sums)) {
      const value = stats[key]
      if (value !== null && value !== undefined) {
        sums[key] += value
        counts[key] += 1
      }
    }
  }
  const avg = {}
  for (const key of Object.keys(sums)) {
    avg[key] = counts[key] > 0 ? Math.round(sums[key] / counts[key]) : null
  }
  return avg
}

// Week/Month/Quarter breakdown: one bar per day in the group, chronological
// (not sorted by value - this is a trend, not a composition). Days missing
// that particular metric are skipped rather than shown as zero.
function barDataByDay(days, metric) {
  return days
    .map((day) => ({ label: formatDisplayDate(day.date), value: dayStats(day)[metric] }))
    .filter((item) => item.value !== null && item.value !== undefined)
}

// Year breakdown: one bar per month, averaging that month's own days for
// the metric (a sum of a month's avg-HR figures isn't a meaningful number,
// and even for duration/calories an average reads more like "a typical day"
// than an arbitrary sum of however many days that month had entries).
function barDataByMonth(days, metric) {
  const byMonth = new Map()
  for (const day of days) {
    const value = dayStats(day)[metric]
    if (value === null || value === undefined) continue
    const key = day.date.slice(0, 7)
    if (!byMonth.has(key)) byMonth.set(key, { sum: 0, count: 0 })
    const entry = byMonth.get(key)
    entry.sum += value
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

// Plain "·"-joined line (matching Sleep's own style - Exercise never used
// Food/Heart Rate's fixed-column grid either) shared by the day summary and
// the group averages. `onOpenBar` is only given at group levels (Week/
// Month/Quarter/Year), which have something to break down further into a
// bar chart; a single day's own line just shows plain text.
function ExerciseStatsLine({ totalMinutes, totalCalories, avgHr, maxHr, extra, onOpenBar }) {
  function piece(metric, text) {
    if (!onOpenBar) return text
    return (
      <button
        type="button"
        className="inline-link-button"
        onClick={(e) => {
          e.stopPropagation()
          e.preventDefault()
          onOpenBar(metric)
        }}
      >
        {text}
      </button>
    )
  }

  return (
    <span>
      {piece('totalMinutes', `${totalMinutes} min`)}
      {' · '}
      {piece('totalCalories', `${totalCalories} kcal`)}
      {extra && <> · {extra}</>}
      {avgHr !== null && (
        <>
          {' · '}
          {piece('avgHr', `avg HR ${avgHr} bpm`)}
          <ZoneBadge bpm={avgHr} maxHr={maxHr} />
        </>
      )}
    </span>
  )
}

function DayBody({ userId, sessions, maxHr }) {
  return (
    <ul className="exercise-list">
      {sessions.map((session) => (
        <li key={session.id} className="exercise-entry">
          <div className="exercise-entry-header">
            <strong>{session.activity_name || session.activity_type || 'Activity'}</strong>
            <span className="text-muted entry-time-with-icon">
              {formatLocalTime(session.start_time)} – {formatLocalTime(session.end_time)}
              <SessionHrPopup
                userId={userId}
                startTime={session.start_time}
                endTime={session.end_time}
                label={session.activity_name || session.activity_type || 'Activity'}
                maxHr={maxHr}
              />
            </span>
          </div>
          <div className="exercise-entry-stats">
            {stat(session.duration_minutes, ' min')} · {stat(session.calories, ' kcal')} ·{' '}
            {session.distance !== null
              ? `${stat(session.distance)} ${session.distance_unit ?? ''}`
              : '—'}{' '}
            · {stat(session.steps, ' steps')} · avg HR {stat(session.average_heart_rate, ' bpm')}
            {session.average_heart_rate !== null && <ZoneBadge bpm={session.average_heart_rate} maxHr={maxHr} />}
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
  const [barRequest, setBarRequest] = useState(null)
  const [openState, setOpenState] = useState({})

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getExercise(userId, view)
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
    const avg = averageExerciseStats(days)
    const label = groupLabel(level, key)
    function onOpenBar(metric) {
      const title = `${METRIC_LABELS[metric]} — ${label} (${level === 'year' ? 'by month' : 'by day'})`
      const items = level === 'year' ? barDataByMonth(days, metric) : barDataByDay(days, metric)
      setBarRequest({ title, items })
    }
    return (
      <ExerciseStatsLine
        totalMinutes={avg.totalMinutes}
        totalCalories={avg.totalCalories}
        avgHr={avg.avgHr}
        maxHr={avg.maxHr}
        onOpenBar={onOpenBar}
      />
    )
  }

  function renderDaySummary(day) {
    const { totalMinutes, totalCalories, avgHr, maxHr, sessionCount } = dayStats(day)
    const extra = `${sessionCount} ${sessionCount === 1 ? 'session' : 'sessions'}`
    return (
      <ExerciseStatsLine totalMinutes={totalMinutes} totalCalories={totalCalories} avgHr={avgHr} maxHr={maxHr} extra={extra} />
    )
  }

  function renderDayBody(day) {
    return <DayBody key={day.date} userId={userId} sessions={day.sessions} maxHr={day.max_heart_rate ?? null} />
  }

  return (
    <div className="exercise">
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
          {data.days.length === 0 && <p>No exercise logged for this period.</p>}
          {topHeader && (
            <div className="daily-totals">
              <strong>{groupLabel(topHeader.level, topHeader.key)}:</strong>{' '}
              <span className="day-section-summary">
                {renderGroupSummary(topHeader.level, topHeader.key, data.days)}
              </span>
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

import { useEffect, useMemo, useState } from 'react'
import { Chart as ChartJS, LinearScale, CategoryScale, BarElement, Tooltip } from 'chart.js'
import { Bar } from 'react-chartjs-2'
import { getSleep } from '../api'
import {
  formatDisplayDate,
  formatLocalTime,
  formatHoursMinutes,
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

ChartJS.register(LinearScale, CategoryScale, BarElement, Tooltip)

const STAGE_COLORS = {
  AWAKE: '#d9822b',
  LIGHT: '#7fb3d5',
  DEEP: '#2f5f8f',
  REM: '#8e5fb3',
  ASLEEP: '#5fa5a0',
  RESTLESS: '#c9a227',
  UNSPECIFIED: '#999',
}

const BAR_COLOR = '#5fa5a0'

const METRIC_LABELS = {
  totalMinutes: 'Total sleep',
  remMinutes: 'REM',
  deepMinutes: 'Deep',
}

// Toolbar levels, coarsest first - same idea as Food/Heart Rate's toolbar,
// minus the meal-equivalent leaf level (nothing sits below a day here).
const TOOLBAR_LEVELS = [
  { level: 'year', badge: 'Y', title: 'Collapse to year' },
  { level: 'quarter', badge: 'Q', title: 'Collapse to quarter' },
  { level: 'month', badge: 'M', title: 'Collapse to month' },
  { level: 'week', badge: 'W', title: 'Collapse to week' },
  { level: 'day', badge: 'D', title: 'Collapse to day' },
]
const LEVEL_ORDER = TOOLBAR_LEVELS.map((l) => l.level)

// The user's own target bands for REM/Deep sleep - only these two stages
// have a meaningful "was this enough" answer; the others don't get a badge.
const QUALITY_STAGES = new Set(['REM', 'DEEP'])

function sleepQuality(stageType, totalMinutes) {
  if (!QUALITY_STAGES.has(stageType)) return null
  if (totalMinutes < 60) return { label: 'bad', className: 'quality-bad' }
  if (totalMinutes < 75) return { label: 'adequate', className: 'quality-adequate' }
  if (totalMinutes < 90) return { label: 'ok', className: 'quality-ok' }
  return { label: 'good', className: 'quality-good' }
}

// A day's own headline numbers - total time asleep across every session
// that day, plus REM/Deep totals (null, not 0, when that day has no stage
// breakdown at all - e.g. a manually-logged session with no detected
// stages - so averaging elsewhere can skip it rather than dragging the
// average down with a false zero). Single source of truth for the day
// summary line, the group-level averages, and the bar-chart breakdowns.
function dayStats(day) {
  const totalMinutes = day.sessions.reduce((sum, s) => sum + s.duration_minutes, 0)
  const stageSums = {}
  day.sessions.forEach((s) => {
    s.stage_totals.forEach((st) => {
      stageSums[st.stage_type] = (stageSums[st.stage_type] || 0) + st.minutes
    })
  })
  return {
    totalMinutes,
    remMinutes: stageSums.REM ?? null,
    deepMinutes: stageSums.DEEP ?? null,
  }
}


// Average of each day's own value per field, skipping days where that
// particular field is null (a day with no stage breakdown contributes to
// neither REM's nor Deep's average, but still counts toward Total's).
function averageSleepStats(days) {
  const sums = { totalMinutes: 0, remMinutes: 0, deepMinutes: 0 }
  const counts = { totalMinutes: 0, remMinutes: 0, deepMinutes: 0 }
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
// the metric (a sum of a month's sleep minutes isn't a meaningful number).
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

  const chartOptions = {
    plugins: {
      legend: { display: false },
      tooltip: { callbacks: { label: (ctx) => formatHoursMinutes(ctx.parsed.y) } },
    },
    scales: {
      y: { ticks: { callback: (value) => formatHoursMinutes(value) } },
    },
  }

  return (
    <Popup title={title} onClose={onClose}>
      {items.length > 0 ? (
        <div className="chart-wrap">
          <Bar data={chartData} options={chartOptions} />
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

// Plain "·"-joined line (Sleep never used Food/Heart Rate's fixed-column
// grid) shared by the day summary and the group averages - the one place
// REM/Deep quality badges (bad/adequate/ok/good) actually render, per the
// user's own request: the tag/color coding belongs on the totals/averages
// line, not repeated on every session's own graph legend below. `onOpenBar`
// is only given at group levels (Week/Month/Quarter/Year), which have
// something to break down further into a bar chart; a single day's own
// line just shows plain text.
function SleepStatsLine({ totalMinutes, remMinutes, deepMinutes, extra, onOpenBar }) {
  const remQuality = remMinutes !== null ? sleepQuality('REM', remMinutes) : null
  const deepQuality = deepMinutes !== null ? sleepQuality('DEEP', deepMinutes) : null

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
      {piece('totalMinutes', formatHoursMinutes(totalMinutes))}
      {extra && <> · {extra}</>}
      {remMinutes !== null && (
        <>
          {' · '}
          {piece('remMinutes', `REM ${formatHoursMinutes(remMinutes)}`)}
          {remQuality && <span className={`quality-badge ${remQuality.className}`}>{remQuality.label}</span>}
        </>
      )}
      {deepMinutes !== null && (
        <>
          {' · '}
          {piece('deepMinutes', `Deep ${formatHoursMinutes(deepMinutes)}`)}
          {deepQuality && <span className={`quality-badge ${deepQuality.className}`}>{deepQuality.label}</span>}
        </>
      )}
    </span>
  )
}

function DayBody({ sessions }) {
  return (
    <>
      {sessions.map((session) => {
        const totalMinutes =
          session.stage_totals.reduce((sum, s) => sum + s.minutes, 0) || session.duration_minutes
        return (
          <section key={session.id} className="sleep-session">
            <div className="sleep-session-header">
              <strong>{formatHoursMinutes(session.duration_minutes)}</strong>
              <span className="text-muted">
                {formatLocalTime(session.start_time)} – {formatLocalTime(session.end_time)}
              </span>
              {session.sleep_type && <span className="text-muted">{session.sleep_type}</span>}
              {session.main_sleep === true && <span className="text-muted">main sleep</span>}
            </div>

            {session.stages.length > 0 && (
              <>
                {/* Segments in chronological order (not merged by type) so
                    the bar shows the actual progression through the
                    night's sleep cycles, not just total time per stage.
                    Region/start/end/duration live in the hover tooltip
                    instead of a separate list below - too long to scan for
                    a real night's worth of stage transitions. */}
                <div className="stage-bar">
                  {session.stages.map((s, i) => (
                    <div
                      key={i}
                      className="stage-segment"
                      style={{
                        width: `${(s.minutes / totalMinutes) * 100}%`,
                        backgroundColor: STAGE_COLORS[s.stage_type] || '#999',
                      }}
                      title={`${s.stage_type}: ${formatLocalTime(s.start_time)} – ${formatLocalTime(s.end_time)} (${formatHoursMinutes(s.minutes)})`}
                    />
                  ))}
                </div>
                <div className="stage-legend">
                  {/* Plain totals only - no quality tag/color here, per the
                      user's own request: that belongs on the totals/
                      averages line (SleepStatsLine), not repeated on every
                      session's own graph legend. */}
                  {session.stage_totals.map((s) => (
                    <span key={s.stage_type} className="stage-legend-item">
                      <span
                        className="stage-swatch"
                        style={{ backgroundColor: STAGE_COLORS[s.stage_type] || '#999' }}
                      />
                      {s.stage_type} {formatHoursMinutes(s.minutes)}
                    </span>
                  ))}
                </div>
              </>
            )}
          </section>
        )
      })}
    </>
  )
}

export default function Sleep({ userId, view }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [barRequest, setBarRequest] = useState(null)
  const [openState, setOpenState] = useState({})

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getSleep(userId, view)
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
    const avg = averageSleepStats(days)
    const label = groupLabel(level, key)
    function onOpenBar(metric) {
      const title = `${METRIC_LABELS[metric]} — ${label} (${level === 'year' ? 'by month' : 'by day'})`
      const items = level === 'year' ? barDataByMonth(days, metric) : barDataByDay(days, metric)
      setBarRequest({ title, items })
    }
    return (
      <SleepStatsLine
        totalMinutes={avg.totalMinutes}
        remMinutes={avg.remMinutes}
        deepMinutes={avg.deepMinutes}
        onOpenBar={onOpenBar}
      />
    )
  }

  function renderDaySummary(day) {
    const { totalMinutes, remMinutes, deepMinutes } = dayStats(day)
    const extra = day.sessions.length > 1 ? `${day.sessions.length} sessions` : null
    return <SleepStatsLine totalMinutes={totalMinutes} remMinutes={remMinutes} deepMinutes={deepMinutes} extra={extra} />
  }

  function renderDayBody(day) {
    return <DayBody key={day.date} {...day} />
  }

  return (
    <div className="sleep">
      <p className="page-note">Showing sleep that ended on this day.</p>

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
          {data.days.length === 0 && <p>No sleep logged for this period.</p>}
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

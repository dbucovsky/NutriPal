import { useEffect, useMemo, useState } from 'react'
import { Chart as ChartJS, CategoryScale, LinearScale, PointElement, LineElement, BarElement, Tooltip } from 'chart.js'
import { Line, Bar } from 'react-chartjs-2'
import { getWeight } from '../api'
import {
  formatLocalTime,
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

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, BarElement, Tooltip)

const BAR_COLOR = '#2f7d4f'

const METRIC_LABELS = {
  avgWeight: 'Avg weight',
}

// Toolbar levels, coarsest first - same idea as Nutrition/Heart Rate/Sleep/
// Exercise/Steps's toolbar, minus the meal-equivalent leaf level (nothing
// sits below a day here).
const TOOLBAR_LEVELS = [
  { level: 'year', badge: 'Y', title: 'Collapse to year' },
  { level: 'quarter', badge: 'Q', title: 'Collapse to quarter' },
  { level: 'month', badge: 'M', title: 'Collapse to month' },
  { level: 'week', badge: 'W', title: 'Collapse to week' },
  { level: 'day', badge: 'D', title: 'Collapse to day' },
]
const LEVEL_ORDER = TOOLBAR_LEVELS.map((l) => l.level)

// API datetimes are UTC with no 'Z' suffix - same parsing trick as
// formatLocalTime, but returning an epoch for charting on a linear axis.
function readingTimestamp(utcDateTimeStr) {
  return new Date(utcDateTimeStr.replace(' ', 'T') + 'Z').getTime()
}

function round1(value) {
  return Math.round(value * 10) / 10
}

// A day's own headline numbers - single source of truth reused for the day
// summary, the group averages, and the bar-chart breakdowns. weight.php
// only ever returns a day that has at least one reading, so avgWeight is
// never null for a day actually present in `days`.
function dayStats(day) {
  const values = day.readings.map((r) => r.value_lb)
  const avgWeight = round1(values.reduce((a, b) => a + b, 0) / values.length)
  const minWeight = Math.min(...values)
  const maxWeight = Math.max(...values)
  return { avgWeight, minWeight, maxWeight, readingCount: values.length }
}

// Average of each day's own average - the same "average of days' own
// values" convention Heart Rate/Exercise/Steps all use for their own group
// summaries, rather than averaging every individual reading directly (a
// day with 3 readings shouldn't outweigh a day with 1).
function averageWeightStats(days) {
  const values = days.map((day) => dayStats(day).avgWeight)
  const avgWeight = values.length > 0 ? round1(values.reduce((a, b) => a + b, 0) / values.length) : null
  return { avgWeight, dayCount: values.length }
}

// Week/Month/Quarter breakdown: one bar per day in the group, chronological
// (not sorted by value - this is a trend, not a ranking).
function barDataByDay(days) {
  return days.map((day) => ({ label: formatDisplayDate(day.date), value: dayStats(day).avgWeight }))
}

// Year breakdown: one bar per month, averaging that month's own days -
// same convention as Exercise/Heart Rate/Steps's own Year breakdowns.
function barDataByMonth(days) {
  const byMonth = new Map()
  for (const day of days) {
    const value = dayStats(day).avgWeight
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

// Plain "·"-joined line shared by the day summary and the group averages -
// same style as Exercise/Steps's own stats line. `onOpenBar` is only given
// at group levels (Week/Month/Quarter/Year), which have something to break
// down further into a bar chart; a single day's own line just shows text.
function WeightStatsLine({ avgWeight, extra, onOpenBar }) {
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
      {piece(`${avgWeight} lb avg`)}
      {extra && <> · {extra}</>}
    </span>
  )
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

export default function Weight({ userId, view }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [barRequest, setBarRequest] = useState(null)
  const [openState, setOpenState] = useState({})

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getWeight(userId, view)
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

  // Flattened across every day in range, regardless of the tree's own
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
    const avg = averageWeightStats(days)
    function onOpenBar() {
      const label = groupLabel(level, key)
      if (level === 'year') {
        setBarRequest({ title: `${METRIC_LABELS.avgWeight} — ${label} (by month)`, items: barDataByMonth(days) })
      } else {
        setBarRequest({ title: `${METRIC_LABELS.avgWeight} — ${label} (by day)`, items: barDataByDay(days) })
      }
    }
    if (avg.avgWeight === null) return null
    return <WeightStatsLine avgWeight={avg.avgWeight} extra={`${avg.dayCount} ${avg.dayCount === 1 ? 'day' : 'days'} logged`} onOpenBar={onOpenBar} />
  }

  function renderDaySummary(day) {
    const { avgWeight, minWeight, maxWeight, readingCount } = dayStats(day)
    const extra =
      readingCount > 1
        ? `${readingCount} readings${minWeight !== maxWeight ? ` (${minWeight}–${maxWeight} lb)` : ''}`
        : null
    return <WeightStatsLine avgWeight={avgWeight} extra={extra} />
  }

  function renderDayBody(day) {
    return <DayBody key={day.date} readings={day.readings} />
  }

  return (
    <div className="weight">
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
          {data.days.length === 0 && <p>No weight logged for this period.</p>}

          {points.length > 1 && (
            <div className="chart-wrap">
              <Line data={chartData} options={chartOptions} />
            </div>
          )}

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

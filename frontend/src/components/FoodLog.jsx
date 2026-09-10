import { useEffect, useMemo, useState } from 'react'
import { Chart as ChartJS, ArcElement, Tooltip as ChartTooltip, Legend } from 'chart.js'
import { Pie } from 'react-chartjs-2'
import { getFoodLog } from '../api'
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
import FoodTree, { buildTree, enumerateNodeKeys, defaultOpenFor, LEVEL_PREFIX } from './FoodTree'
import Popup from './Popup'

ChartJS.register(ArcElement, ChartTooltip, Legend)

const MEAL_ORDER = ['BREAKFAST', 'LUNCH', 'DINNER', 'EARLY_SNACK', 'MORNING_SNACK', 'AFTERNOON_SNACK', 'LATE_NIGHT_SNACK']
const MEAL_LABELS = {
  BREAKFAST: 'Breakfast',
  LUNCH: 'Lunch',
  DINNER: 'Dinner',
  EARLY_SNACK: 'Early Snack',
  MORNING_SNACK: 'Morning Snack',
  AFTERNOON_SNACK: 'Afternoon Snack',
  LATE_NIGHT_SNACK: 'Late Night Snack',
}

const METRIC_LABELS = {
  energy_kcal: 'Calories',
  protein_g: 'Protein',
  carb_g: 'Carbs',
  fat_g: 'Fat',
}

const PIE_COLORS = [
  '#2f7d4f', '#d9822b', '#7fb3d5', '#8e5fb3', '#c9a227', '#b3261e',
  '#5fa5a0', '#6b6375', '#2f5f8f', '#e07a5f',
]

// Toolbar levels, coarsest first - matches FoodTree's own hierarchy plus
// the Food-only "meal" leaf level.
const TOOLBAR_LEVELS = [
  { level: 'year', badge: 'Y', title: 'Collapse to year' },
  { level: 'quarter', badge: 'Q', title: 'Collapse to quarter' },
  { level: 'month', badge: 'M', title: 'Collapse to month' },
  { level: 'week', badge: 'W', title: 'Collapse to week' },
  { level: 'day', badge: 'D', title: 'Collapse to day' },
  { level: 'meal', badge: 'Me', title: 'Collapse to meal' },
]
const LEVEL_ORDER = TOOLBAR_LEVELS.map((l) => l.level)

function round2(value) {
  return Math.round(value * 100) / 100
}

function macro(value, unit = 'g') {
  return value === null || value === undefined ? '—' : `${value}${unit}`
}

// Meal-total thresholds are tighter than day/period-average ones (a single
// meal isn't meant to carry a whole day's budget); day totals and
// week/month/quarter/year averages share the same numbers, per the user's
// own spec. Carb/fat checks are skipped entirely under 200 kcal, where
// ratios are noisy/meaningless on a near-empty meal or day. Red implies
// yellow (checked first); protein only ever gets a positive "green", never
// a warning color; missing inputs just skip that cell's color rather than
// guessing.
function classifyMacros({ energy_kcal, protein_g, carb_g, fat_g }, profile) {
  const t = profile === 'meal'
    ? { calYellow: 750, calRed: 1200, protGreen: 30 }
    : { calYellow: 1800, calRed: 2100, protGreen: 140 }

  const energyClass =
    energy_kcal == null ? null : energy_kcal > t.calRed ? 'warn-red' : energy_kcal > t.calYellow ? 'warn-yellow' : null
  const proteinClass = protein_g == null ? null : protein_g > t.protGreen ? 'warn-green' : null

  let carbClass = null
  let fatClass = null
  if (energy_kcal != null && energy_kcal > 200) {
    if (protein_g != null && carb_g != null) {
      carbClass = carb_g > protein_g * 3 ? 'warn-red' : carb_g > protein_g * 2 ? 'warn-yellow' : null
    }
    if (fat_g != null) {
      const fatShare = (fat_g * 9) / energy_kcal
      fatClass = fatShare > 0.35 ? 'warn-red' : fatShare > 0.2 ? 'warn-yellow' : null
    }
  }

  return { energyClass, proteinClass, carbClass, fatClass }
}

// Fixed-width 7-column grid (kcal-value | "Prot" | value | "Carb" | value |
// "Fat" | value) so digits line up regardless of label width - reused
// everywhere a macro line is shown (entries, meal/day summaries, week/
// month/quarter/year averages), so values line up both down one day and
// across different days/periods.
function MacroRow({ energyKcal, proteinG, carbG, fatG, onClickMetric, colorClasses }) {
  const c = colorClasses || {}

  function cell(value, unit, metric, colorClass) {
    const content = macro(value, unit)
    const className = ['macro-cell-value', colorClass].filter(Boolean).join(' ')
    if (!onClickMetric) {
      return <span className={className}>{content}</span>
    }
    return (
      <button
        type="button"
        className={`${className} macro-cell-clickable`}
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
    <span className="macro-grid">
      {cell(energyKcal, ' kcal', 'energy_kcal', c.energyClass)}
      <span className="macro-cell-label">Prot</span>
      {cell(proteinG, 'g', 'protein_g', c.proteinClass)}
      <span className="macro-cell-label">Carb</span>
      {cell(carbG, 'g', 'carb_g', c.carbClass)}
      <span className="macro-cell-label">Fat</span>
      {cell(fatG, 'g', 'fat_g', c.fatClass)}
    </span>
  )
}

function macroRowFromTotals(totals, onClickMetric, profile) {
  return (
    <MacroRow
      energyKcal={totals.energy_kcal}
      proteinG={totals.protein_g}
      carbG={totals.carb_g}
      fatG={totals.fat_g}
      onClickMetric={onClickMetric}
      colorClasses={classifyMacros(totals, profile)}
    />
  )
}

function mealTotals(entries) {
  const totals = { energy_kcal: 0, protein_g: 0, carb_g: 0, fat_g: 0 }
  let any = false
  for (const key of Object.keys(totals)) {
    for (const entry of entries) {
      if (entry[key] !== null && entry[key] !== undefined) {
        totals[key] += entry[key]
        any = true
      }
    }
    totals[key] = any ? round2(totals[key]) : null
    any = false
  }
  return totals
}

// Sum of each day's own total / number of days with data in the group -
// day totals are never null (see food-log.php), so no null-skipping needed.
function averageTotals(days) {
  const sums = { energy_kcal: 0, protein_g: 0, carb_g: 0, fat_g: 0 }
  for (const day of days) {
    for (const key of Object.keys(sums)) {
      sums[key] += day.totals[key]
    }
  }
  const n = days.length || 1
  const avg = {}
  for (const key of Object.keys(sums)) {
    avg[key] = round2(sums[key] / n)
  }
  return avg
}

// Per-food contribution to one metric across a set of entries - grouped by
// (name, brand) so a food logged twice is one slice, not two. Used for
// both day-level (all of a day's entries) and meal-level (just that
// meal's entries) pies.
function pieDataForEntries(entries, metric) {
  const byFood = new Map()
  for (const entry of entries) {
    const value = entry[metric]
    if (!value) continue
    const key = entry.brand_name ? `${entry.name} (${entry.brand_name})` : entry.name
    byFood.set(key, (byFood.get(key) || 0) + value)
  }
  return [...byFood.entries()]
    .map(([label, value]) => ({ label, value: round2(value) }))
    .sort((a, b) => b.value - a.value)
}

// Week/Month/Quarter pies: one slice per day in the group, sized by that
// day's own total (not average) for the metric.
function pieDataByDay(days, metric) {
  return days
    .map((day) => ({ label: formatDisplayDate(day.date), value: day.totals[metric] }))
    .filter((item) => item.value)
    .sort((a, b) => b.value - a.value)
}

// Year pies: one slice per month, sized by that month's own total.
function pieDataByMonth(days, metric) {
  const byMonth = new Map()
  for (const day of days) {
    const key = day.date.slice(0, 7)
    byMonth.set(key, (byMonth.get(key) || 0) + day.totals[metric])
  }
  return [...byMonth.entries()]
    .map(([key, value]) => ({ label: formatMonthLabel(`${key}-01`), value: round2(value) }))
    .filter((item) => item.value)
    .sort((a, b) => b.value - a.value)
}

function MacroPiePopup({ title, items, onClose }) {
  const chartData = {
    labels: items.map((i) => i.label),
    datasets: [
      {
        data: items.map((i) => i.value),
        backgroundColor: items.map((_, i) => PIE_COLORS[i % PIE_COLORS.length]),
      },
    ],
  }

  return (
    <Popup title={title} onClose={onClose}>
      {items.length > 0 ? (
        <div className="chart-wrap">
          <Pie data={chartData} options={{ plugins: { legend: { position: 'right' } } }} />
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

// Small icon-badge toolbar for the collapse/expand quick actions. Buttons
// for a level with no matching node in the current data are disabled
// (e.g. Y/Q/M gray out on a Week view, which never produces those nodes).
function FoodToolbar({ availableLevels, onExpandAll, onCollapseAll, onCollapseTo, onReset }) {
  return (
    <div className="food-toolbar">
      <button type="button" className="toolbar-badge" title="Expand all" onClick={onExpandAll}>
        ⤓
      </button>
      <button type="button" className="toolbar-badge" title="Collapse all" onClick={onCollapseAll}>
        ⤒
      </button>
      <span className="toolbar-sep" />
      {TOOLBAR_LEVELS.map(({ level, badge, title }) => (
        <button
          key={level}
          type="button"
          className="toolbar-badge"
          title={title}
          disabled={!availableLevels.has(level)}
          onClick={() => onCollapseTo(level)}
        >
          {badge}
        </button>
      ))}
      <span className="toolbar-sep" />
      <button type="button" className="toolbar-badge" title="Reset to default" onClick={onReset}>
        ↻
      </button>
    </div>
  )
}

export default function FoodLog({ userId, view }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [pieRequest, setPieRequest] = useState(null)
  const [openState, setOpenState] = useState({})

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getFoodLog(userId, view)
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

  // A view's own granularity (week/month/year) always spans exactly one such
  // period, so buildTree's "skip a level with only one group" rule always
  // collapses it away - same reason the single-day case needs its own totals
  // line above the meals (item 1). This mirrors that for week/month/year
  // (items 6/8/9): a top summary line for the period being viewed, computed
  // from every day in range, shown above whatever buildTree did produce.
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

  function openPie(metric, title, items) {
    setPieRequest({ metric, title, items })
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
    setOpenState(
      Object.fromEntries(nodeKeys.map(({ key, level }) => [key, LEVEL_ORDER.indexOf(level) < targetIndex]))
    )
  }

  function handleReset() {
    setOpenState({})
  }

  function renderDaySummary(day) {
    const onClickMetric = (metric) => {
      const entries = Object.values(day.meals).flat()
      openPie(metric, `${METRIC_LABELS[metric]} — ${formatDisplayDate(day.date)}`, pieDataForEntries(entries, metric))
    }
    return macroRowFromTotals(day.totals, onClickMetric, 'day')
  }

  function renderGroupSummary(level, key, days) {
    const avg = averageTotals(days)
    const onClickMetric = (metric) => {
      const label = groupLabel(level, key)
      if (level === 'year') {
        openPie(metric, `${METRIC_LABELS[metric]} — ${label} (by month)`, pieDataByMonth(days, metric))
      } else {
        openPie(metric, `${METRIC_LABELS[metric]} — ${label} (by day)`, pieDataByDay(days, metric))
      }
    }
    return macroRowFromTotals(avg, onClickMetric, 'day')
  }

  function renderDayBody(day) {
    return (
      <>
        {MEAL_ORDER.filter((meal) => day.meals[meal]?.length).map((meal) => {
          const mealKey = `${LEVEL_PREFIX.meal}:${day.date}:${meal}`
          const isOpen = mealKey in openState ? openState[mealKey] : defaultOpenFor('meal')
          const entries = day.meals[meal]
          const totals = mealTotals(entries)
          const onClickMetric = (metric) =>
            openPie(
              metric,
              `${METRIC_LABELS[metric]} — ${MEAL_LABELS[meal]}, ${formatDisplayDate(day.date)}`,
              pieDataForEntries(entries, metric)
            )
          return (
            <details
              key={meal}
              className="meal-section"
              open={isOpen}
              onToggle={(e) => handleToggle(mealKey, e.currentTarget.open)}
            >
              <summary>
                <span className="meal-section-title">{MEAL_LABELS[meal]}</span>
                <span className="meal-section-summary">{macroRowFromTotals(totals, onClickMetric, 'meal')}</span>
              </summary>
              {isOpen && (
                <ul>
                  {entries.map((entry) => (
                    <li key={entry.id} className="food-entry">
                      <div className="food-entry-name">
                        {entry.name}
                        {entry.brand_name && <span className="brand"> ({entry.brand_name})</span>}
                      </div>
                      <div className="food-entry-serving">
                        {entry.serving_amount} {entry.serving_unit_label}
                      </div>
                      <div className="food-entry-macros">
                        <MacroRow
                          energyKcal={entry.energy_kcal}
                          proteinG={entry.protein_g}
                          carbG={entry.carb_g}
                          fatG={entry.fat_g}
                        />
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </details>
          )
        })}
      </>
    )
  }

  return (
    <div className="food-log">
      <FoodToolbar
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
          {data.days.length === 0 && <p>No food logged for this period.</p>}
          {topHeader && (
            <div className="daily-totals">
              <strong>{groupLabel(topHeader.level, topHeader.key)}:</strong>{' '}
              <span className="day-section-summary">{renderGroupSummary(topHeader.level, topHeader.key, data.days)}</span>
            </div>
          )}
          <FoodTree
            tree={tree}
            openState={openState}
            onToggle={handleToggle}
            renderGroupSummary={renderGroupSummary}
            renderDaySummary={renderDaySummary}
            renderDayBody={renderDayBody}
          />
        </>
      )}

      {pieRequest && (
        <MacroPiePopup title={pieRequest.title} items={pieRequest.items} onClose={() => setPieRequest(null)} />
      )}
    </div>
  )
}

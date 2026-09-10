import {
  formatDisplayDate,
  formatWeekLabel,
  formatMonthLabel,
  formatQuarterLabel,
  formatYearLabel,
  weekKey,
  monthKey,
  quarterKey,
  yearKey,
} from '../dateUtils'

// Coarsest first - a day gets grouped into a year, then a quarter within
// that year, then a month within that quarter, then a week within that
// month. Any level that would only produce a single group for this
// particular range is skipped entirely (see groupAndRender below), so a
// Week view (where every level here collapses to one group) falls
// straight through to the flat day list - pixel-identical to before this
// hierarchy existed.
const GROUP_LEVELS = [
  { keyFn: yearKey, labelFn: (key) => formatYearLabel(`${key}-01-01`), className: 'year-section', defaultOpen: false },
  { keyFn: quarterKey, labelFn: formatQuarterLabel, className: 'quarter-section', defaultOpen: false },
  { keyFn: monthKey, labelFn: (key) => formatMonthLabel(`${key}-01`), className: 'month-section', defaultOpen: false },
  { keyFn: weekKey, labelFn: formatWeekLabel, className: 'week-section', defaultOpen: true },
]

function groupBy(days, keyFn) {
  const groups = []
  const byKey = new Map()
  for (const day of days) {
    const key = keyFn(day.date)
    let group = byKey.get(key)
    if (!group) {
      group = { key, days: [] }
      byKey.set(key, group)
      groups.push(group)
    }
    group.days.push(day)
  }
  return groups
}

// Open-by-default only for short day-level lists (≤7, i.e. at most a
// week's worth); month/year default collapsed so a year view doesn't open
// hundreds of day sections at once. `renderSummary(day)`, when given,
// renders aggregated stats (e.g. daily totals) into the day's summary
// line itself, so collapsing a day doesn't hide the one thing worth
// seeing about it at a glance.
function renderDays(days, renderDay, renderSummary) {
  if (days.length === 1) {
    return renderDay(days[0])
  }
  const defaultOpen = days.length <= 7
  return days.map((day) => (
    <details key={day.date} className="day-section" open={defaultOpen}>
      <summary className="day-section-header">
        <span className="day-section-title">{formatDisplayDate(day.date)}</span>
        {renderSummary && <span className="day-section-summary">{renderSummary(day)}</span>}
      </summary>
      {renderDay(day)}
    </details>
  ))
}

function renderLevel(days, levelIndex, renderDay, renderSummary) {
  if (levelIndex >= GROUP_LEVELS.length) {
    return renderDays(days, renderDay, renderSummary)
  }
  const level = GROUP_LEVELS[levelIndex]
  const groups = groupBy(days, level.keyFn)
  if (groups.length <= 1) {
    // No point wrapping everything in a group that only contains itself -
    // skip straight to the next finer level.
    return renderLevel(days, levelIndex + 1, renderDay, renderSummary)
  }
  return groups.map((group) => (
    <details key={group.key} className={level.className} open={level.defaultOpen}>
      <summary className="group-section-header">{level.labelFn(group.key)}</summary>
      {renderLevel(group.days, levelIndex + 1, renderDay, renderSummary)}
    </details>
  ))
}

export default function MultiDay({ days, renderDay, renderSummary }) {
  if (days.length === 0) {
    return null
  }
  if (days.length === 1) {
    return renderDay(days[0])
  }

  return <>{renderLevel(days, 0, renderDay, renderSummary)}</>
}

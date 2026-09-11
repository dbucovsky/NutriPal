import {
  formatDisplayDate,
  formatWeekNumberLabel,
  formatMonthLabel,
  formatQuarterLabel,
  formatYearLabel,
  weekKey,
  monthKey,
  quarterKey,
  yearKey,
} from '../dateUtils'

// Food-specific fork of MultiDay.jsx's hierarchy - kept separate rather
// than further overloading the shared component, since Food's needs
// (mixed total/average semantics per level, per-level pie scoping, a
// toolbar-drivable *controlled* open/closed state instead of the plain
// uncontrolled default MultiDay uses, week-number labels, meal-level
// sub-grouping) don't apply to any of the other five pages still using
// MultiDay as-is.
export const LEVEL_PREFIX = { year: 'Y', quarter: 'Q', month: 'M', week: 'W', day: 'D', meal: 'Me' }

const GROUP_LEVELS = [
  { level: 'year', keyFn: yearKey, labelFn: (key) => formatYearLabel(`${key}-01-01`) },
  { level: 'quarter', keyFn: quarterKey, labelFn: formatQuarterLabel },
  { level: 'month', keyFn: monthKey, labelFn: (key) => formatMonthLabel(`${key}-01`) },
  { level: 'week', keyFn: weekKey, labelFn: formatWeekNumberLabel },
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

// Builds the same year->quarter->month->week->day tree once, so both
// rendering and key-enumeration (for the toolbar) walk identical
// structure - a level that would only produce a single group for this
// data is skipped entirely, exactly like MultiDay.
export function buildTree(days) {
  function build(subset, levelIndex) {
    if (levelIndex >= GROUP_LEVELS.length) {
      return subset.map((day) => ({ type: 'day', date: day.date, day }))
    }
    const level = GROUP_LEVELS[levelIndex]
    const groups = groupBy(subset, level.keyFn)
    if (groups.length <= 1) {
      return build(subset, levelIndex + 1)
    }
    return groups.map((group) => ({
      type: level.level,
      key: group.key,
      label: level.labelFn(group.key),
      days: group.days,
      children: build(group.days, levelIndex + 1),
    }))
  }
  return build(days, 0)
}

// Every node's stable key, plus the day-level's meal sub-keys (meals are
// rendered by FoodLog itself, not FoodTree, but the toolbar needs to know
// they exist too). Used both to seed default open/closed state and to
// tell the toolbar which "collapse to <level>" buttons are meaningful for
// the data currently on screen.
export function enumerateNodeKeys(tree) {
  const keys = []
  function walk(nodes) {
    for (const node of nodes) {
      if (node.type === 'day') {
        keys.push({ key: `${LEVEL_PREFIX.day}:${node.date}`, level: 'day' })
        for (const mealKey of Object.keys(node.day.meals)) {
          keys.push({ key: `${LEVEL_PREFIX.meal}:${node.date}:${mealKey}`, level: 'meal' })
        }
      } else {
        keys.push({ key: `${LEVEL_PREFIX[node.type]}:${node.key}`, level: node.type })
        walk(node.children)
      }
    }
  }
  walk(tree)
  return keys
}

// Everything defaults closed, at every level - the toolbar's own "Collapse
// all" and the natural first-load/Reset state should be the same thing,
// not two different heuristics to keep in sync. Expanding anything is then
// always a deliberate click, via the toolbar's Expand all/collapse-to-level
// or a section's own toggle.
export function defaultOpenFor() {
  return false
}

function renderNodes(nodes, openState, onToggle, renderGroupSummary, renderDaySummary, renderDayBody) {
  return nodes.map((node) => {
    if (node.type === 'day') {
      const key = `${LEVEL_PREFIX.day}:${node.date}`
      const isOpen = key in openState ? openState[key] : defaultOpenFor('day')
      return (
        <details key={key} className="day-section" open={isOpen} onToggle={(e) => onToggle(key, e.currentTarget.open)}>
          <summary className="day-section-header">
            <span className="day-section-title">{formatDisplayDate(node.date)}</span>
            <span className="day-section-summary">{renderDaySummary(node.day)}</span>
          </summary>
          {isOpen && renderDayBody(node.day)}
        </details>
      )
    }
    const key = `${LEVEL_PREFIX[node.type]}:${node.key}`
    const isOpen = key in openState ? openState[key] : defaultOpenFor(node.type)
    return (
      <details
        key={key}
        className={`${node.type}-section`}
        open={isOpen}
        onToggle={(e) => onToggle(key, e.currentTarget.open)}
      >
        <summary className="tree-group-header">
          <span className="tree-group-title">{node.label}</span>
          <span className="day-section-summary">{renderGroupSummary(node.type, node.key, node.days)}</span>
        </summary>
        {isOpen && renderNodes(node.children, openState, onToggle, renderGroupSummary, renderDaySummary, renderDayBody)}
      </details>
    )
  })
}

export default function FoodTree({ tree, openState, onToggle, renderGroupSummary, renderDaySummary, renderDayBody }) {
  if (tree.length === 0) {
    return null
  }
  if (tree.length === 1 && tree[0].type === 'day') {
    // Single day, no range to collapse - still show the day's own totals
    // line (with links) above its meals, just without a pointless toggle.
    return (
      <>
        <div className="daily-totals">
          <strong>Totals:</strong> <span className="day-section-summary">{renderDaySummary(tree[0].day)}</span>
        </div>
        {renderDayBody(tree[0].day)}
      </>
    )
  }
  return <>{renderNodes(tree, openState, onToggle, renderGroupSummary, renderDaySummary, renderDayBody)}</>
}

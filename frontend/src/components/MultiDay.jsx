import { formatDisplayDate } from '../dateUtils'

// Renders `days` (the API's day-grouped array) as a collapsible section per
// day when there's more than one, or the bare day content when there's
// just one (view=day, or a range that happened to only have one day of
// data) - so single-day pages stay pixel-identical to before this existed.
// Open-by-default only for short ranges (week/custom-few-days); month/year
// default collapsed so a year view doesn't open up to 365 sections at once.
// `renderSummary(day)`, when given, renders aggregated stats (e.g. daily
// totals) into the summary line itself, so collapsing a day doesn't hide
// the one thing worth seeing about it at a glance.
export default function MultiDay({ days, renderDay, renderSummary }) {
  if (days.length === 0) {
    return null
  }
  if (days.length === 1) {
    return renderDay(days[0])
  }

  const defaultOpen = days.length <= 7

  return (
    <>
      {days.map((day) => (
        <details key={day.date} className="day-section" open={defaultOpen}>
          <summary className="day-section-header">
            <span className="day-section-title">{formatDisplayDate(day.date)}</span>
            {renderSummary && <span className="day-section-summary">{renderSummary(day)}</span>}
          </summary>
          {renderDay(day)}
        </details>
      ))}
    </>
  )
}

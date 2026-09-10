import { formatDisplayDate } from '../dateUtils'

// Renders `days` (the API's day-grouped array) as a collapsible section per
// day when there's more than one, or the bare day content when there's
// just one (view=day, or a range that happened to only have one day of
// data) - so single-day pages stay pixel-identical to before this existed.
// Open-by-default only for short ranges (week/custom-few-days); month/year
// default collapsed so a year view doesn't open up to 365 sections at once.
export default function MultiDay({ days, renderDay }) {
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
          <summary className="day-section-header">{formatDisplayDate(day.date)}</summary>
          {renderDay(day)}
        </details>
      ))}
    </>
  )
}

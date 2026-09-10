export function todayLocal() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

const WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
const MONTHS = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
]

// "Tuesday 08-Sep-2026" - anchored at UTC noon so this never shifts to an
// adjacent calendar date due to a DST transition or the browser's own
// timezone (dateStr is a plain YYYY-MM-DD with no time/zone of its own).
export function formatDisplayDate(dateStr) {
  const d = new Date(`${dateStr}T12:00:00Z`)
  const weekday = WEEKDAYS[d.getUTCDay()]
  const day = String(d.getUTCDate()).padStart(2, '0')
  const month = MONTHS[d.getUTCMonth()]
  const year = d.getUTCFullYear()
  return `${weekday} ${day}-${month}-${year}`
}

// API endpoints return UTC datetime strings with no 'Z' suffix (e.g.
// "2026-09-05 03:16:00") - append it so the browser's Date parses them as
// UTC and displays them converted to the viewer's own local time.
export function formatLocalTime(utcDateTimeStr) {
  const d = new Date(utcDateTimeStr.replace(' ', 'T') + 'Z')
  return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
}

// "1:15" (H:MM) - always hours:minutes, never bare minutes, per the user's
// preference for reading sleep durations.
export function formatHoursMinutes(minutes) {
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return `${h}:${String(m).padStart(2, '0')}`
}

// Same UTC-noon-anchor trick as formatDisplayDate, so date arithmetic never
// shifts a plain YYYY-MM-DD across a DST boundary or the browser's own zone.
function toDate(dateStr) {
  return new Date(`${dateStr}T12:00:00Z`)
}

function toDateStr(d) {
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-${String(d.getUTCDate()).padStart(2, '0')}`
}

export function addDays(dateStr, n) {
  const d = toDate(dateStr)
  d.setUTCDate(d.getUTCDate() + n)
  return toDateStr(d)
}

export function addMonths(dateStr, n) {
  const d = toDate(dateStr)
  d.setUTCMonth(d.getUTCMonth() + n)
  return toDateStr(d)
}

export function addYears(dateStr, n) {
  const d = toDate(dateStr)
  d.setUTCFullYear(d.getUTCFullYear() + n)
  return toDateStr(d)
}

export function startOfWeek(dateStr) {
  const d = toDate(dateStr)
  return addDays(dateStr, -d.getUTCDay())
}

export function startOfMonth(dateStr) {
  const d = toDate(dateStr)
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-01`
}

export function startOfYear(dateStr) {
  const d = toDate(dateStr)
  return `${d.getUTCFullYear()}-01-01`
}

// Given the current view's anchor date, computes the next/previous anchor
// (direction = 1 or -1) - steps by the view's own period so "next" on a
// month view moves a whole month, not a single day.
export function stepDateByView(dateStr, viewType, direction) {
  switch (viewType) {
    case 'week':
      return addDays(dateStr, 7 * direction)
    case 'month':
      return addMonths(startOfMonth(dateStr), direction)
    case 'year':
      return addYears(startOfYear(dateStr), direction)
    default:
      return addDays(dateStr, direction)
  }
}

function formatMonthDay(dateStr) {
  const d = toDate(dateStr)
  return `${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}`
}

export function formatWeekLabel(dateStr) {
  const start = startOfWeek(dateStr)
  const end = addDays(start, 6)
  const year = toDate(end).getUTCFullYear()
  return `${formatMonthDay(start)} – ${formatMonthDay(end)}, ${year}`
}

const FULL_MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]

export function formatMonthLabel(dateStr) {
  const d = toDate(dateStr)
  return `${FULL_MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`
}

export function formatYearLabel(dateStr) {
  return String(toDate(dateStr).getUTCFullYear())
}

export function formatRangeLabel(startDateStr, endDateStr) {
  if (startDateStr === endDateStr) return formatDisplayDate(startDateStr)
  const startYear = toDate(startDateStr).getUTCFullYear()
  const endYear = toDate(endDateStr).getUTCFullYear()
  const start = startYear === endYear ? formatMonthDay(startDateStr) : `${formatMonthDay(startDateStr)}, ${startYear}`
  return `${start} – ${formatMonthDay(endDateStr)}, ${endYear}`
}

// Grouping keys for MultiDay's hierarchical day->week->month->quarter->year
// collapsing - plain string slicing/math, no Date object, so there's no
// timezone footgun to worry about (a YYYY-MM-DD string's own year/month
// digits are unambiguous regardless of the viewer's local zone).
export function weekKey(dateStr) {
  return startOfWeek(dateStr)
}

export function monthKey(dateStr) {
  return dateStr.slice(0, 7)
}

export function quarterKey(dateStr) {
  const year = dateStr.slice(0, 4)
  const month = Number(dateStr.slice(5, 7))
  const quarter = Math.floor((month - 1) / 3) + 1
  return `${year}-Q${quarter}`
}

export function yearKey(dateStr) {
  return dateStr.slice(0, 4)
}

export function formatQuarterLabel(quarterKeyStr) {
  const [year, q] = quarterKeyStr.split('-Q')
  return `Q${q} ${year}`
}

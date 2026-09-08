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

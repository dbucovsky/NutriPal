export function todayLocal() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export function shiftDate(dateStr, days) {
  // Anchor at UTC noon so adding/subtracting a day never lands on a
  // different calendar date due to a DST transition.
  const d = new Date(`${dateStr}T12:00:00Z`)
  d.setUTCDate(d.getUTCDate() + days)
  return d.toISOString().slice(0, 10)
}

// API endpoints return UTC datetime strings with no 'Z' suffix (e.g.
// "2026-09-05 03:16:00") - append it so the browser's Date parses them as
// UTC and displays them converted to the viewer's own local time.
export function formatLocalTime(utcDateTimeStr) {
  const d = new Date(utcDateTimeStr.replace(' ', 'T') + 'Z')
  return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
}

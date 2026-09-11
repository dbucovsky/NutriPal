// Classic 5-zone heart-rate-training model, as % of Max HR - shared between
// the Exercise tab's own zone badges (Exercise.jsx) and the session bpm-curve
// popups (SessionHrPopup.jsx, HeartRate.jsx's own exercise-session popup)
// so the color mapping is defined once. Below 50% isn't a trained "zone" in
// this model - hrZone() returns null there, and callers fall back to a
// neutral color/no badge. `color` hex values must match .hr-zone-1..5 in
// App.css (badges use the CSS classes directly; charts need real hex since
// Chart.js can't read CSS classes).
export const HR_ZONES = [
  { min: 0.9, key: 5, label: 'Zone 5 · Maximum', className: 'hr-zone-5', color: '#b3261e' },
  { min: 0.8, key: 4, label: 'Zone 4 · Hard', className: 'hr-zone-4', color: '#d9822b' },
  { min: 0.7, key: 3, label: 'Zone 3 · Moderate', className: 'hr-zone-3', color: '#c9a227' },
  { min: 0.6, key: 2, label: 'Zone 2 · Aerobic', className: 'hr-zone-2', color: '#3a8a4d' },
  { min: 0.5, key: 1, label: 'Zone 1 · Very Light', className: 'hr-zone-1', color: '#5b8fc9' },
]

export function hrZone(bpm, maxHr) {
  if (!bpm || !maxHr) return null
  const pct = bpm / maxHr
  return HR_ZONES.find((z) => pct >= z.min) ?? null
}

function hexToRgba(hex, alpha) {
  const n = parseInt(hex.slice(1), 16)
  const r = (n >> 16) & 255
  const g = (n >> 8) & 255
  const b = n & 255
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

// Horizontal chartjs-plugin-annotation boxes, one per zone, spanning the
// bpm range that zone covers for this maxHr - a background band, not a
// per-segment line color, since two adjacent zone colors (e.g. green/gold)
// were hard to tell apart as a thin line and green collided visually with
// the line's own default color. Below Zone 1 (under 50% of maxHr) is left
// unshaded. The topmost zone (5) has no yMax, so its band stretches to
// whatever the chart's own y-axis max ends up being.
export function zoneBandAnnotations(maxHr) {
  if (!maxHr) return {}
  const annotations = {}
  HR_ZONES.forEach((zone, i) => {
    annotations[`hrZoneBand${zone.key}`] = {
      type: 'box',
      yMin: zone.min * maxHr,
      yMax: i === 0 ? undefined : HR_ZONES[i - 1].min * maxHr,
      backgroundColor: hexToRgba(zone.color, 0.16),
      borderWidth: 0,
      drawTime: 'beforeDatasetsDraw',
    }
  })
  return annotations
}

// This zone's actual bpm range for a given maxHr, for the legend - the
// same zone can mean a different bpm window per person/date, so a bare
// "Zone 3" label alone doesn't say much without it.
export function zoneRangeLabel(zone, maxHr) {
  const zoneIndex = HR_ZONES.findIndex((z) => z.key === zone.key)
  const low = Math.round(zone.min * maxHr)
  if (zoneIndex === 0) {
    return `${low}+ bpm`
  }
  const high = Math.round(HR_ZONES[zoneIndex - 1].min * maxHr) - 1
  return `${low}–${high} bpm`
}

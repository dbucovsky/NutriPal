import { HR_ZONES, zoneRangeLabel } from '../hrZones'

// Z1..Z5 color key for a zone-banded bpm chart (SessionHrPopup.jsx,
// HeartRate.jsx's exercise-session popup), with each zone's actual bpm
// range for this chart's own maxHr - the same zone number covers a
// different bpm window per person/date, so the color alone doesn't say much.
export default function ZoneLegend({ maxHr }) {
  return (
    <div className="hr-zone-legend">
      {[...HR_ZONES].reverse().map((z) => (
        <span key={z.key} className="hr-zone-legend-item">
          <span className={`quality-badge ${z.className}`}>Z{z.key}</span>
          {z.label.split(' · ')[1]}
          {maxHr && <span className="text-muted"> ({zoneRangeLabel(z, maxHr)})</span>}
        </span>
      ))}
    </div>
  )
}

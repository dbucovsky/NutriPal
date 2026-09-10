import { useEffect, useState } from 'react'
import { getAppVersion } from '../api'

export function AboutPanel() {
  const [version, setVersion] = useState(null)

  useEffect(() => {
    let cancelled = false
    getAppVersion()
      .then((v) => {
        if (!cancelled) setVersion(v)
      })
      .catch(() => {
        // Non-fatal: version line just stays blank.
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div>
      <p>
        <strong>NutriPal</strong>
        {version && <span className="text-muted"> — {version}</span>}
      </p>
      <p className="text-muted">
        A personal health-tracking app pulling nutrition, sleep, exercise, heart rate, weight, and step data from
        Google Health and Health Connect.
      </p>
    </div>
  )
}

export function HelpPanel() {
  return (
    <div>
      <p>
        <strong>Food, Heart Rate, Sleep, Exercise, Weight, Steps</strong> — browse your logged health data. Use the
        Day/Week/Month/Year/Custom buttons above the tabs to change the range; multi-day views collapse into
        weeks/months/quarters/years.
      </p>
      <p>
        <strong>Quick sync</strong> (the arrow icon) — pulls in new data since your last sync, one click, no options.
      </p>
      <p>
        <strong>Sync</strong> (this menu) — the full sync page: a full-history resync, replaying a prior recorded
        run, or importing a Health Connect export file.
      </p>
    </div>
  )
}

export function SettingsPanel() {
  return <p className="text-muted">There's nothing user-configurable in NutriPal yet.</p>
}

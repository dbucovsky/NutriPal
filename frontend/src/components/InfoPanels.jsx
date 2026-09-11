import { useEffect, useState } from 'react'
import { getAppVersion, getProfile, updateProfile } from '../api'

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
        <strong>Nutrition, Heart Rate, Sleep, Exercise, Weight, Steps</strong> — browse your logged health data. Use the
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

// Matches the seeded lut_gender rows (id, name) - hardcoded here rather
// than a lookup endpoint, same as every other LUT-backed display label in
// this app (meal names, activity types, etc.).
const GENDER_OPTIONS = [
  { id: 1, label: 'Male' },
  { id: 2, label: 'Female' },
  { id: 3, label: 'Unspecified' },
]

// Matches the seeded lut_max_hr_source rows - same hardcode-the-small-
// closed-vocabulary pattern as GENDER_OPTIONS above.
const MAX_HR_SOURCES = [
  { id: 'age', label: 'Age-based (220 − age)' },
  { id: 'observed', label: 'Observed from recent sessions' },
  { id: 'manual', label: 'Manual' },
]

export function SettingsPanel({ userId }) {
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [saving, setSaving] = useState(false)
  const [overrideInput, setOverrideInput] = useState('')

  useEffect(() => {
    let cancelled = false
    getProfile(userId)
      .then((data) => {
        if (!cancelled) setProfile(data)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [userId])

  function applyPatch(patch) {
    setSaving(true)
    setError(null)
    updateProfile(userId, patch)
      .then(setProfile)
      .catch((err) => setError(err.message))
      .finally(() => setSaving(false))
  }

  if (loading) return <p>Loading…</p>
  if (!profile) return <p className="login-error">{error}</p>

  return (
    <div className="settings-form">
      <div className="settings-field">
        <label htmlFor="settings-birth-date">Birth date</label>
        <input
          id="settings-birth-date"
          type="date"
          min="1900-01-01"
          max={new Date().toISOString().slice(0, 10)}
          value={profile.birth_date ?? ''}
          onChange={(e) => applyPatch({ birth_date: e.target.value || null })}
        />
      </div>

      <div className="settings-field">
        <label htmlFor="settings-gender">Gender</label>
        <select
          id="settings-gender"
          value={profile.gender_id ?? ''}
          onChange={(e) => applyPatch({ gender_id: e.target.value ? Number(e.target.value) : null })}
        >
          <option value="">—</option>
          {GENDER_OPTIONS.map((g) => (
            <option key={g.id} value={g.id}>
              {g.label}
            </option>
          ))}
        </select>
      </div>

      <div className="settings-max-hr">
        <strong>Max heart rate</strong>{' '}
        <span className="text-muted">
          {profile.max_heart_rate !== null
            ? `currently ${profile.max_heart_rate} bpm (${MAX_HR_SOURCES.find((s) => s.id === profile.max_heart_rate_source)?.label ?? profile.max_heart_rate_source})`
            : 'not set yet'}
        </span>

        {(() => {
          const selectedSource = profile.max_hr_source ?? 'age'
          const valueFor = {
            age: profile.max_hr_age_estimate !== null ? `${profile.max_hr_age_estimate} bpm` : 'set a birth date above',
            observed:
              profile.max_hr_observed_estimate !== null
                ? `${profile.max_hr_observed_estimate} bpm`
                : 'no qualifying running/treadmill/aerobics sessions in the last 3 weeks',
            manual: null,
          }
          return MAX_HR_SOURCES.map((source) => (
            <label key={source.id} className="settings-radio-row">
              <input
                type="radio"
                name="max-hr-source"
                checked={selectedSource === source.id}
                onChange={() => applyPatch({ max_hr_source: source.id })}
              />
              <span>{source.label}:</span>
              {source.id === 'manual' ? (
                <>
                  <input
                    type="number"
                    min="1"
                    max="250"
                    placeholder={profile.max_hr_manual_override !== null ? `${profile.max_hr_manual_override} bpm` : 'bpm'}
                    value={overrideInput}
                    onChange={(e) => setOverrideInput(e.target.value)}
                  />
                  <button
                    type="button"
                    disabled={!overrideInput || saving}
                    onClick={() => {
                      applyPatch({ max_heart_rate_override: Number(overrideInput) })
                      setOverrideInput('')
                    }}
                  >
                    Save
                  </button>
                </>
              ) : (
                <span className="text-muted">{valueFor[source.id]}</span>
              )}
            </label>
          ))
        })()}
      </div>

      {error && <p className="login-error">{error}</p>}

      <p className="text-muted">
        Max heart rate colors the heart-rate zones on the Exercise tab. All three estimates above are always kept up
        to date regardless of which one is selected, so switching is instant.
      </p>
    </div>
  )
}

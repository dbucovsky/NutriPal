// Thin wrappers around the PHP JSON API (see public/api/*.php). No
// authentication of any kind yet - login.php is a placeholder that just
// looks up a user by email, and every other endpoint trusts whatever
// user_id it's given. Real auth is future work.

export async function login(email) {
  const res = await fetch('/api/login.php', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  })
  const data = await res.json()
  if (!res.ok) {
    throw new Error(data.error || 'Login failed')
  }
  return data
}

// `view` is { type: 'day'|'week'|'month'|'year'|'custom', date, endDate }.
// endDate is only sent (and only meaningful) for view=custom.
async function getRangeJson(endpoint, userId, view, errorLabel) {
  const params = new URLSearchParams({ user_id: userId, date: view.date, view: view.type })
  if (view.type === 'custom') {
    params.set('end_date', view.endDate)
  }
  const res = await fetch(`/api/${endpoint}?${params}`)
  const data = await res.json()
  if (!res.ok) {
    throw new Error(data.error || errorLabel)
  }
  return data
}

export function getFoodLog(userId, view) {
  return getRangeJson('food-log.php', userId, view, 'Failed to load food log')
}

export function getHeartRate(userId, view) {
  return getRangeJson('heart-rate.php', userId, view, 'Failed to load heart rate')
}

export function getSleep(userId, view) {
  return getRangeJson('sleep.php', userId, view, 'Failed to load sleep')
}

export function getExercise(userId, view) {
  return getRangeJson('exercise.php', userId, view, 'Failed to load exercise')
}

export function getWeight(userId, view) {
  return getRangeJson('weight.php', userId, view, 'Failed to load weight')
}

export function getSteps(userId, view) {
  return getRangeJson('steps.php', userId, view, 'Failed to load steps')
}

// start/end are UTC "Y-m-d H:i:s" strings (e.g. an exercise session's own
// start_time/end_time), not a date/view - this is a lookup for one exact
// window, not a page-level range.
export async function getHeartRateRange(userId, start, end) {
  const params = new URLSearchParams({ user_id: userId, start, end })
  const res = await fetch(`/api/heart-rate-range.php?${params}`)
  const data = await res.json()
  if (!res.ok) {
    throw new Error(data.error || 'Failed to load heart rate')
  }
  return data
}

export async function runSync(body) {
  const res = await fetch('/api/run-sync.php', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const data = await res.json()
  if (!res.ok) {
    throw new Error(data.error || 'Sync failed')
  }
  return data
}

export async function getSyncRuns() {
  const res = await fetch('/api/sync-runs.php')
  const data = await res.json()
  if (!res.ok) {
    throw new Error(data.error || 'Failed to load sync runs')
  }
  return data.runs
}

export async function getSyncProgress(type) {
  const res = await fetch(`/api/sync-progress.php?type=${type}`)
  if (!res.ok) {
    throw new Error('Failed to load progress')
  }
  return res.json()
}

export async function getFaq() {
  const res = await fetch('/api/faq.php')
  const data = await res.json()
  if (!res.ok) {
    throw new Error(data.error || 'Failed to load FAQ')
  }
  return data
}

export async function getAppVersion() {
  const res = await fetch('/api/version.php')
  const data = await res.json()
  if (!res.ok) {
    throw new Error(data.error || 'Failed to load version')
  }
  return data.version
}

export async function getProfile(userId) {
  const res = await fetch(`/api/profile.php?user_id=${userId}`)
  const data = await res.json()
  if (!res.ok) {
    throw new Error(data.error || 'Failed to load profile')
  }
  return data
}

// `patch` may include any of birth_date, gender_id, max_heart_rate_override,
// reset_max_heart_rate - only the fields present are changed server-side.
export async function updateProfile(userId, patch) {
  const res = await fetch('/api/profile.php', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: userId, ...patch }),
  })
  const data = await res.json()
  if (!res.ok) {
    throw new Error(data.error || 'Failed to update profile')
  }
  return data
}

export async function importHealthConnect(path) {
  const res = await fetch('/api/import-hc.php', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  })
  const data = await res.json()
  if (!res.ok) {
    throw new Error(data.error || 'Import failed')
  }
  return data
}

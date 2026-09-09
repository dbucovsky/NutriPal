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

async function getJson(endpoint, userId, date, errorLabel) {
  const params = new URLSearchParams({ user_id: userId, date })
  const res = await fetch(`/api/${endpoint}?${params}`)
  const data = await res.json()
  if (!res.ok) {
    throw new Error(data.error || errorLabel)
  }
  return data
}

export function getFoodLog(userId, date) {
  return getJson('food-log.php', userId, date, 'Failed to load food log')
}

export function getHeartRate(userId, date) {
  return getJson('heart-rate.php', userId, date, 'Failed to load heart rate')
}

export function getSleep(userId, date) {
  return getJson('sleep.php', userId, date, 'Failed to load sleep')
}

export function getExercise(userId, date) {
  return getJson('exercise.php', userId, date, 'Failed to load exercise')
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

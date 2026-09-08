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

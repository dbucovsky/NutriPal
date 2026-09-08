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

export async function getFoodLog(userId, date) {
  const params = new URLSearchParams({ user_id: userId, date })
  const res = await fetch(`/api/food-log.php?${params}`)
  const data = await res.json()
  if (!res.ok) {
    throw new Error(data.error || 'Failed to load food log')
  }
  return data
}

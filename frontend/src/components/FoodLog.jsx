import { useEffect, useState } from 'react'
import { getFoodLog } from '../api'
import { todayLocal } from '../dateUtils'
import DateNav from './DateNav'

const MEAL_ORDER = ['BREAKFAST', 'LUNCH', 'DINNER', 'SNACK', 'ANYTIME']
const MEAL_LABELS = {
  BREAKFAST: 'Breakfast',
  LUNCH: 'Lunch',
  DINNER: 'Dinner',
  SNACK: 'Snack',
  ANYTIME: 'Anytime',
}

function macro(value, unit = 'g') {
  return value === null || value === undefined ? '—' : `${value}${unit}`
}

export default function FoodLog({ userId }) {
  const [date, setDate] = useState(todayLocal())
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getFoodLog(userId, date)
      .then((result) => {
        if (!cancelled) setData(result)
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
  }, [userId, date])

  return (
    <div className="food-log">
      <DateNav date={date} onChange={setDate} />

      {loading && <p>Loading…</p>}
      {error && <p className="login-error">{error}</p>}

      {data && !loading && (
        <>
          {Object.keys(data.meals).length === 0 && <p>No food logged this day.</p>}

          {MEAL_ORDER.filter((meal) => data.meals[meal]?.length).map((meal) => (
            <section key={meal} className="meal-section">
              <h3>{MEAL_LABELS[meal]}</h3>
              <ul>
                {data.meals[meal].map((entry) => (
                  <li key={entry.id} className="food-entry">
                    <div className="food-entry-name">
                      {entry.name}
                      {entry.brand_name && <span className="brand"> ({entry.brand_name})</span>}
                    </div>
                    <div className="food-entry-serving">
                      {entry.serving_amount} {entry.serving_unit_label}
                    </div>
                    <div className="food-entry-macros">
                      {macro(entry.energy_kcal, ' kcal')} · P {macro(entry.protein_g)} · C{' '}
                      {macro(entry.carb_g)} · F {macro(entry.fat_g)}
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          ))}

          <footer className="daily-totals">
            <strong>Totals:</strong> {macro(data.totals.energy_kcal, ' kcal')} · P{' '}
            {macro(data.totals.protein_g)} · C {macro(data.totals.carb_g)} · F{' '}
            {macro(data.totals.fat_g)}
          </footer>
        </>
      )}
    </div>
  )
}

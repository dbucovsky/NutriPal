import { useEffect, useState } from 'react'
import { getFoodLog } from '../api'
import MultiDay from './MultiDay'

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

function DayBody({ meals, totals }) {
  return (
    <>
      {MEAL_ORDER.filter((meal) => meals[meal]?.length).map((meal) => (
        <details key={meal} className="meal-section" open>
          <summary>{MEAL_LABELS[meal]}</summary>
          <ul>
            {meals[meal].map((entry) => (
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
        </details>
      ))}

      <footer className="daily-totals">
        <strong>Totals:</strong> {macro(totals.energy_kcal, ' kcal')} · P{' '}
        {macro(totals.protein_g)} · C {macro(totals.carb_g)} · F {macro(totals.fat_g)}
      </footer>
    </>
  )
}

export default function FoodLog({ userId, view }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getFoodLog(userId, view)
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
  }, [userId, view.type, view.date, view.endDate])

  return (
    <div className="food-log">
      {loading && <p>Loading…</p>}
      {error && <p className="login-error">{error}</p>}

      {data && !loading && (
        <>
          {data.days.length === 0 && <p>No food logged for this period.</p>}
          <MultiDay days={data.days} renderDay={(day) => <DayBody key={day.date} {...day} />} />
        </>
      )}
    </div>
  )
}

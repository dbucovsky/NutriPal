import { useEffect, useState } from 'react'
import { Chart as ChartJS, ArcElement, Tooltip as ChartTooltip, Legend } from 'chart.js'
import { Pie } from 'react-chartjs-2'
import { getFoodLog } from '../api'
import { formatDisplayDate } from '../dateUtils'
import MultiDay from './MultiDay'
import Popup from './Popup'

ChartJS.register(ArcElement, ChartTooltip, Legend)

const MEAL_ORDER = ['BREAKFAST', 'LUNCH', 'DINNER', 'SNACK', 'ANYTIME']
const MEAL_LABELS = {
  BREAKFAST: 'Breakfast',
  LUNCH: 'Lunch',
  DINNER: 'Dinner',
  SNACK: 'Snack',
  ANYTIME: 'Anytime',
}

const METRIC_LABELS = {
  energy_kcal: 'Calories',
  protein_g: 'Protein',
  carb_g: 'Carbs',
  fat_g: 'Fat',
}

const PIE_COLORS = [
  '#2f7d4f', '#d9822b', '#7fb3d5', '#8e5fb3', '#c9a227', '#b3261e',
  '#5fa5a0', '#6b6375', '#2f5f8f', '#e07a5f',
]

function macro(value, unit = 'g') {
  return value === null || value === undefined ? '—' : `${value}${unit}`
}

// Fixed-width 7-column grid (kcal-value | "P" | value | "C" | value | "F" |
// value) so digits line up regardless of label width - unlike inline text
// ("160 kcal · P 16g"), the same column template is reused everywhere a
// macro line is shown (entries, meal/day summaries, footer totals), so
// values line up both down one day and across different days.
function MacroRow({ energyKcal, proteinG, carbG, fatG, onClickMetric }) {
  function cell(value, unit, metric) {
    const content = macro(value, unit)
    if (!onClickMetric) {
      return <span className="macro-cell-value">{content}</span>
    }
    return (
      <button
        type="button"
        className="macro-cell-value macro-cell-clickable"
        onClick={(e) => {
          e.stopPropagation()
          e.preventDefault()
          onClickMetric(metric)
        }}
      >
        {content}
      </button>
    )
  }

  return (
    <span className="macro-grid">
      {cell(energyKcal, ' kcal', 'energy_kcal')}
      <span className="macro-cell-label">P</span>
      {cell(proteinG, 'g', 'protein_g')}
      <span className="macro-cell-label">C</span>
      {cell(carbG, 'g', 'carb_g')}
      <span className="macro-cell-label">F</span>
      {cell(fatG, 'g', 'fat_g')}
    </span>
  )
}

function macroRowFromTotals(totals, onClickMetric) {
  return (
    <MacroRow
      energyKcal={totals.energy_kcal}
      proteinG={totals.protein_g}
      carbG={totals.carb_g}
      fatG={totals.fat_g}
      onClickMetric={onClickMetric}
    />
  )
}

function mealTotals(entries) {
  const totals = { energy_kcal: 0, protein_g: 0, carb_g: 0, fat_g: 0 }
  let any = false
  for (const key of Object.keys(totals)) {
    for (const entry of entries) {
      if (entry[key] !== null && entry[key] !== undefined) {
        totals[key] += entry[key]
        any = true
      }
    }
    totals[key] = any ? Math.round(totals[key] * 100) / 100 : null
    any = false
  }
  return totals
}

// Per-food contribution to one macro across every meal that day - grouped
// by (name, brand) so a food logged twice in one day is one slice, not two.
function pieDataForDay(day, metric) {
  const byFood = new Map()
  for (const entries of Object.values(day.meals)) {
    for (const entry of entries) {
      const value = entry[metric]
      if (!value) continue
      const key = entry.brand_name ? `${entry.name} (${entry.brand_name})` : entry.name
      byFood.set(key, (byFood.get(key) || 0) + value)
    }
  }
  return [...byFood.entries()]
    .map(([label, value]) => ({ label, value: Math.round(value * 100) / 100 }))
    .sort((a, b) => b.value - a.value)
}

function MacroPiePopup({ day, metric, onClose }) {
  const items = pieDataForDay(day, metric)
  const chartData = {
    labels: items.map((i) => i.label),
    datasets: [
      {
        data: items.map((i) => i.value),
        backgroundColor: items.map((_, i) => PIE_COLORS[i % PIE_COLORS.length]),
      },
    ],
  }

  return (
    <Popup title={`${METRIC_LABELS[metric]} — ${formatDisplayDate(day.date)}`} onClose={onClose}>
      {items.length > 0 ? (
        <div className="chart-wrap">
          <Pie data={chartData} options={{ plugins: { legend: { position: 'right' } } }} />
        </div>
      ) : (
        <p>No data for this day.</p>
      )}
    </Popup>
  )
}

function DayBody({ meals, totals, onClickMetric }) {
  return (
    <>
      {MEAL_ORDER.filter((meal) => meals[meal]?.length).map((meal) => (
        <details key={meal} className="meal-section" open>
          <summary>
            <span className="meal-section-title">{MEAL_LABELS[meal]}</span>
            <span className="meal-section-summary">{macroRowFromTotals(mealTotals(meals[meal]))}</span>
          </summary>
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
                  <MacroRow
                    energyKcal={entry.energy_kcal}
                    proteinG={entry.protein_g}
                    carbG={entry.carb_g}
                    fatG={entry.fat_g}
                  />
                </div>
              </li>
            ))}
          </ul>
        </details>
      ))}

      <footer className="daily-totals">
        <strong>Totals:</strong> {macroRowFromTotals(totals, onClickMetric)}
      </footer>
    </>
  )
}

export default function FoodLog({ userId, view }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [pieRequest, setPieRequest] = useState(null)

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
          <MultiDay
            days={data.days}
            renderDay={(day) => (
              <DayBody key={day.date} {...day} onClickMetric={(metric) => setPieRequest({ day, metric })} />
            )}
            renderSummary={(day) => macroRowFromTotals(day.totals, (metric) => setPieRequest({ day, metric }))}
          />
        </>
      )}

      {pieRequest && (
        <MacroPiePopup day={pieRequest.day} metric={pieRequest.metric} onClose={() => setPieRequest(null)} />
      )}
    </div>
  )
}

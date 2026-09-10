import { useRef } from 'react'
import {
  formatDisplayDate,
  formatWeekLabel,
  formatMonthLabel,
  formatYearLabel,
  formatRangeLabel,
  stepDateByView,
} from '../dateUtils'

const VIEW_MODES = [
  { type: 'day', label: 'Day' },
  { type: 'week', label: 'Week' },
  { type: 'month', label: 'Month' },
  { type: 'year', label: 'Year' },
  { type: 'custom', label: 'Custom' },
]

function labelFor(view) {
  switch (view.type) {
    case 'week':
      return formatWeekLabel(view.date)
    case 'month':
      return formatMonthLabel(view.date)
    case 'year':
      return formatYearLabel(view.date)
    case 'custom':
      return formatRangeLabel(view.date, view.endDate)
    default:
      return formatDisplayDate(view.date)
  }
}

export default function DateNav({ view, onChange, showViewModes }) {
  const inputRef = useRef(null)

  function openPicker() {
    if (inputRef.current?.showPicker) {
      inputRef.current.showPicker()
    } else {
      inputRef.current?.focus()
    }
  }

  function step(direction) {
    onChange({ ...view, date: stepDateByView(view.date, view.type, direction) })
  }

  function selectViewType(type) {
    if (type === view.type) return
    if (type === 'custom') {
      onChange({ ...view, type, endDate: view.endDate || view.date })
    } else {
      onChange({ ...view, type })
    }
  }

  return (
    <div className="date-nav">
      {view.type === 'custom' ? (
        <div className="date-nav-custom">
          <input
            type="date"
            value={view.date}
            onChange={(e) => e.target.value && onChange({ ...view, date: e.target.value })}
            aria-label="Custom range start"
          />
          <span className="text-muted">to</span>
          <input
            type="date"
            value={view.endDate}
            min={view.date}
            onChange={(e) => e.target.value && onChange({ ...view, endDate: e.target.value })}
            aria-label="Custom range end"
          />
        </div>
      ) : (
        <div className="date-nav-arrows">
          <button type="button" className="date-arrow" aria-label="Previous" onClick={() => step(-1)}>
            ‹
          </button>
          <button type="button" className="date-display" onClick={openPicker}>
            {labelFor(view)}
          </button>
          <button type="button" className="date-arrow" aria-label="Next" onClick={() => step(1)}>
            ›
          </button>
          <input
            ref={inputRef}
            type="date"
            value={view.date}
            onChange={(e) => e.target.value && onChange({ ...view, date: e.target.value })}
            className="date-input-hidden"
            aria-label="Select date"
          />
        </div>
      )}

      {showViewModes && (
        <div className="view-mode-nav">
          {VIEW_MODES.map((mode) => (
            <button
              key={mode.type}
              type="button"
              className={mode.type === view.type ? 'view-mode active' : 'view-mode'}
              onClick={() => selectViewType(mode.type)}
            >
              {mode.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

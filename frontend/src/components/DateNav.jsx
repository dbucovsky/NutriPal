import { useRef } from 'react'
import { formatDisplayDate } from '../dateUtils'

export default function DateNav({ date, onChange }) {
  const inputRef = useRef(null)

  function openPicker() {
    if (inputRef.current?.showPicker) {
      inputRef.current.showPicker()
    } else {
      inputRef.current?.focus()
    }
  }

  return (
    <div className="date-nav">
      <button type="button" className="date-display" onClick={openPicker}>
        {formatDisplayDate(date)}
      </button>
      <input
        ref={inputRef}
        type="date"
        value={date}
        onChange={(e) => e.target.value && onChange(e.target.value)}
        className="date-input-hidden"
        aria-label="Select date"
      />
    </div>
  )
}

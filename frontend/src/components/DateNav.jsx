import { shiftDate } from '../dateUtils'

export default function DateNav({ date, onChange }) {
  return (
    <div className="date-nav">
      <button onClick={() => onChange(shiftDate(date, -1))}>&larr;</button>
      <h2>{date}</h2>
      <button onClick={() => onChange(shiftDate(date, 1))}>&rarr;</button>
    </div>
  )
}

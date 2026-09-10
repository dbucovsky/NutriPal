// Minimal shared modal - backdrop click or the close button both close it.
export default function Popup({ title, onClose, children }) {
  return (
    <div className="popup-overlay" onClick={onClose}>
      <div className="popup-content" onClick={(e) => e.stopPropagation()}>
        <div className="popup-header">
          <span>{title}</span>
          <button type="button" className="popup-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}

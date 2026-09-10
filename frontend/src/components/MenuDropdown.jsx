import { useEffect, useRef, useState } from 'react'

const ITEMS = [
  { key: 'logout', label: 'Log out' },
  { key: 'settings', label: 'Settings' },
  { key: 'help', label: 'Help' },
  { key: 'sync', label: 'Sync' },
  { key: 'about', label: 'About' },
]

// The app full-screens <Login> whenever there's no current user (see
// App.jsx), so this menu is only ever reachable while logged in - "Log
// out" is the only reachable state, same as today; no "Log in" branch to
// wire up here.
export default function MenuDropdown({ onSelect, onLogout }) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef(null)

  useEffect(() => {
    if (!open) return
    function handleClickOutside(e) {
      if (rootRef.current && !rootRef.current.contains(e.target)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [open])

  function handleItemClick(key) {
    setOpen(false)
    if (key === 'logout') {
      onLogout()
    } else {
      onSelect(key)
    }
  }

  return (
    <div className="menu-dropdown-root" ref={rootRef}>
      <button
        type="button"
        className="menu-button"
        onClick={() => setOpen((o) => !o)}
        aria-label="Menu"
        aria-expanded={open}
      >
        <svg viewBox="0 0 16 16" width="18" height="18" aria-hidden="true">
          <rect x="1" y="3" width="14" height="2" fill="currentColor" />
          <rect x="1" y="7" width="14" height="2" fill="currentColor" />
          <rect x="1" y="11" width="14" height="2" fill="currentColor" />
        </svg>
      </button>

      {open && (
        <ul className="menu-dropdown">
          {ITEMS.map((item) => (
            <li key={item.key}>
              <button type="button" className="menu-dropdown-item" onClick={() => handleItemClick(item.key)}>
                {item.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

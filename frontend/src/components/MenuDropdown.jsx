import { useEffect, useRef, useState } from 'react'

// The 'help' item has a submenu (Help popup + FAQ, opened as its own page in
// a new tab rather than a popup, since FAQ content is meant to be its own
// bookmarkable page) - `external` items open via window.open instead of
// calling onSelect.
const ITEMS = [
  { key: 'sync', label: 'Sync' },
  { key: 'settings', label: 'Settings' },
  { key: 'logout', label: 'Log out' },
  {
    key: 'help',
    label: 'Help',
    children: [
      { key: 'help', label: 'Help' },
      { key: 'faq', label: 'FAQ', external: '/faq.html' },
    ],
  },
  { key: 'about', label: 'About' },
]

// The app full-screens <Login> whenever there's no current user (see
// App.jsx), so this menu is only ever reachable while logged in - "Log
// out" is the only reachable state, same as today; no "Log in" branch to
// wire up here.
export default function MenuDropdown({ onSelect, onLogout }) {
  const [open, setOpen] = useState(false)
  const [submenuKey, setSubmenuKey] = useState(null)
  const rootRef = useRef(null)

  useEffect(() => {
    if (!open) return
    function handleClickOutside(e) {
      if (rootRef.current && !rootRef.current.contains(e.target)) {
        setOpen(false)
        setSubmenuKey(null)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [open])

  function closeAll() {
    setOpen(false)
    setSubmenuKey(null)
  }

  function handleItemClick(item) {
    if (item.external) {
      window.open(item.external, '_blank', 'noopener')
      closeAll()
      return
    }
    closeAll()
    if (item.key === 'logout') {
      onLogout()
    } else {
      onSelect(item.key)
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
          {ITEMS.map((item) =>
            item.children ? (
              <li key={item.key} className="menu-dropdown-submenu">
                <button
                  type="button"
                  className="menu-dropdown-item menu-dropdown-item-parent"
                  onClick={() => setSubmenuKey((k) => (k === item.key ? null : item.key))}
                  aria-expanded={submenuKey === item.key}
                >
                  {item.label} <span aria-hidden="true">{submenuKey === item.key ? '▾' : '▸'}</span>
                </button>
                {submenuKey === item.key && (
                  <ul className="menu-dropdown-submenu-list">
                    {item.children.map((child) => (
                      <li key={child.key}>
                        <button type="button" className="menu-dropdown-item" onClick={() => handleItemClick(child)}>
                          {child.label}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            ) : (
              <li key={item.key}>
                <button type="button" className="menu-dropdown-item" onClick={() => handleItemClick(item)}>
                  {item.label}
                </button>
              </li>
            )
          )}
        </ul>
      )}
    </div>
  )
}

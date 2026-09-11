import { useState } from 'react'
import Login from './components/Login'
import FoodLog from './components/FoodLog'
import HeartRate from './components/HeartRate'
import Sleep from './components/Sleep'
import Exercise from './components/Exercise'
import Weight from './components/Weight'
import Steps from './components/Steps'
import Sync from './components/Sync'
import DateNav from './components/DateNav'
import MenuDropdown from './components/MenuDropdown'
import QuickSyncButton from './components/QuickSyncButton'
import Popup from './components/Popup'
import { AboutPanel, HelpPanel, SettingsPanel } from './components/InfoPanels'
import { todayLocal } from './dateUtils'
import './App.css'

const STORAGE_KEY = 'nutripal.currentUser'

const TABS = [
  { key: 'food', label: 'Nutrition', Component: FoodLog },
  { key: 'heart-rate', label: 'Heart Rate', Component: HeartRate },
  { key: 'sleep', label: 'Sleep', Component: Sleep },
  { key: 'exercise', label: 'Exercise', Component: Exercise },
  { key: 'weight', label: 'Weight', Component: Weight },
  { key: 'steps', label: 'Steps', Component: Steps },
]

// Sync/Settings/Help/About all open as a popup from the menu now, not a tab.
const PANEL_TITLES = {
  sync: 'Sync',
  settings: 'Settings',
  help: 'Help',
  about: 'About',
}

function renderPanel(panel, userId) {
  switch (panel) {
    case 'sync':
      return <Sync />
    case 'settings':
      return <SettingsPanel userId={userId} />
    case 'help':
      return <HelpPanel />
    case 'about':
      return <AboutPanel />
    default:
      return null
  }
}

function loadStoredUser() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

function App() {
  const [currentUser, setCurrentUser] = useState(loadStoredUser)
  const [activeTab, setActiveTab] = useState(TABS[0].key)
  const [openPanel, setOpenPanel] = useState(null) // 'sync' | 'settings' | 'help' | 'about' | null
  // Shared across every tab, so switching tabs keeps the same day/range
  // selected rather than each page defaulting back to today independently.
  const [view, setView] = useState(() => ({ type: 'day', date: todayLocal(), endDate: todayLocal() }))

  function handleLogin(user) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(user))
    setCurrentUser(user)
  }

  function handleLogout() {
    localStorage.removeItem(STORAGE_KEY)
    setCurrentUser(null)
  }

  if (!currentUser) {
    return <Login onLogin={handleLogin} />
  }

  const Active = TABS.find((t) => t.key === activeTab).Component

  return (
    <div className="app">
      <header className="app-header">
        <div className="header-left">
          <MenuDropdown onSelect={setOpenPanel} onLogout={handleLogout} />
          <QuickSyncButton />
        </div>
        <span>Logged in as {currentUser.name}</span>
      </header>

      <DateNav view={view} onChange={setView} showViewModes />

      <nav className="tab-nav">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            className={tab.key === activeTab ? 'tab active' : 'tab'}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      <Active userId={currentUser.id} date={view.date} view={view} />

      {openPanel && (
        <Popup title={PANEL_TITLES[openPanel]} onClose={() => setOpenPanel(null)}>
          {renderPanel(openPanel, currentUser.id)}
        </Popup>
      )}
    </div>
  )
}

export default App

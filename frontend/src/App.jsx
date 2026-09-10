import { useState } from 'react'
import Login from './components/Login'
import FoodLog from './components/FoodLog'
import HeartRate from './components/HeartRate'
import Sleep from './components/Sleep'
import Exercise from './components/Exercise'
import Weight from './components/Weight'
import Sync from './components/Sync'
import DateNav from './components/DateNav'
import { todayLocal } from './dateUtils'
import './App.css'

const STORAGE_KEY = 'nutripal.currentUser'

const TABS = [
  { key: 'food', label: 'Food', Component: FoodLog },
  { key: 'heart-rate', label: 'Heart Rate', Component: HeartRate },
  { key: 'sleep', label: 'Sleep', Component: Sleep },
  { key: 'exercise', label: 'Exercise', Component: Exercise },
  { key: 'weight', label: 'Weight', Component: Weight },
  { key: 'sync', label: 'Sync', Component: Sync },
]

// Only these tabs understand a multi-day view; Heart Rate/Sync stay day-only.
const MULTI_DAY_TABS = new Set(['food', 'sleep', 'exercise', 'weight'])

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
  // Shared across every tab, so switching tabs keeps the same day/range
  // selected rather than each page defaulting back to today independently.
  // `type` defaults to 'day' so nothing changes for tabs that never touch
  // view modes (Heart Rate, Sync just read `view.date`).
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
  const showViewModes = MULTI_DAY_TABS.has(activeTab)

  // Tabs without multi-day support (Heart Rate, Sync) only ever read
  // `view.date` and never touch `view.type` - so they're shown a
  // forced-'day' nav (no leftover week/month/year arrow-stepping) without
  // that override ever overwriting the real shared view mode, which the
  // user expects to still be there when they switch back to e.g. Food.
  const displayedView = showViewModes ? view : { ...view, type: 'day' }

  function handleViewChange(next) {
    setView(showViewModes ? next : { ...view, date: next.date })
  }

  return (
    <div className="app">
      <header className="app-header">
        <span>Logged in as {currentUser.name}</span>
        <button onClick={handleLogout}>Log out</button>
      </header>

      <DateNav view={displayedView} onChange={handleViewChange} showViewModes={showViewModes} />

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
    </div>
  )
}

export default App

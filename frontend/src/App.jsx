import { useState } from 'react'
import Login from './components/Login'
import FoodLog from './components/FoodLog'
import HeartRate from './components/HeartRate'
import Sleep from './components/Sleep'
import Exercise from './components/Exercise'
import DateNav from './components/DateNav'
import { todayLocal } from './dateUtils'
import './App.css'

const STORAGE_KEY = 'nutripal.currentUser'

const TABS = [
  { key: 'food', label: 'Food', Component: FoodLog },
  { key: 'heart-rate', label: 'Heart Rate', Component: HeartRate },
  { key: 'sleep', label: 'Sleep', Component: Sleep },
  { key: 'exercise', label: 'Exercise', Component: Exercise },
]

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
  // Shared across every tab, so switching tabs keeps the same day selected
  // rather than each page defaulting back to today independently.
  const [date, setDate] = useState(todayLocal())

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
        <span>Logged in as {currentUser.name}</span>
        <button onClick={handleLogout}>Log out</button>
      </header>

      <DateNav date={date} onChange={setDate} />

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

      <Active userId={currentUser.id} date={date} />
    </div>
  )
}

export default App

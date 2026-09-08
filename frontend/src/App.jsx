import { useState } from 'react'
import Login from './components/Login'
import FoodLog from './components/FoodLog'
import './App.css'

const STORAGE_KEY = 'nutripal.currentUser'

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

  return (
    <div className="app">
      <header className="app-header">
        <span>Logged in as {currentUser.name}</span>
        <button onClick={handleLogout}>Log out</button>
      </header>
      <FoodLog userId={currentUser.id} />
    </div>
  )
}

export default App

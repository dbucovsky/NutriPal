import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import './App.css'
import FaqPage from './components/FaqPage.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <FaqPage />
  </StrictMode>,
)

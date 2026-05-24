import { useState, useEffect } from 'react'
import './App.css'

function App() {
  const [isBackendOnline, setIsBackendOnline] = useState(false)
  const [checking, setChecking] = useState(true)

  useEffect(() => {
    let active = true

    const checkBackend = async () => {
      try {
        const response = await fetch('http://localhost:8000/')
        if (response.ok) {
          const data = await response.json()
          if (active && data.status === 'running') {
            setIsBackendOnline(true)
            setChecking(false)
            return
          }
        }
        throw new Error('Invalid response')
      } catch (err) {
        if (active) {
          setIsBackendOnline(false)
          setChecking(false)
        }
      }
    }

    // Initial check
    checkBackend()

    // Poll every 3 seconds
    const interval = setInterval(checkBackend, 3000)

    return () => {
      active = false
      clearInterval(interval)
    }
  }, [])

  return (
    <div className="app-container">
      <div className="glow-orb"></div>
      
      <div className="brand-card">
        <div className="brand-badge">React + Vite + FastAPI</div>
        <h1 className="brand-title">Ai Funda</h1>
        <p className="brand-subtitle">Intelligent AI Playground</p>
        
        <div className="pulse-indicator">
          <span className={`pulse-dot ${isBackendOnline ? 'online' : checking ? 'checking' : 'offline'}`}></span>
          <span className="pulse-text">
            {isBackendOnline 
              ? 'Backend Online' 
              : checking 
                ? 'Checking Server...' 
                : 'Backend Offline'
            }
          </span>
        </div>
      </div>
    </div>
  )
}

export default App

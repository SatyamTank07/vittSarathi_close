import './App.css'

function App() {
  return (
    <div className="app-container">
      <div className="glow-orb"></div>
      <div className="brand-card">
        <div className="brand-badge">React + Vite</div>
        <h1 className="brand-title">Ai Funda</h1>
        <p className="brand-subtitle">Intelligent AI Playground</p>
        <div className="pulse-indicator">
          <span className="pulse-dot"></span>
          <span className="pulse-text">System Active</span>
        </div>
      </div>
    </div>
  )
}

export default App

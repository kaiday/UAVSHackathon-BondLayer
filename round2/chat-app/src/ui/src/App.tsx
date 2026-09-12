import { useEffect, useState } from 'react'
import './App.css'

function App() {
  const [merchantHealth, setMerchantHealth] = useState<boolean | null>(null)
  const [agentHealth, setAgentHealth] = useState<boolean | null>(null)

  useEffect(() => {
    // Check merchant service health
    fetch('/merchant-api/health')
      .then(() => setMerchantHealth(true))
      .catch(() => setMerchantHealth(false))

    // Check agent service health
    fetch('/agent-api/health')
      .then(() => setAgentHealth(true))
      .catch(() => setAgentHealth(false))
  }, [])

  return (
    <div className="app">
      <header className="header">
        <h1>BondLayer Demo</h1>
        <p className="subtitle">UCP Integration & Loyalty Layer Proof</p>
      </header>

      <main className="main">
        <section className="status-section">
          <h2>Service Status</h2>
          <div className="status-grid">
            <div className={`status-card ${merchantHealth === true ? 'healthy' : merchantHealth === false ? 'error' : 'loading'}`}>
              <div className="status-indicator"></div>
              <h3>Merchant Service</h3>
              <p className="port">:8000</p>
              <p className="status-text">
                {merchantHealth === null && 'Checking...'}
                {merchantHealth === true && '✓ Running'}
                {merchantHealth === false && '✗ Not responding'}
              </p>
            </div>

            <div className={`status-card ${agentHealth === true ? 'healthy' : agentHealth === false ? 'error' : 'loading'}`}>
              <div className="status-indicator"></div>
              <h3>Agent Service</h3>
              <p className="port">:8001</p>
              <p className="status-text">
                {agentHealth === null && 'Checking...'}
                {agentHealth === true && '✓ Running'}
                {agentHealth === false && '✗ Not responding'}
              </p>
            </div>
          </div>
        </section>

        <section className="info-section">
          <h2>Phase 0 - Scaffolding</h2>
          <p>Core services and UI shell ready. Awaiting implementation of:</p>
          <ul>
            <li>UCP integration routes</li>
            <li>Mock shopping agent</li>
            <li>Chat interface</li>
            <li>Loyalty layer</li>
            <li>Record signing & verification</li>
          </ul>
        </section>
      </main>

      <footer className="footer">
        <p>BondLayer © 2026 Hackathon</p>
      </footer>
    </div>
  )
}

export default App

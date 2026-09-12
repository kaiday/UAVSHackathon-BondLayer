import { useEffect, useState } from 'react'
import './App.css'

interface RankedResult {
  rank: number
  merchant: string
  product_id: string
  product_name: string
  price: number
  description: string
  reasoning: string
}

interface AgentResponse {
  user_query: string
  parsed_intent: string
  results: RankedResult[]
  final_recommendation: string
  bondlayer_enabled: boolean
  ucp_header: string | null
}

function App() {
  const [merchantHealth, setMerchantHealth] = useState<boolean | null>(null)
  const [agentHealth, setAgentHealth] = useState<boolean | null>(null)
  const [query, setQuery] = useState('')
  const [bondlayerEnabled, setBondlayerEnabled] = useState(true)
  const [loading, setLoading] = useState(false)
  const [response, setResponse] = useState<AgentResponse | null>(null)
  const [error, setError] = useState('')

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

  const handleQuery = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!query.trim()) return

    setLoading(true)
    setError('')
    setResponse(null)

    try {
      const res = await fetch('/agent-api/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: query,
          bondlayer_enabled: bondlayerEnabled,
        }),
      })

      if (!res.ok) throw new Error('Query failed')
      const data = await res.json()
      setResponse(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error')
    } finally {
      setLoading(false)
    }
  }

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

        {agentHealth && merchantHealth && (
          <section className="query-section">
            <h2>Shopping Agent - Issue #15</h2>

            <div className="control-group">
              <label className="switch-label">
                <input
                  type="checkbox"
                  checked={bondlayerEnabled}
                  onChange={(e) => setBondlayerEnabled(e.target.checked)}
                  disabled={loading}
                />
                <span className={bondlayerEnabled ? 'enabled' : 'disabled'}>
                  {bondlayerEnabled ? '✓ BondLayer Enabled' : '✗ BondLayer Disabled'}
                </span>
              </label>
              {response && (
                <div className="ucp-header">
                  UCP Header: <code>{response.ucp_header || 'none'}</code>
                </div>
              )}
            </div>

            <form onSubmit={handleQuery} className="query-form">
              <div className="input-group">
                <input
                  type="text"
                  placeholder="What are you looking for? (e.g., 'USB-C charger under $30')"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  disabled={loading}
                  className="query-input"
                />
                <button
                  type="submit"
                  disabled={loading || !query.trim()}
                  className="submit-btn"
                >
                  {loading ? 'Searching...' : 'Search'}
                </button>
              </div>
            </form>

            {error && <div className="error-message">{error}</div>}

            {response && (
              <div className="response-section">
                <div className="query-info">
                  <p><strong>Your Query:</strong> {response.user_query}</p>
                  <p><strong>Parsed Intent:</strong> {response.parsed_intent}</p>
                  <p><strong>BondLayer:</strong> {response.bondlayer_enabled ? 'ON (negotiation includes org.bondlayer.benefit_value)' : 'OFF (extension pruned)'}</p>
                </div>

                <div className="recommendation">
                  <h3>Recommendation</h3>
                  <p>{response.final_recommendation}</p>
                </div>

                {response.results.length > 0 && (
                  <div className="results">
                    <h3>Ranked Results</h3>
                    <div className="results-list">
                      {response.results.map((result, idx) => (
                        <div key={idx} className="result-item">
                          <div className="rank-badge">#{result.rank}</div>
                          <div className="result-content">
                            <h4>{result.product_name}</h4>
                            <p className="merchant">{result.merchant}</p>
                            <p className="price">${result.price}</p>
                            <p className="description">{result.description}</p>
                            <p className="reasoning"><em>"{result.reasoning}"</em></p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </section>
        )}

        {(!agentHealth || !merchantHealth) && (
          <section className="info-section">
            <h2>⚠️ Services Not Ready</h2>
            <p>Start the services to test Issue #15:</p>
            <pre className="code-block">
{`# Terminal 1: Merchant Service
cd round2/chat-app
pip install -r requirements.txt
python -m src.merchant.main

# Terminal 2: Agent Service (requires ANTHROPIC_API_KEY)
export ANTHROPIC_API_KEY=sk-...
python -m src.agent.main

# Terminal 3: UI
cd src/ui
npm install
npm run dev`}
            </pre>
          </section>
        )}
      </main>

      <footer className="footer">
        <p>BondLayer © 2026 Hackathon | Issue #15: Agent Pipeline</p>
      </footer>
    </div>
  )
}

export default App

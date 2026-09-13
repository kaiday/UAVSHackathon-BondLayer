import { useEffect, useState } from 'react'
import './App.css'
import ChatPane from './components/ChatPane'
import ResultsView from './components/ResultsView'
import EvidenceTimeline from './components/EvidenceTimeline'
import TranscriptPanel from './components/TranscriptPanel'
import UCPLog from './components/UCPLog'
import type { AgentResponse, MerchantExchange } from './types'

function App() {
  const [merchantHealth, setMerchantHealth] = useState<boolean | null>(null)
  const [agentHealth, setAgentHealth] = useState<boolean | null>(null)
  const [query, setQuery] = useState('')
  const [bondlayerEnabled, setBondlayerEnabled] = useState(true)
  const [currentResponse, setCurrentResponse] = useState<AgentResponse | null>(null)
  const [pinnedResponse, setPinnedResponse] = useState<AgentResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [showTranscript, setShowTranscript] = useState(false)
  const [displayingPinned, setDisplayingPinned] = useState(false)

  useEffect(() => {
    fetch('/merchant-api/health')
      .then((r) => setMerchantHealth(r.ok))
      .catch(() => setMerchantHealth(false))

    fetch('/agent-api/health')
      .then((r) => setAgentHealth(r.ok))
      .catch(() => setAgentHealth(false))
  }, [])

  const handleQuery = async (userQuery: string) => {
    setQuery(userQuery)
    setLoading(true)
    try {
      const response = await fetch('/agent-api/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: userQuery, bondlayer_enabled: bondlayerEnabled })
      })
      const data = await response.json()
      setCurrentResponse(data)
      setDisplayingPinned(false)
    } catch (error) {
      console.error('Error querying agent:', error)
    } finally {
      setLoading(false)
    }
  }

  const handlePinComparison = () => {
    setPinnedResponse(currentResponse)
  }

  const handleToggleBondLayer = (enabled: boolean) => {
    setBondlayerEnabled(enabled)
    if (query) {
      handleQuery(query)
    }
  }

  const toggleComparison = () => {
    if (pinnedResponse && currentResponse) {
      setDisplayingPinned(!displayingPinned)
    }
  }

  const displayResponse = displayingPinned ? pinnedResponse : currentResponse

  return (
    <div className="app">
      <header className="header">
        <h1>🔗 BondLayer Demo</h1>
        <p className="subtitle">A neutral shopping agent, over real UCP</p>
      </header>

      <main className="main-content">
        <div className="layout">
          {/* Left: Chat Pane */}
          <div className="left-panel">
            <ChatPane
              onQuery={handleQuery}
              loading={loading}
              bondlayerEnabled={bondlayerEnabled}
              onToggleBondLayer={handleToggleBondLayer}
            />

            {/* Status Section */}
            <section className="status-section">
              <h3>Service Status</h3>
              <div className="status-mini">
                <span className={`status-dot ${merchantHealth === true ? 'healthy' : 'error'}`}></span>
                <span>Merchant: {merchantHealth === true ? '✓' : '✗'}</span>
              </div>
              <div className="status-mini">
                <span className={`status-dot ${agentHealth === true ? 'healthy' : 'error'}`}></span>
                <span>Agent: {agentHealth === true ? '✓' : '✗'}</span>
              </div>
            </section>
          </div>

          {/* Right: Results and Evidence */}
          <div className="right-panel">
            {currentResponse && (
              <>
                {/* Comparison Control */}
                {pinnedResponse && currentResponse && (
                  <div className="comparison-control">
                    <button
                      className={`comparison-btn ${displayingPinned ? 'active' : ''}`}
                      onClick={toggleComparison}
                    >
                      {displayingPinned ? '📌 Pinned Run' : '⚡ Current Run'}
                    </button>
                    <div className="status-indicator">
                      {displayingPinned && <span className="badge">Pinned (BondLayer: {pinnedResponse.bondlayer_enabled ? 'ON' : 'OFF'})</span>}
                      {!displayingPinned && <span className="badge">Current (BondLayer: {currentResponse.bondlayer_enabled ? 'ON' : 'OFF'})</span>}
                    </div>
                  </div>
                )}

                {/* Results */}
                <ResultsView response={displayResponse!} />

                {/* Pin Button */}
                {!pinnedResponse && (
                  <button className="pin-btn" onClick={handlePinComparison}>
                    📌 Pin This Run for Comparison
                  </button>
                )}

                {/* Evidence Timeline */}
                <EvidenceTimeline response={displayResponse!} />

                {/* UCP Negotiation Log */}
                <UCPLog
                  header={displayResponse!.ucp_agent_header}
                  bondlayerEnabled={displayResponse!.bondlayer_enabled}
                  exchanges={
                    (displayResponse!.evidence_log.find((s) => s.step === 'fan_out')
                      ?.exchanges ?? []) as MerchantExchange[]
                  }
                />

                {/* Transcript Toggle */}
                <div className="transcript-section">
                  <button
                    className="transcript-toggle"
                    onClick={() => setShowTranscript(!showTranscript)}
                  >
                    {showTranscript ? '▼' : '▶'} Model Transcript
                  </button>
                  {showTranscript && <TranscriptPanel transcript={displayResponse!.transcript} />}
                </div>
              </>
            )}

            {loading && (
              <div className="loading">
                <div className="spinner"></div>
                <p>Processing your query...</p>
              </div>
            )}

            {!currentResponse && !loading && (
              <div className="empty-state">
                <p>📝 Enter a shopping query to begin</p>
              </div>
            )}
          </div>
        </div>
      </main>

      <footer className="footer">
        <p>BondLayer 2026 Hackathon - the switch is one token in one UCP-Agent header</p>
      </footer>
    </div>
  )
}

export default App

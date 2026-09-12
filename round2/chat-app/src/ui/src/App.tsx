import { useEffect, useState } from 'react'
import './App.css'
import ChatPane from './components/ChatPane'
import ResultsView from './components/ResultsView'
import EvidenceTimeline from './components/EvidenceTimeline'
import TranscriptPanel from './components/TranscriptPanel'
import UCPLog from './components/UCPLog'

interface EvidenceRecord {
  id: string
  type: string
  description: string
  value: number | null
  source: string
  signed: boolean
  verified: boolean
}

interface RankedResult {
  rank: number
  merchant: string
  product_id: string
  product_name: string
  price: number
  description: string
  reasoning: string
  evidence_records: EvidenceRecord[]
}

interface UCPLogEntry {
  step: string
  detail: string
  [key: string]: string | string[] | number | undefined
}

interface AgentResponse {
  user_query: string
  parsed_intent: string
  results: RankedResult[]
  final_recommendation: string
  bondlayer_enabled: boolean
  transcript: Record<string, string>
  ucp_header: string | null
  ucp_negotiation_log?: UCPLogEntry[]
  records_state_log?: Array<{
    record_id: string
    status: string
    value: number
    credited: number
    verified: boolean
    reason?: string
  }>
}

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
      .then(() => setMerchantHealth(true))
      .catch(() => setMerchantHealth(false))

    fetch('/agent-api/health')
      .then(() => setAgentHealth(true))
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
        <p className="subtitle">Shopping Agent + Loyalty Layer Integration</p>
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
                {displayResponse!.ucp_negotiation_log && displayResponse!.ucp_negotiation_log.length > 0 && (
                  <UCPLog
                    log={displayResponse!.ucp_negotiation_log}
                    bondlayerEnabled={displayResponse!.bondlayer_enabled}
                  />
                )}

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
        <p>BondLayer © 2026 Hackathon — P5 React UI: Chat Pane, Comparison Switch, Evidence Timeline</p>
      </footer>
    </div>
  )
}

export default App

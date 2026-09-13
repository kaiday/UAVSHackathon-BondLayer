import { useState } from 'react'

interface ChatPaneProps {
  onQuery: (query: string) => void
  loading: boolean
  bondlayerEnabled: boolean
  onToggleBondLayer: (enabled: boolean) => void
}

export default function ChatPane({
  onQuery,
  loading,
  bondlayerEnabled,
  onToggleBondLayer
}: ChatPaneProps) {
  const [input, setInput] = useState('')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (input.trim()) {
      onQuery(input)
      setInput('')
    }
  }

  const handleQuickQuery = (query: string) => {
    onQuery(query)
  }

  return (
    <div className="chat-pane">
      <div className="bondlayer-toggle">
        <label>
          <input
            type="checkbox"
            checked={bondlayerEnabled}
            onChange={(e) => onToggleBondLayer(e.target.checked)}
            disabled={loading}
          />
          <span>BondLayer {bondlayerEnabled ? '✓ ON' : '✗ OFF'}</span>
        </label>
        <p className="toggle-hint">
          {bondlayerEnabled
            ? 'Loyalty benefits enabled'
            : 'No benefits (baseline)'}
        </p>
      </div>

      <form onSubmit={handleSubmit} className="chat-form">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="What product are you looking for? (e.g., 'USB-C charger fast charging')"
          disabled={loading}
          rows={3}
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="submit-btn"
        >
          {loading ? '⏳ Processing...' : '🔍 Search'}
        </button>
      </form>

      <div className="quick-queries">
        <p className="quick-label">Quick queries:</p>
        <div className="quick-buttons">
          <button
            onClick={() => handleQuickQuery('USB-C charger')}
            disabled={loading}
            className="quick-btn"
          >
            USB-C charger
          </button>
          <button
            onClick={() => handleQuickQuery('laptop stand')}
            disabled={loading}
            className="quick-btn"
          >
            Laptop stand
          </button>
          <button
            onClick={() => handleQuickQuery('wireless accessories')}
            disabled={loading}
            className="quick-btn"
          >
            Wireless accessories
          </button>
        </div>
      </div>
    </div>
  )
}

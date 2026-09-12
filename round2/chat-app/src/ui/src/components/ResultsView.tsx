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

interface ResultsViewProps {
  response: {
    user_query: string
    parsed_intent: string
    results: RankedResult[]
    final_recommendation: string
    bondlayer_enabled: boolean
  }
}

export default function ResultsView({ response }: ResultsViewProps) {
  const getMerchantColor = (merchant: string) => {
    switch (merchant) {
      case 'voltway':
        return '#FF6B6B'
      case 'citycircuit':
        return '#4ECDC4'
      case 'northgear':
        return '#95E1D3'
      default:
        return '#999'
    }
  }

  return (
    <div className="results-view">
      <div className="query-info">
        <h3>Query: {response.user_query}</h3>
        <p className="intent">Intent: {response.parsed_intent}</p>
      </div>

      <div className="recommendation-highlight">
        <h4>💡 Recommendation</h4>
        <p>{response.final_recommendation}</p>
      </div>

      <div className="results-list">
        <h4>Ranked Results ({response.results.length})</h4>
        {response.results.map((result) => (
          <div
            key={result.product_id}
            className="result-card"
            style={{ borderLeftColor: getMerchantColor(result.merchant) }}
          >
            <div className="result-header">
              <div className="rank-badge">#{result.rank}</div>
              <h5>{result.product_name}</h5>
              <div className="merchant-badge" style={{ backgroundColor: getMerchantColor(result.merchant) }}>
                {result.merchant}
              </div>
            </div>

            <div className="result-content">
              <div className="price">${result.price.toFixed(2)}</div>
              <p className="description">{result.description}</p>
              <p className="reasoning">{result.reasoning}</p>
            </div>

            {result.evidence_records.length > 0 && (
              <div className="evidence-summary">
                <span className="evidence-count">
                  📎 {result.evidence_records.length} benefit{result.evidence_records.length !== 1 ? 's' : ''}
                </span>
                <div className="evidence-icons">
                  {result.evidence_records.map((rec) => (
                    <span
                      key={rec.id}
                      className={`evidence-icon ${rec.signed ? 'signed' : 'unsigned'}`}
                      title={rec.description}
                    >
                      {rec.verified && rec.signed ? '✓' : rec.signed ? '📋' : '⚠'}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

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

interface EvidenceTimelineProps {
  response: {
    user_query: string
    parsed_intent: string
    results: RankedResult[]
    final_recommendation: string
    bondlayer_enabled: boolean
  }
}

export default function EvidenceTimeline({ response }: EvidenceTimelineProps) {
  // Flatten all evidence records for timeline view
  const allRecords = response.results.flatMap((result) =>
    result.evidence_records.map((record) => ({
      ...record,
      product_name: result.product_name,
      merchant: result.merchant,
      productPrice: result.price,
    }))
  )

  if (allRecords.length === 0) {
    return (
      <div className="evidence-timeline">
        <h4>Evidence Timeline</h4>
        <p className="no-records">No benefits available for this configuration</p>
      </div>
    )
  }

  // Group records by state
  const signedPriced = allRecords.filter(
    (r) => r.signed && r.verified && r.value !== null
  )
  const signedUnpriced = allRecords.filter(
    (r) => r.signed && r.verified && r.value === null
  )
  const unsigned = allRecords.filter((r) => !r.signed)

  return (
    <div className="evidence-timeline">
      <h4>Evidence Timeline — Record States</h4>
      <p className="timeline-hint">
        Three visually distinct record states show trust levels at a glance
      </p>

      {/* Signed + Priced (Highest trust) */}
      {signedPriced.length > 0 && (
        <div className="record-group signed-priced">
          <div className="group-header">
            <span className="group-title">✓ Signed & Priced</span>
            <span className="group-count">{signedPriced.length}</span>
          </div>
          <p className="group-desc">Fully verified, with measurable value</p>
          {signedPriced.map((record) => (
            <div key={record.id} className="record-item">
              <div className="record-state-icon">✓</div>
              <div className="record-content">
                <strong>{record.description}</strong>
                <p className="record-source">{record.source}</p>
                {record.value && (
                  <span className="record-value">+${record.value.toFixed(2)}</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Signed + Unpriced (Medium trust) */}
      {signedUnpriced.length > 0 && (
        <div className="record-group signed-unpriced">
          <div className="group-header">
            <span className="group-title">📋 Signed & Unpriced</span>
            <span className="group-count">{signedUnpriced.length}</span>
          </div>
          <p className="group-desc">Verified but value not quantified</p>
          {signedUnpriced.map((record) => (
            <div key={record.id} className="record-item">
              <div className="record-state-icon">📋</div>
              <div className="record-content">
                <strong>{record.description}</strong>
                <p className="record-source">{record.source}</p>
                <span className="record-value">$0 (qualitative)</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Unsigned (No trust) */}
      {unsigned.length > 0 && (
        <div className="record-group unsigned">
          <div className="group-header">
            <span className="group-title">⚠ Unsigned Claims</span>
            <span className="group-count">{unsigned.length}</span>
          </div>
          <p className="group-desc">Unverified — displayed but not credited</p>
          {unsigned.map((record) => (
            <div key={record.id} className="record-item">
              <div className="record-state-icon">⚠</div>
              <div className="record-content">
                <strong>{record.description}</strong>
                <p className="record-source">{record.source}</p>
                {record.value && (
                  <span className="record-value" style={{ color: '#999' }}>
                    (claimed: ${record.value.toFixed(2)}) → $0 credited
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="timeline-summary">
        <p>
          <strong>Total Evidence Records:</strong> {allRecords.length} •
          <strong> Credited:</strong> {signedPriced.length} •
          <strong> Verified but unpriced:</strong> {signedUnpriced.length} •
          <strong> Unverified:</strong> {unsigned.length}
        </p>
      </div>
    </div>
  )
}

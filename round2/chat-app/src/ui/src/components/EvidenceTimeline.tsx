interface EvidenceRecord {
  id: string
  type: string
  description: string
  value: number | null
  source: string
  signed: boolean
  verified: boolean
  state?: string  // "signed_priced" | "signed_unpriced" | "unsigned"
  credited_value?: number
  canonical_json?: string | null
  signature?: string | null
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
    records_state_log?: Array<{
      record_id: string
      status: string
      value: number
      credited: number
      verified: boolean
      reason?: string
    }>
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
      // Use the state field if available (from real signing)
      state: record.state || (
        !record.signed ? 'unsigned' :
        record.value === null || record.value === 0 ? 'signed_unpriced' :
        'signed_priced'
      ),
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

  // Group records by state (from backend)
  const signedPriced = allRecords.filter((r) => r.state === 'signed_priced')
  const signedUnpriced = allRecords.filter((r) => r.state === 'signed_unpriced')
  const unsigned = allRecords.filter((r) => r.state === 'unsigned')

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
                {record.signature && <p className="record-sig">Signature: {record.signature}</p>}
                <span className="record-value">
                  +${(record.credited_value || record.value || 0).toFixed(2)} credited
                </span>
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
                <span className="record-value" style={{ color: '#999' }}>
                  Claimed: ${(record.value || 0).toFixed(2)} → Credited: $0
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="timeline-summary">
        <p>
          <strong>Total Records:</strong> {allRecords.length} •
          <strong> Total Credited:</strong> ${allRecords.reduce((sum, r) => sum + (r.credited_value || 0), 0).toFixed(2)} •
          <strong> Signed:</strong> {signedPriced.length + signedUnpriced.length} •
          <strong> Unsigned:</strong> {unsigned.length}
        </p>
        {response.records_state_log && response.records_state_log.length > 0 && (
          <details className="record-log">
            <summary>Record Signing Log ({response.records_state_log.length})</summary>
            <div className="log-content">
              {response.records_state_log.map((log) => (
                <div key={log.record_id} className="log-entry">
                  <strong>{log.status}</strong>: {log.record_id} → ${log.credited} credited {log.verified && '(verified)'}
                  {log.reason && <span className="log-reason">({log.reason})</span>}
                </div>
              ))}
            </div>
          </details>
        )}
      </div>
    </div>
  )
}

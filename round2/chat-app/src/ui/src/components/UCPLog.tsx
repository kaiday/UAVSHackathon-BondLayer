interface UCPLogEntry {
  step: string
  detail: string
  [key: string]: string | string[] | number | undefined
}

interface UCPLogProps {
  log: UCPLogEntry[]
  bondlayerEnabled: boolean
}

export default function UCPLog({ log, bondlayerEnabled }: UCPLogProps) {
  if (!log || log.length === 0) {
    return null
  }

  const getStepIcon = (step: string): string => {
    switch (step) {
      case 'parse_intent':
        return '🔍'
      case 'fan_out':
        return '🌐'
      case 'rank_products':
        return '📊'
      case 'ucp_negotiation':
        return '🔗'
      case 'record_signing':
        return '✍️'
      case 'record_verification':
        return '✔️'
      case 'bondlayer_disabled':
        return '🚫'
      case 'ucp_complete':
        return '✅'
      default:
        return '•'
    }
  }

  return (
    <div className="ucp-log">
      <h4>UCP Integration Log</h4>
      <div className="log-steps">
        {log.map((entry, idx) => (
          <div key={idx} className="log-step">
            <div className="step-header">
              <span className="step-icon">{getStepIcon(entry.step)}</span>
              <span className="step-name">{entry.step}</span>
            </div>
            <p className="step-detail">{entry.detail}</p>
            {entry.capability && (
              <div className="step-data">
                <strong>Capability:</strong> <code>{entry.capability}</code>
              </div>
            )}
            {entry.algorithm && (
              <div className="step-data">
                <strong>Algorithm:</strong> {entry.algorithm}
              </div>
            )}
            {entry.merchants && Array.isArray(entry.merchants) && (
              <div className="step-data">
                <strong>Merchants:</strong> {entry.merchants.join(', ')}
              </div>
            )}
            {entry.records_verified && (
              <div className="step-data">
                <strong>Records Verified:</strong> {entry.records_verified}
              </div>
            )}
            {entry.header_sent && (
              <div className="step-data">
                <strong>Header:</strong> <code>{entry.header_sent}</code>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

import type { AgentResponse, AuditEntry } from '../types'
import { STATE_LABEL } from '../types'

interface Props {
  response: AgentResponse
}

function termsLine(terms: Record<string, unknown>): string {
  return Object.entries(terms)
    .map(([k, v]) => `${k.replace(/_/g, ' ')}: ${v}`)
    .join(' · ')
}

export default function ResultsView({ response }: Props) {
  const auditBySku = new Map<string, AuditEntry>(
    (response.audit || []).map((a) => [a.sku_id, a])
  )

  if (!response.results.length) {
    return <section className="results"><p>No merchant returned a matching listing.</p></section>
  }

  return (
    <section className="results">
      <h2>Ranking</h2>
      <p className="recommendation">{response.final_recommendation}</p>

      {response.results.map((result) => {
        const audit = auditBySku.get(result.sku_id)
        return (
          <article key={result.sku_id} className={`result rank-${result.rank}`}>
            <header className="result-head">
              <span className="rank-badge">#{result.rank}</span>
              <span className="result-title">{result.title}</span>
              <span className="result-merchant">{result.merchant}</span>
              <span className="result-price">${result.shelf_price_aud.toFixed(2)}</span>
            </header>

            <p className="result-reasoning">{result.reasoning}</p>

            {result.agent_decisive_terms?.length > 0 && (
              <div className="decisive">
                <span className="decisive-label">Terms that moved this decision</span>
                <ul>
                  {result.agent_decisive_terms.map((term, i) => <li key={i}>{term}</li>)}
                </ul>
              </div>
            )}

            {result.records.length > 0 && (
              <ul className="records">
                {result.records.map((record, i) => (
                  <li key={i} className={`record state-${record.state}`}>
                    <span className="record-type">{record.benefit_type.replace(/_/g, ' ')}</span>
                    <span className="record-state">{STATE_LABEL[record.state]}</span>
                    {record.cash_value_aud != null && (
                      <span className="record-cash">${record.cash_value_aud.toFixed(2)}</span>
                    )}
                    <span className="record-terms">{termsLine(record.terms)}</span>
                    <blockquote className="record-source">{record.source_span}</blockquote>
                    <span className="record-reason">{record.reason}</span>
                  </li>
                ))}
              </ul>
            )}

            {audit && (
              <p className="audit-line">
                Audit: {audit.verified_fact_count} verified fact
                {audit.verified_fact_count === 1 ? '' : 's'}
                {audit.verified_fees_waived_aud > 0 &&
                  ` · $${audit.verified_fees_waived_aud.toFixed(2)} in fees waived`}
                {audit.ignored_count > 0 && ` · ${audit.ignored_count} ignored`}
              </p>
            )}
          </article>
        )
      })}
    </section>
  )
}

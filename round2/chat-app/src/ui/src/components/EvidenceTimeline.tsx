import type { AgentResponse, EvidenceStep } from '../types'
import { STATE_LABEL } from '../types'

interface Props {
  response: AgentResponse
}

const STEP_TITLE: Record<string, string> = {
  declare: 'Declare capabilities',
  intent_parse: 'Decode the request',
  identity: 'Fetch identity over UCP',
  fan_out: 'Query every merchant',
  rank: 'Agent ranks the offers',
  audit: 'Independent verification audit',
  record_states: 'Every record served',
}

function StepBody({ step }: { step: EvidenceStep }) {
  if (step.step === 'declare' && step.ucp_agent_header) {
    return <code className="step-code">{step.ucp_agent_header}</code>
  }

  if (step.step === 'intent_parse' && step.intent) {
    return (
      <ul className="step-list">
        <li>{step.intent.summary}</li>
        {step.intent.max_price_aud != null && <li>under ${step.intent.max_price_aud}</li>}
        {step.intent.must_have?.map((m, i) => <li key={i}>{m}</li>)}
      </ul>
    )
  }

  if (step.step === 'fan_out' && step.exchanges) {
    return (
      <ul className="step-list">
        {step.exchanges.map((ex) => (
          <li key={ex.merchant}>
            {ex.merchant} - {ex.status_code} - {ex.product_count} products,{' '}
            {ex.record_count} records, extension {ex.extension_served ? 'served' : 'pruned'}
          </li>
        ))}
      </ul>
    )
  }

  if (step.step === 'record_states' && step.records) {
    return (
      <ul className="step-list records-list">
        {step.records.map((r, i) => (
          <li key={i} className={`state-${r.state}`}>
            <strong>{r.merchant}</strong> {r.benefit_type.replace(/_/g, ' ')} -{' '}
            {STATE_LABEL[r.state]}
            {r.cash_value_aud != null && ` - $${r.cash_value_aud.toFixed(2)}`}
            <span className="record-reason"> {r.reason}</span>
          </li>
        ))}
      </ul>
    )
  }

  return null
}

/** Reads as a chain of thought, not a log dump. */
export default function EvidenceTimeline({ response }: Props) {
  return (
    <section className="evidence-timeline">
      <h3>Evidence</h3>
      <ol className="timeline">
        {response.evidence_log.map((step, i) => (
          <li key={i} className={`timeline-step step-${step.step}`}>
            <div className="step-title">{STEP_TITLE[step.step] ?? step.step}</div>
            <div className="step-detail">{step.detail}</div>
            <StepBody step={step} />
          </li>
        ))}
      </ol>
    </section>
  )
}

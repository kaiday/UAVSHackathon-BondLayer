// The agent service response, as of the facts-not-prices refactor.
//
// There is deliberately no "effective cost" here. Most benefits are facts, not
// prices: a 24-month warranty has no honest dollar figure, so the agent decides
// what it is worth and the UI shows which terms moved its decision.

export type RecordState = 'verified_monetary' | 'verified_fact' | 'unverified'

export interface VerifiedRecord {
  merchant: string
  issuer: string
  benefit_type: string
  terms: Record<string, string | number | boolean>
  /** Only set where the benefit really is money the shopper does not pay. */
  cash_value_aud: number | null
  source_span: string
  key_id: string | null
  signed: boolean
  verified: boolean
  state: RecordState
  reason: string
}

export interface RankedResult {
  rank: number
  merchant: string
  sku_id: string
  title: string
  shelf_price_aud: number
  /** The verified terms the agent says actually moved this offer. */
  agent_decisive_terms: string[]
  reasoning: string
  records: VerifiedRecord[]
}

export interface AuditEntry {
  sku_id: string
  merchant: string
  title: string
  shelf_price_aud: number
  verified_fact_count: number
  verified_facts: Array<{ benefit_type: string; terms: Record<string, unknown> }>
  verified_fees_waived_aud: number
  ignored_count: number
  ignored: Array<{ benefit_type: string; claimed_aud: number | null; reason: string }>
}

export interface MerchantExchange {
  merchant: string
  url: string
  request_header: string
  status_code: number
  active_capabilities: Record<string, string>
  pruned_capabilities: Record<string, string>
  extension_served: boolean
  product_count: number
  record_count: number
  error: string | null
}

export interface EvidenceStep {
  step: string
  detail: string
  ucp_agent_header?: string
  bondlayer_declared?: boolean
  exchanges?: MerchantExchange[]
  records?: Array<VerifiedRecord & { sku_id: string }>
  intent?: Intent
  consent_given?: boolean
  audit?: AuditEntry[]
}

export interface Intent {
  summary: string
  category: string | null
  max_price_aud: number | null
  must_have: string[]
}

export interface TranscriptCall {
  label: string
  model: string
  system: string
  prompt: string
  completion: string
  latency_ms: number
  at: string
}

export interface AgentResponse {
  user_query: string
  bondlayer_enabled: boolean
  ucp_agent_header: string
  intent: Intent
  results: RankedResult[]
  final_recommendation: string
  evidence_log: EvidenceStep[]
  audit: AuditEntry[]
  transcript: TranscriptCall[]
}

export const STATE_LABEL: Record<RecordState, string> = {
  verified_monetary: 'Verified - a fee not paid',
  verified_fact: 'Verified fact',
  unverified: 'Unverified - never cited',
}

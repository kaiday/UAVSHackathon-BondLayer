"use client";

import { useEndpoint } from "./api";

export type ComparisonMode = "enabled" | "control" | "all";
export type Demand = { label: string; requests: number; request_ids: string[] };
export type Gap = {
  key: string; kind: string; title: string; reason: string; action: string; href: string;
  sku_ids?: string[]; record_id?: string; need?: string;
};
export type Opportunity = {
  id: string; kind: string; title: string; action: string; href: string; requests: number;
  request_ids: string[]; examples: { request_id: string; reason: string }[];
};
export type Benefit = { record_id: string | null; type: string; label: string; state: string; reason: string };
export type ShoppingRequest = {
  request_id: string; created_at: string; question: string; has_offer: boolean;
  outcome: string; selected: boolean | null; unanswered: string[];
  requirements: { text: string; kind: string; satisfied: boolean; attribute: string | null; record_id: string | null; note: string }[];
  benefits: Benefit[]; gaps: Gap[];
  product: { sku_id: string; title: string | null; price: string | null } | null;
  checkout: { status: string; order_id?: string | null; payment_status?: string | null };
  technical: { request_id: string; evidence_version: number | null; benefits_enabled: boolean | null };
};
export type ShoppingInsights = {
  merchant: string; display_name: string;
  period: { days: number; since: string | null; until: string; mode: ComparisonMode };
  metrics: { requests: number; with_offers: number; unanswered: number; checkout_confirmations: number;
    selected: number; selection_known: number; detailed_reports: number };
  demand: { categories: Demand[]; budgets: Demand[]; needs: Demand[] };
  opportunities: Opportunity[];
  benefits: { label: string; state: string; state_label: string; requests: number; request_ids: string[] }[];
  recent: ShoppingRequest[];
  coverage: { source: string; retained_report_limit: number; excluded_undated_or_future: number; note: string };
};

export function useShoppingInsights(merchant: string | null, days: number, mode: ComparisonMode) {
  return useEndpoint<ShoppingInsights>(merchant ? `/onboard/insights/${encodeURIComponent(merchant)}?days=${days}&mode=${mode}` : null);
}

export const BENEFIT_STATES: Record<string, string> = {
  credited: "Considered with value", unpriced: "Verified, unpriced", not_credited: "Verified, no value credited",
  eligibility_unknown: "Eligibility unknown", ineligible: "Not eligible", expired: "Expired", unverified: "Could not verify",
};
export const GAP_LABELS: Record<string, string> = {
  missing_data: "Missing product facts", missing_evidence: "Missing policy evidence", eligibility_unknown: "Eligibility unknown",
  ineligible: "Offer conditions not met", expired: "Offer expired", unverified: "Verification issue",
  no_offer: "No matching offer", unknown: "Cause not recorded",
};

export function gapExplanation(gap: { kind: string; reason: string }) {
  if (gap.kind === "eligibility_unknown") return "The agent could not establish the shopper's eligibility for this benefit. This does not mean the shopper is ineligible.";
  if (gap.kind === "ineligible") return "The saved comparison reports that this shopper did not meet the offer's conditions.";
  if (gap.kind === "expired") return "The published benefit's validity had ended when the comparison was recorded.";
  if (gap.kind === "unverified") return "The agent could not verify this benefit. Review its published record and signing information.";
  return gap.reason;
}

// Answers a merchant's question from the readiness report alone.
//
// No model and no second data source: the answer is a selection of the
// diagnostics the server already returned for the selected merchant, grouped
// and ordered. Every count on screen is a count of those diagnostics; every
// sentence of advice is the server's own message.

import type { Diagnostic, MerchantReport } from "./api";

export type AskIntent = "fixes" | "blockers" | "field" | "fallback";

export type AskGroup = {
  severity: Diagnostic["severity"];
  rule: string;
  field: string;
  rows: number;
  autofixed: number;
  example: string;
  skus: string[];
};

export type AskAnswer = {
  intent: AskIntent;
  matched: string;
  fields: string[];
  groups: AskGroup[];
};

const SEVERITY_ORDER: Diagnostic["severity"][] = ["blocker", "degrades_match", "cosmetic", "info"];

// Shopper-facing words for the report's field names. A field is also matched by
// its own name ("gtin", "screen_in"), so a field not listed here still works.
const FIELD_WORDS: Record<string, string[]> = {
  price: ["price", "prices", "pricing", "cost", "costs"],
  weight_kg: ["weight", "weights", "heavy", "light", "kg"],
  ram: ["ram", "memory"],
  storage: ["storage", "ssd", "disk"],
  screen_in: ["screen", "screens", "display", "inch", "inches"],
  gtin: ["gtin", "barcode", "barcodes", "ean", "upc"],
  title: ["title", "titles", "name", "names", "duplicate", "duplicates"],
  brand: ["brand", "brands"],
  battery_wh: ["battery", "batteries"],
  cpu: ["cpu", "processor", "processors"],
  category: ["category", "categories"],
  condition: ["condition"],
};

const BLOCKER_WORDS = ["blocker", "blockers", "blocking", "worst", "urgent", "critical"];
const FIX_WORDS = [
  "improve", "improving", "performance", "perform", "fix", "fixes", "readiness", "ready",
  "score", "better", "boost", "increase", "visible", "visibility", "rank", "ranking",
  "win", "sales", "sell", "agents", "agent", "problem", "problems", "issues", "wrong",
];

function words(question: string): string[] {
  return question.toLowerCase().match(/[a-z0-9_]+/g) ?? [];
}

function groupDiagnostics(diagnostics: Diagnostic[]): AskGroup[] {
  const groups = new Map<string, AskGroup>();
  for (const d of diagnostics) {
    const key = `${d.severity}|${d.rule}|${d.field}`;
    let group = groups.get(key);
    if (!group) {
      group = { severity: d.severity, rule: d.rule, field: d.field, rows: 0, autofixed: 0, example: d.message, skus: [] };
      groups.set(key, group);
    }
    group.rows += 1;
    if (d.autofixed) group.autofixed += 1;
    if (!group.skus.includes(d.sku_id)) group.skus.push(d.sku_id);
  }
  return [...groups.values()].sort(
    (a, b) => SEVERITY_ORDER.indexOf(a.severity) - SEVERITY_ORDER.indexOf(b.severity) || b.rows - a.rows,
  );
}

export function answer(question: string, report: MerchantReport): AskAnswer {
  const asked = words(question);
  const groups = groupDiagnostics(report.diagnostics);
  const actionable = groups.filter((g) => g.severity !== "info");

  const reportFields = [...new Set(report.diagnostics.map((d) => d.field))];
  const fields = reportFields.filter((field) =>
    asked.includes(field.toLowerCase()) || (FIELD_WORDS[field] ?? []).some((w) => asked.includes(w)),
  );
  if (fields.length > 0) {
    return {
      intent: "field",
      matched: `your question mentions ${fields.join(", ")}`,
      fields,
      groups: groups.filter((g) => fields.includes(g.field)),
    };
  }

  const blockerWord = BLOCKER_WORDS.find((w) => asked.includes(w));
  if (blockerWord) {
    return {
      intent: "blockers",
      matched: `"${blockerWord}"`,
      fields: [],
      groups: groups.filter((g) => g.severity === "blocker"),
    };
  }

  const fixWord = FIX_WORDS.find((w) => asked.includes(w));
  if (fixWord) {
    return { intent: "fixes", matched: `"${fixWord}"`, fields: [], groups: actionable };
  }

  return { intent: "fallback", matched: "no catalogue topic", fields: [], groups: actionable.slice(0, 3) };
}

"use client";

// The only source of numbers in this console.
//
// Every figure rendered anywhere under /console comes from a response fetched
// here. There is no fixture file, no seeded array, no placeholder total. If a
// value is not in one of these payloads it does not appear on screen.
//
// URLs are relative on purpose: the static export is served by the same
// FastAPI process that serves /onboard, so same-origin fetch needs no base URL,
// no CORS and no configuration at the venue.

import { useCallback, useEffect, useState, useSyncExternalStore } from "react";

export type MerchantSummary = {
  merchant: string;
  display_name: string;
  domain: string;
  rows_read: number;
  readiness: number;
  blockers: number;
};

export type Diagnostic = {
  row: number;
  sku_id: string;
  field: string;
  rule: string;
  severity: "blocker" | "degrades_match" | "cosmetic" | "info";
  found: string;
  normalised: string | null;
  message: string;
  autofixed: boolean;
};

export type MerchantReport = {
  merchant: string;
  rows_read: number;
  rows_rejected: number;
  skus: number;
  readiness: number;
  attributes_fixed: number;
  by_severity: Record<string, number>;
  by_rule: Record<string, number>;
  diagnostics: Diagnostic[];
};

export type RequestSummary = {
  request_id: string;
  utterance: string;
  merchants: Array<{ merchant: string; control_merchant: boolean; won: boolean }>;
};

export type MerchantRow = {
  request_id: string;
  merchant: string;
  control_merchant: boolean;
  fields_exposed: number;
  legible_share: number;
  value_credited_aud: string | null;
  value_withheld_aud: string | null;
  won: boolean;
  lost_because: string | null;
  sku_id: string | null;
  shelf_price: string | null;
  effective_cost: string | null;
  unsatisfied: string[];
};

export type RequestReport = {
  source?: string;
  extension_enabled?: boolean;
  request_id: string;
  utterance: string;
  bundle: boolean;
  expect_unsatisfied: boolean;
  constraints: Array<{ text: string; kind: string }>;
  metrics: Record<string, unknown>;
  unsatisfied: string[];
  bundle_composed: Record<string, unknown> | null;
  merchants: MerchantRow[];
  control: MerchantRow[];
};

async function getJSON<T>(path: string): Promise<T> {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    throw new Error(`${path} returned ${response.status} ${response.statusText}`);
  }
  return (await response.json()) as T;
}

// --- the selected merchant ------------------------------------------------
//
// One value, shared by every page, kept outside React so a page does not need a
// provider above it. Persisted so switching merchant survives a navigation.

const STORAGE_KEY = "bondlayer.console.merchant";
const listeners = new Set<() => void>();
let selected: string | null = null;

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function setMerchant(merchant: string | null) {
  selected = merchant;
  try {
    if (merchant === null) window.localStorage.removeItem(STORAGE_KEY);
    else window.localStorage.setItem(STORAGE_KEY, merchant);
  } catch {
    // Private windows and blocked site data: the selection just does not persist.
  }
  listeners.forEach((listener) => listener());
}

export function useSelectedMerchant(): string | null {
  const stored = useSyncExternalStore(
    subscribe,
    () => selected,
    () => null,
  );
  useEffect(() => {
    if (selected !== null) return;
    try {
      const remembered = window.localStorage.getItem(STORAGE_KEY);
      if (remembered) setMerchant(remembered);
    } catch {
      // ignored — the merchant list will select a default instead
    }
  }, []);
  return stored;
}

// --- fetch hooks ----------------------------------------------------------

export type Loadable<T> = {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
};

export function useEndpoint<T>(path: string | null): Loadable<T> {
  const [result, setResult] = useState<{ key: string; path: string; data: T | null; error: string | null } | null>(null);
  const [nonce, setNonce] = useState(0);
  const key = `${path}:${nonce}`;

  useEffect(() => {
    if (path === null) return;
    let live = true;
    getJSON<T>(path)
      .then((payload) => {
        if (live) {
          setResult({ key, path, data: payload, error: null });
        }
      })
      .catch((cause: unknown) => {
        if (live) {
          setResult({ key, path, data: null, error: cause instanceof Error ? cause.message : String(cause) });
        }
      });
    return () => {
      live = false;
    };
  }, [path, key]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  const current = path !== null && result?.key === key ? result : null;
  return { data: path !== null && result?.path === path ? result.data : null, error: current?.error ?? null,
    loading: path !== null && current === null, reload };
}

/** `GET /onboard/merchants` — and it selects the first merchant if none is set. */
export function useMerchants(): Loadable<MerchantSummary[]> {
  const state = useEndpoint<MerchantSummary[]>("/onboard/merchants");
  const merchant = useSelectedMerchant();
  useEffect(() => {
    if (!state.loading && state.data && !state.data.some((entry) => entry.merchant === merchant)) {
      const next = state.data[0]?.merchant ?? null;
      if (next !== merchant) setMerchant(next);
    }
  }, [merchant, state.data, state.loading]);
  useEffect(() => {
    window.addEventListener("bondlayer:merchants-changed", state.reload);
    return () => window.removeEventListener("bondlayer:merchants-changed", state.reload);
  }, [state.reload]);
  return state;
}

export function refreshMerchants() {
  window.dispatchEvent(new Event("bondlayer:merchants-changed"));
}

export type CatalogueUpload = { merchant: string; display_name: string; report: MerchantReport; published: boolean };

export async function uploadCatalogue(file: File, options: {
  merchant?: string; displayName?: string; domain?: string; preview?: boolean; create?: boolean;
} = {}): Promise<CatalogueUpload> {
  const params = new URLSearchParams();
  if (options.merchant) params.set("merchant", options.merchant);
  if (options.preview) params.set("preview", "true");
  if (options.create) params.set("create", "true");
  const form = new FormData();
  form.append("file", file);
  if (options.displayName !== undefined) form.append("display_name", options.displayName);
  if (options.domain !== undefined) form.append("domain", options.domain);
  const response = await fetch(`/onboard/catalog?${params}`, { method: "POST", body: form });
  const text = await response.text();
  let body;
  try { body = JSON.parse(text); } catch { throw new Error(`Catalogue service returned ${response.status}. Please retry.`); }
  if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : `Upload failed (${response.status})`);
  return body as CatalogueUpload;
}

/** `GET /onboard/report/{merchant}` */
export function useReport(merchant: string | null): Loadable<MerchantReport> {
  return useEndpoint<MerchantReport>(merchant ? `/onboard/report/${merchant}` : null);
}

/** `GET /onboard/requests` */
export function useRequests(): Loadable<RequestSummary[]> {
  return useEndpoint<RequestSummary[]>("/onboard/requests");
}

/** `GET /onboard/requests/{id}` */
export function useRequestReport(id: string | null): Loadable<RequestReport> {
  return useEndpoint<RequestReport>(id ? `/onboard/requests/${id}` : null);
}

// --- formatting -----------------------------------------------------------
//
// Formatters only. None of these invents, rounds up, defaults or fills in a
// value; a missing figure renders as an em dash, never as zero.

export function money(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return `$${n.toLocaleString("en-AU", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function percent(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

export function severityTone(severity: string): string {
  if (severity === "blocker") return "danger";
  if (severity === "degrades_match") return "warning";
  return "neutral";
}

/** `blocker` → `Blocker`, `degrades_match` → `Degrades match`. */
export function humanise(token: string): string {
  const spaced = token.replace(/_/g, " ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

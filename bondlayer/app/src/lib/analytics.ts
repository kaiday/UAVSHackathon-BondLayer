"use client";

// The Analytics page's two sources, kept apart from api.ts so each stays small.
//
//   /onboard/analytics  — the benchmark: 30 frozen requests, summed server-side
//   /onboard/traffic    — live: the UCP calls this server actually received
//
// Same rule as api.ts: every figure on screen is a field of one of these
// payloads. Nothing is computed, seeded or filled in here.

import { useCallback, useEffect, useState } from "react";

export type BenchmarkMerchant = {
  merchant: string;
  control_merchant: boolean;
  requests: number;
  wins: number;
  win_rate: number;
  value_credited_aud: string;
  value_withheld_aud: string;
  mean_legible_share: number;
};

export type LossReason = {
  reason: string;
  count: number;
  merchants: Record<string, number>;
};

export type Benchmark = {
  source: "benchmark";
  requests: number;
  eval_commit: string | null;
  merchants: BenchmarkMerchant[];
  loss_reasons: LossReason[];
  service_values_answered: { bondlayer: [number, number]; control: [number, number] };
};

export const ROUTES = ["profile", "search", "lookup", "intent", "checkout"] as const;
export type Route = (typeof ROUTES)[number];

export type TrafficPoint = { t: number; total: number } & Record<Route, number>;

export type TrafficEvent = {
  ts: number;
  kind: "call" | "order";
  merchant: string;
  route: Route | null;
  status: number | null;
  declared: string[];
  order_id: string | null;
  honoured: number | null;
  cited: number | null;
};

export type Traffic = {
  source: "live";
  merchant: string | null;
  now: number;
  first_event: number | null;
  bucket: "minute" | "hour";
  bucket_seconds: number;
  window: number;
  totals: {
    calls: number;
    by_route: Record<Route, number>;
    refused_406: number;
    declared_benefit_value: number;
    declared_intent_match: number;
    benefit_value_share: number | null;
  };
  orders: { count: number; honoured: number; cited: number };
  by_merchant: Array<{ merchant: string; calls: number; orders: number }>;
  series: TrafficPoint[];
  recent: TrafficEvent[];
};

export type Polled<T> = { data: T | null; error: string | null; reload: () => void };

function usePolled<T>(path: string, everyMs: number | null): Polled<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let live = true;
    const load = () =>
      fetch(path, { headers: { Accept: "application/json" } })
        .then((response) => {
          if (!response.ok) throw new Error(`${path} returned ${response.status} ${response.statusText}`);
          return response.json() as Promise<T>;
        })
        .then((payload) => {
          if (live) {
            setData(payload);
            setError(null);
          }
        })
        .catch((cause: unknown) => {
          if (live) setError(cause instanceof Error ? cause.message : String(cause));
        });
    load();
    const timer = everyMs === null ? null : window.setInterval(load, everyMs);
    return () => {
      live = false;
      if (timer !== null) window.clearInterval(timer);
    };
  }, [path, everyMs, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return { data, error, reload };
}

/** `GET /onboard/analytics` — fetched once; the benchmark does not move. */
export function useBenchmark(): Polled<Benchmark> {
  return usePolled<Benchmark>("/onboard/analytics", null);
}

/** `GET /onboard/traffic` — polled, so the live chart fills in as calls arrive. */
export function useTraffic(merchant: string | null, bucket: "minute" | "hour"): Polled<Traffic> {
  const query = new URLSearchParams({ bucket, window: bucket === "minute" ? "60" : "24" });
  if (merchant) query.set("merchant", merchant);
  return usePolled<Traffic>(`/onboard/traffic?${query}`, 5000);
}

/** `DELETE /onboard/traffic` — a clean chart before a demo run. */
export async function resetTraffic(): Promise<void> {
  const response = await fetch("/onboard/traffic", { method: "DELETE" });
  if (!response.ok) throw new Error(`/onboard/traffic returned ${response.status}`);
}

/** Epoch seconds → local clock time, e.g. `11:42`. */
export function clock(seconds: number, withSeconds = false): string {
  return new Date(seconds * 1000).toLocaleTimeString("en-AU", {
    hour: "2-digit",
    minute: "2-digit",
    ...(withSeconds ? { second: "2-digit" } : {}),
  });
}

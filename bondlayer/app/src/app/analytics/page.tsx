"use client";

import { useState } from "react";
import { Failed, Loading } from "@/components/states";
import { humanise, money, percent } from "@/lib/api";
import {
  ROUTES,
  clock,
  resetTraffic,
  useBenchmark,
  useTraffic,
  type Benchmark,
  type Traffic,
} from "@/lib/analytics";
import styles from "./analytics.module.css";

/**
 * Two sources, labelled so they cannot be confused:
 *
 * - Benchmark — the 30 frozen requests, summed by /onboard/analytics from the
 *   same reports the Request console shows one at a time.
 * - Live traffic — the UCP calls this server actually received, from
 *   /onboard/traffic. Counts only; never the shopper's words.
 *
 * Every figure is a field of those payloads. An empty log renders as an empty
 * state, never as a placeholder series.
 */
export default function AnalyticsPage() {
  return (
    <div className="content">
      <div className="page-heading">
        <div>
          <h1>Analytics</h1>
          <p>
            Two sources, kept apart: the <b>benchmark</b> is the frozen 30-request evaluation, and
            <b> live traffic</b> is what agents have actually sent this server since it started.
          </p>
        </div>
      </div>
      <BenchmarkSection />
      <TrafficSection />
    </div>
  );
}

// --- benchmark --------------------------------------------------------------

function BenchmarkSection() {
  const { data, error } = useBenchmark();
  return (
    <section className={`panel ${styles.section}`}>
      <div className="panel-heading">
        <div>
          <h2>Benchmark</h2>
          <p>
            Summed from the request reports written by <code>scripts/eval_run.py</code>
            {data?.eval_commit && (
              <>
                {" "}at <code>{data.eval_commit}</code>
              </>
            )}
            . These numbers do not move while the server runs.
          </p>
        </div>
        <span className="pill neutral">{data ? `${data.requests} frozen requests` : "frozen requests"}</span>
      </div>
      {error && <Failed what="the benchmark" error={error} />}
      {!data && !error && <Loading what="the benchmark" />}
      {data && <BenchmarkBody data={data} />}
    </section>
  );
}

function BenchmarkBody({ data }: { data: Benchmark }) {
  const [answered, total] = data.service_values_answered.bondlayer;
  const [answeredControl, totalControl] = data.service_values_answered.control;
  return (
    <div className={styles.body}>
      <div className={styles.headline}>
        <div>
          <span>SERVICE + VALUES clauses answered</span>
          <strong>
            {answered}/{total}
          </strong>
          <small>with signed benefit records</small>
        </div>
        <div>
          <span>Same clauses, control</span>
          <strong>
            {answeredControl}/{totalControl}
          </strong>
          <small>catalogue attributes only</small>
        </div>
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Merchant</th>
              <th>Wins</th>
              <th>Win rate</th>
              <th>Verified value credited</th>
              <th>Value withheld</th>
              <th>Mean legible share</th>
            </tr>
          </thead>
          <tbody>
            {data.merchants.map((m) => (
              <tr key={m.merchant}>
                <td>
                  <strong>{humanise(m.merchant)}</strong>{" "}
                  {m.control_merchant && <span className="pill neutral">control</span>}
                </td>
                <td>
                  {m.wins} of {m.requests}
                </td>
                <td>
                  <span className={styles.rate}>
                    <i style={{ width: `${m.win_rate * 100}%` }} />
                  </span>
                  {percent(m.win_rate)}
                </td>
                <td>
                  <span className="money-pill">{money(m.value_credited_aud)}</span>
                </td>
                <td>
                  <span className="money-pill withheld">{money(m.value_withheld_aud)}</span>
                </td>
                <td>{percent(m.mean_legible_share)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h3 className={styles.subhead}>Why merchants lost</h3>
      <ul className={styles.reasons}>
        {data.loss_reasons.map((r) => (
          <li key={r.reason}>
            <b>{r.count}</b>
            <span>
              {r.reason}
              <small>
                {Object.entries(r.merchants)
                  .map(([merchant, n]) => `${humanise(merchant)} ${n}`)
                  .join(" · ")}
              </small>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

// --- live traffic -------------------------------------------------------------

function TrafficSection() {
  const [merchant, setMerchant] = useState<string | null>(null);
  const [bucket, setBucket] = useState<"minute" | "hour">("minute");
  const [armed, setArmed] = useState(false);
  const { data, error, reload } = useTraffic(merchant, bucket);

  const onReset = async () => {
    if (!armed) {
      setArmed(true);
      return;
    }
    setArmed(false);
    await resetTraffic();
    reload();
  };

  return (
    <section className={`panel ${styles.section}`}>
      <div className="panel-heading">
        <div>
          <h2>Live traffic</h2>
          <p>
            Calls agents made to this server&rsquo;s UCP routes, refreshed every 5 seconds. Counted:
            route, status and the capabilities the agent declared. Never recorded: the shopper&rsquo;s
            words or anything shopper-side.
          </p>
        </div>
        <span className="pill success">this server, live</span>
      </div>

      <div className={styles.controls}>
        <div className="filter-row">
          <button
            className={`pill ${merchant === null ? "success" : "neutral"}`}
            onClick={() => setMerchant(null)}
            type="button"
          >
            All merchants
          </button>
          {data?.by_merchant.map((m) => (
            <button
              className={`pill ${merchant === m.merchant ? "success" : "neutral"}`}
              key={m.merchant}
              onClick={() => setMerchant(m.merchant)}
              type="button"
            >
              {humanise(m.merchant)} {m.calls}
            </button>
          ))}
        </div>
        <div className="filter-row">
          {(["minute", "hour"] as const).map((value) => (
            <button
              className={`pill ${bucket === value ? "success" : "neutral"}`}
              key={value}
              onClick={() => setBucket(value)}
              type="button"
            >
              Per {value}
            </button>
          ))}
          <button className={`pill ${armed ? "danger" : "neutral"}`} onClick={onReset} type="button">
            {armed ? "Click again to clear the log" : "Reset"}
          </button>
        </div>
      </div>

      {error && <Failed what="live traffic" error={error} />}
      {!data && !error && <Loading what="live traffic" />}
      {data && <TrafficBody data={data} />}
    </section>
  );
}

function TrafficBody({ data }: { data: Traffic }) {
  if (data.totals.calls === 0 && data.orders.count === 0) {
    return (
      <div className={styles.empty}>
        <strong>No agent traffic yet{data.merchant ? ` for ${humanise(data.merchant)}` : ""}.</strong>
        <p>
          Send a query from the buyer agent (<code>:8001</code>), or run the <code>curl</code> calls in
          the README. This chart fills in as calls arrive.
        </p>
      </div>
    );
  }

  const { totals, orders } = data;
  return (
    <div className={styles.body}>
      <div className={styles.headline}>
        <div>
          <span>UCP calls</span>
          <strong>{totals.calls}</strong>
          <small>{data.first_event ? `since ${clock(data.first_event)}` : "—"}</small>
        </div>
        <div>
          <span>Declared the benefit extension</span>
          <strong>{percent(totals.benefit_value_share)}</strong>
          <small>
            {totals.declared_benefit_value} of {totals.calls} calls
          </small>
        </div>
        <div>
          <span>Refused (406)</span>
          <strong>{totals.refused_406}</strong>
          <small>capability not negotiated</small>
        </div>
        <div>
          <span>Orders placed</span>
          <strong>{orders.count}</strong>
          <small>
            {orders.honoured} of {orders.cited} cited records honoured
          </small>
        </div>
      </div>

      <TrafficChart data={data} />

      <ul className={styles.routes}>
        {ROUTES.map((route) => (
          <li key={route}>
            <span>{humanise(route)}</span>
            <b>{totals.by_route[route]}</b>
          </li>
        ))}
      </ul>

      <h3 className={styles.subhead}>Most recent</h3>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Time</th>
              <th>Merchant</th>
              <th>Event</th>
              <th>Status</th>
              <th>Declared</th>
            </tr>
          </thead>
          <tbody>
            {data.recent.map((e, i) => (
              <tr key={`${e.ts}-${i}`}>
                <td>{clock(e.ts, true)}</td>
                <td>{humanise(e.merchant)}</td>
                <td>
                  {e.kind === "order" ? (
                    <>
                      order <code>{e.order_id}</code> · {e.honoured}/{e.cited} honoured
                    </>
                  ) : (
                    humanise(e.route ?? "")
                  )}
                </td>
                <td>
                  {e.status === null ? (
                    "—"
                  ) : (
                    <span className={`pill ${e.status < 400 ? "success" : "danger"}`}>{e.status}</span>
                  )}
                </td>
                <td>
                  {e.kind === "order"
                    ? "—"
                    : e.declared.length
                      ? e.declared.map(humanise).join(", ")
                      : "plain UCP"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function TrafficChart({ data }: { data: Traffic }) {
  const points = data.series;
  const peak = Math.max(1, ...points.map((p) => p.total));
  const step = points.length > 1 ? 600 / (points.length - 1) : 0;
  const xy = points.map((p, i) => [i * step, 160 - (p.total / peak) * 140] as const);
  const label = `Calls per ${data.bucket}, last ${data.window} ${data.bucket}s, peak ${peak}`;

  return (
    <div className="line-chart" role="img" aria-label={label}>
      <svg viewBox="0 0 600 170" preserveAspectRatio="none">
        <path className="chart-grid" d="M0 20H600M0 90H600M0 160H600" />
        <polyline className="chart-line" points={xy.map(([x, y]) => `${x},${y}`).join(" ")} />
        {xy.map(([x, y], i) => (
          <circle className="chart-point" cx={x} cy={y} key={points[i].t} r={4}>
            <title>
              {clock(points[i].t)} · {points[i].total} calls
            </title>
          </circle>
        ))}
      </svg>
      <div className="chart-axis">
        <span>{points.length ? clock(points[0].t) : ""}</span>
        <span>peak {peak} per {data.bucket}</span>
        <span>now</span>
      </div>
    </div>
  );
}

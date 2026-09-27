"use client";

import Link from "next/link";
import { Check, ChevronDown } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { humanise, setMerchant, useMerchants, useSelectedMerchant, type MerchantReport } from "@/lib/api";
import { useShoppingInsights, type ShoppingInsights } from "@/lib/insights";

function activitySeries(data: ShoppingInsights | null) {
  const end = data ? new Date(data.period.until) : new Date();
  const dates = Array.from({ length: 14 }, (_, index) => {
    const date = new Date(end);
    date.setUTCDate(end.getUTCDate() - (13 - index));
    return date.toISOString().slice(0, 10);
  });
  const counts = new Map(dates.map((date) => [date, 0]));
  data?.recent.forEach((request) => {
    const date = request.created_at.slice(0, 10);
    if (counts.has(date)) counts.set(date, (counts.get(date) ?? 0) + 1);
  });
  return dates.map((date) => counts.get(date) ?? 0);
}

function ActivityLine({ values }: { values: number[] }) {
  const width = 420;
  const height = 112;
  const pad = 8;
  const maximum = Math.max(1, ...values);
  const x = (index: number) => pad + (index / Math.max(1, values.length - 1)) * (width - pad * 2);
  const y = (value: number) => height - pad - (value / maximum) * (height - pad * 2);
  const points = values.map((value, index) => `${x(index)},${y(value)}`).join(" ");
  const area = `M${x(0)},${height - pad} L${points.replaceAll(" ", " L")} L${x(values.length - 1)},${height - pad} Z`;
  const total = values.reduce((sum, value) => sum + value, 0);

  return (
    <div className="catalogue-activity-plot">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${total} shopping requests in the last 14 days`}>
        {[.25, .5, .75].map((position) => <line key={position} x1={pad} x2={width - pad} y1={height * position} y2={height * position} />)}
        <path className="catalogue-activity-area" d={area} />
        <polyline points={points} />
        <circle cx={x(values.length - 1)} cy={y(values[values.length - 1])} r="4" />
      </svg>
      <div><span>14 days ago</span><span>{total ? `${total} requests` : "No requests yet"}</span><span>Today</span></div>
    </div>
  );
}

/**
 * Merchant dropdown used in the Catalogue page's action row. Every merchant comes from
 * `GET /onboard/merchants`, so a merchant added to the server appears without
 * a rebuild.
 */
export function CurrentMerchant() {
  const { data } = useMerchants();
  const selected = useSelectedMerchant();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const current = data?.find((merchant) => merchant.merchant === selected);
  useEffect(() => {
    function close(event: PointerEvent) {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, []);
  if (!current) return <span />;

  return (
    <div className={`current-merchant ${open ? "is-open" : ""}`} ref={rootRef} onKeyDown={event => {
      if (event.key === "Escape") {
        setOpen(false);
        rootRef.current?.querySelector<HTMLButtonElement>(".merchant-trigger")?.focus();
      }
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        setOpen(true);
        requestAnimationFrame(() => {
          const options = Array.from(rootRef.current?.querySelectorAll<HTMLButtonElement>(".merchant-menu button") ?? []);
          const index = options.indexOf(document.activeElement as HTMLButtonElement);
          options[(index + (event.key === "ArrowDown" ? 1 : -1) + options.length) % options.length]?.focus();
        });
      }
    }}>
      <button type="button" className="merchant-trigger" aria-haspopup="listbox" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span>Merchant</span>
        <strong>{current.display_name || humanise(current.merchant)}</strong>
        <ChevronDown size={15} aria-hidden="true" />
      </button>
      <div className="merchant-menu" role="listbox" aria-label="Choose merchant" inert={!open}>
        {data?.map((merchant, index) => (
          <button type="button" role="option" aria-selected={merchant.merchant === current.merchant} className={merchant.merchant === current.merchant ? "selected" : ""} key={merchant.merchant}
            style={{ transitionDelay: open ? `${index * 35}ms` : "0ms" }}
            onClick={() => { setMerchant(merchant.merchant); setOpen(false); rootRef.current?.querySelector<HTMLButtonElement>(".merchant-trigger")?.focus(); }}>
            <i className="merchant-option-mark" aria-hidden="true">{merchant.merchant === current.merchant && <Check size={12} />}</i>
            <span>{merchant.display_name || humanise(merchant.merchant)}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

/**
 * One card per merchant. The five with the most blockers show first (lowest
 * readiness breaks ties), so the stores that need fixing lead. The selected
 * merchant is always among the visible cards.
 */
export function ComparisonStrip({ report }: { report?: MerchantReport | null }) {
  const { data } = useMerchants();
  const selected = useSelectedMerchant();
  const { data: insights } = useShoppingInsights(selected, 30, "enabled");
  if (!data) return null;

  const ranked = [...data].sort((a, b) => b.blockers - a.blockers || a.readiness - b.readiness);
  const current = ranked.find((merchant) => merchant.merchant === selected) ?? ranked[0];
  const others = ranked.filter((merchant) => merchant.merchant !== current?.merchant);
  if (!current) return null;
  const activity = activitySeries(insights);

  return (
    <section className="catalogue-group" aria-label="Catalogue selection" data-tour="comparison">
      <div className="catalogue-browser">
        <div className="catalogue-column">
          <div className="catalogue-column-heading"><h3>Selected catalogue</h3></div>
          <article className="catalogue-featured" aria-label={`Selected catalogue: ${current.display_name || humanise(current.merchant)}`}>
            <header>
              <h3>{current.display_name || humanise(current.merchant)}</h3>
              <span className="catalogue-active-pill">Active</span>
            </header>
            <div className="catalogue-featured-overview">
              <div className="catalogue-featured-score"><strong>{current.readiness}%</strong><span>Agent readiness</span></div>
              <div className="catalogue-featured-chart">
                <p>Shopping activity <span>Last 14 days</span></p>
                <ActivityLine values={activity} />
              </div>
            </div>
            <div className="catalogue-featured-summary">
              <h4>Catalogue summary</h4>
              <dl>
                <div><dt>Catalogue rows</dt><dd>{current.rows_read}</dd></div>
                <div><dt>Rows rejected</dt><dd>{report?.rows_rejected ?? "—"}</dd></div>
                <div><dt>Auto-fixed</dt><dd>{report?.attributes_fixed ?? "—"}</dd></div>
                <div><dt>Issues</dt><dd>{report?.diagnostics.length ?? "—"}</dd></div>
              </dl>
            </div>
          </article>
        </div>

        <div className="catalogue-column">
          <div className="catalogue-column-heading"><h3>Other catalogues</h3><p>{others.length} available</p></div>
          <aside className="catalogue-list-panel" aria-label="Other catalogues">
            {others.length ? <div className="catalogue-list">
              {others.map((merchant) => (
                <button type="button" key={merchant.merchant} onClick={() => setMerchant(merchant.merchant)}>
                  <span><strong>{merchant.display_name || humanise(merchant.merchant)}</strong><small>{merchant.rows_read} rows · {merchant.blockers} blockers</small></span>
                  <b>{merchant.readiness}%</b>
                </button>
              ))}
            </div> : <div className="catalogue-list-empty"><p>No other catalogues yet.</p><Link href="/onboarding/">Add another catalogue →</Link></div>}
          </aside>
        </div>
      </div>
    </section>
  );
}

"use client";

import { useState } from "react";
import { X } from "lucide-react";
import { humanise, setMerchant, useMerchants, useSelectedMerchant } from "@/lib/api";

const TOP = 5;

/**
 * The merchant being viewed, shown in the topbar as plain text. Switching
 * happens on the merchant cards; every merchant listed comes from
 * `GET /onboard/merchants`, so a merchant added to the server appears without
 * a rebuild.
 */
export function CurrentMerchant() {
  const { data } = useMerchants();
  const selected = useSelectedMerchant();
  const current = data?.find((merchant) => merchant.merchant === selected);
  if (!current) return <span />;

  return (
    <p className="current-merchant">
      <span>Merchant</span>
      <strong>{current.display_name || humanise(current.merchant)}</strong>
    </p>
  );
}

/**
 * One card per merchant. The five with the most blockers show first (lowest
 * readiness breaks ties), so the stores that need fixing lead. The selected
 * merchant is always among the visible cards.
 */
export function ComparisonStrip() {
  const { data } = useMerchants();
  const selected = useSelectedMerchant();
  const [expanded, setExpanded] = useState(false);
  if (!data) return null;

  const ranked = [...data].sort((a, b) => b.blockers - a.blockers || a.readiness - b.readiness);
  let visible = expanded ? ranked : ranked.slice(0, TOP);
  if (!expanded && selected && !visible.some((merchant) => merchant.merchant === selected)) {
    const current = ranked.find((merchant) => merchant.merchant === selected);
    if (current) visible = [...visible.slice(0, TOP - 1), current];
  }

  return (
    <section className="merchant-strip" aria-label="Merchant comparison" data-tour="comparison">
      {visible.map((merchant) => (
        <article
          className={`metric merchant-card ${merchant.merchant === selected ? "metric-selected" : ""}`}
          key={merchant.merchant}
          onClick={() => setMerchant(merchant.merchant)}
        >
          <p><button className="merchant-select" onClick={() => setMerchant(merchant.merchant)} aria-pressed={merchant.merchant === selected}>{merchant.display_name || humanise(merchant.merchant)}</button></p>
          <strong>{merchant.readiness}%</strong>
          <div className="metric-trend">
            <span className={merchant.blockers > 0 ? "down" : "up"}>
              {merchant.blockers} blockers
            </span>
            <small>{merchant.rows_read} rows</small>
          </div>
        </article>
      ))}
      {data.length > TOP && (
        <button type="button" className={`strip-toggle ${expanded ? "is-open" : ""}`} aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>
          {expanded ? <><X size={15} strokeWidth={2.2} aria-hidden="true" /> Close</> : `Show all merchants (${data.length})`}
        </button>
      )}
    </section>
  );
}

"use client";

import { humanise, setMerchant, useMerchants, useSelectedMerchant } from "@/lib/api";

/**
 * The switcher in the topbar. Its options are whatever `GET /onboard/merchants`
 * returns — there is no hardcoded merchant list, so a merchant added to the
 * server appears here without a rebuild.
 */
export function MerchantSwitcher() {
  const { data, error } = useMerchants();
  const selected = useSelectedMerchant();

  if (error) return <span className="switcher-error">merchants unavailable</span>;
  if (!data) return <span className="switcher-error">loading merchants…</span>;

  return (
    <label className="merchant-switcher">
      <span>Merchant</span>
      <select value={selected ?? ""} onChange={(event) => setMerchant(event.target.value)}>
        {data.map((merchant) => (
          <option key={merchant.merchant} value={merchant.merchant}>
            {humanise(merchant.merchant)} · {merchant.readiness}% ready
          </option>
        ))}
      </select>
    </label>
  );
}

/** One row per merchant, straight off `/onboard/merchants`. */
export function ComparisonStrip() {
  const { data } = useMerchants();
  const selected = useSelectedMerchant();
  if (!data) return null;

  return (
    <section className="metrics" aria-label="Merchant comparison" data-tour="comparison">
      {data.map((merchant) => (
        <article
          className={`metric ${merchant.merchant === selected ? "metric-selected" : ""}`}
          key={merchant.merchant}
        >
          <p>{humanise(merchant.merchant)}</p>
          <strong>{merchant.readiness}%</strong>
          <div className="metric-trend">
            <span className={merchant.blockers > 0 ? "down" : "up"}>
              {merchant.blockers} blockers
            </span>
            <small>{merchant.rows_read} rows read</small>
          </div>
        </article>
      ))}
    </section>
  );
}

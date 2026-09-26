"use client";

import { Fragment, useState } from "react";
import Link from "next/link";
import { ArrowRight, ChevronDown, Lightbulb, RefreshCw, Search } from "lucide-react";
import { BarList, ChartCard, Donut, LineChart, Meter, SERIES, Sparkline, StackedBars, StatTile } from "@/components/charts";
import { Failed, Loading } from "@/components/states";
import { money, useSelectedMerchant } from "@/lib/api";
import { BENEFIT_STATES, GAP_LABELS, gapExplanation, useShoppingInsights,
  type ComparisonMode, type ShoppingInsights, type ShoppingRequest } from "@/lib/insights";
import styles from "./insights.module.css";

type Focus = { title: string; ids: string[] } | null;

const DAY = 24 * 60 * 60 * 1000;

/** Outcome slices in a fixed order, so a colour always means the same outcome. */
const OUTCOMES = [
  { key: "Offer selected by agent", label: "Chosen, not checked out" },
  { key: "Another offer selected by agent", label: "Competitor chosen" },
  { key: "Checkout confirmed", label: "Chosen and checked out" },
  { key: "Outcome unknown", label: "Unknown" },
];

const BENEFIT_GROUPS = [
  { name: "Credited", states: ["credited"] },
  { name: "Verified, no credit", states: ["unpriced", "not_credited"] },
  { name: "Eligibility issue", states: ["eligibility_unknown", "ineligible"] },
  { name: "Not verified", states: ["expired", "unverified"] },
];

function dateTime(value: string) {
  return new Intl.DateTimeFormat("en-AU", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function shortDate(value: string | number) {
  return new Intl.DateTimeFormat("en-AU", { day: "numeric", month: "short" }).format(new Date(value));
}

function plural(count: number, word: string) {
  return `${count} ${count === 1 ? word : `${word}s`}`;
}

function percent(part: number, whole: number) {
  return whole ? `${Math.round((part / whole) * 100)}%` : "—";
}

/** Requests per day (per week past 45 days) across the selected period. */
function timeline(data: ShoppingInsights) {
  const until = new Date(data.period.until).getTime();
  const created = data.recent.map((r) => new Date(r.created_at).getTime());
  const start = data.period.since ? new Date(data.period.since).getTime() : Math.min(until, ...created);
  const spanDays = Math.max(1, Math.ceil((until - start) / DAY));
  const size = spanDays > 45 ? 7 : 1;
  const count = Math.max(1, Math.ceil(spanDays / size));
  const labels = Array.from({ length: count }, (_, i) => shortDate(start + i * size * DAY));
  const all = Array<number>(count).fill(0);
  const offers = Array<number>(count).fill(0);
  data.recent.forEach((request, i) => {
    const bucket = Math.min(count - 1, Math.max(0, Math.floor((created[i] - start) / (size * DAY))));
    all[bucket] += 1;
    if (request.has_offer) offers[bucket] += 1;
  });
  return { labels, all, offers, weekly: size === 7 };
}

function RequestDetails({ request }: { request: ShoppingRequest }) {
  const confirmed = request.checkout.status === "confirmed";
  return <div className={styles.evidence}>
    {confirmed && <p className={styles.muted}>Checkout confirmed. Not a paid sale.</p>}
    {request.gaps[0] && <div className={styles.nextAction}><Lightbulb size={17} /><span><b>{request.gaps[0].title}</b> · {gapExplanation(request.gaps[0])}</span></div>}
    <div className={styles.detailGrid}>
      <div>
        <h4>Requirements</h4>
        {request.requirements.length > 0 ? <ul className={styles.requirements}>{request.requirements.map((r, i) => <li key={i}>
          <span className={`pill ${r.satisfied ? "success" : "warning"}`}>{r.satisfied ? "Met" : "Unanswered"}</span><span>{r.text}</span>
        </li>)}</ul> : <p className={styles.muted}>Not recorded.</p>}
      </div>
      <div>
        <h4>Benefits</h4>
        {request.benefits.length ? <ul className={styles.requirements}>{request.benefits.map((b, i) => <li key={`${b.record_id}-${i}`}><span>{b.label}</span><span className="pill neutral">{BENEFIT_STATES[b.state] ?? b.state}</span></li>)}</ul> :
          <p className={styles.muted}>{request.technical.benefits_enabled === false ? "Not requested in this run." : "Not recorded."}</p>}
      </div>
    </div>
    {request.gaps.length > 0 && <><h4>Next steps</h4><ul className={styles.gapList}>{request.gaps.map((g, i) => <li key={`${g.key}-${i}`}>
      <strong>{g.title}</strong><p>{gapExplanation(g)}</p>
      {g.sku_ids?.length ? <p className={styles.muted}>Products: {g.sku_ids.slice(0, 10).join(", ")}{g.sku_ids.length > 10 ? " …" : ""}</p> : null}
      <Link href={g.href}>{g.action} <ArrowRight size={13} /></Link>
    </li>)}</ul></>}
    <details className={styles.technical}><summary>Technical details</summary>
      <dl><dt>Report ID</dt><dd><code>{request.request_id}</code></dd>
        <dt>Order ID</dt><dd>{request.checkout.order_id || "—"}</dd></dl>
      {request.requirements.map((r, i) => <p key={i}>{r.note}{r.record_id && <> · <code>{r.record_id}</code></>}</p>)}
      {request.benefits.map((b, i) => <p key={i}><code>{b.record_id}</code> · {b.reason}</p>)}
    </details>
  </div>;
}

function RequestRow({ request }: { request: ShoppingRequest }) {
  const [open, setOpen] = useState(false);
  const good = request.checkout.status === "confirmed" || request.selected === true;
  return <Fragment>
    <tr className={open ? styles.rowOpen : ""}>
      <td className={styles.nowrap}>{dateTime(request.created_at)}</td>
      <td className={styles.question}>“{request.question}”</td>
      <td>{request.product ? <><span className={styles.productName}>{request.product.title || request.product.sku_id}</span><small>{money(request.product.price)}</small></> : <span className={styles.muted}>No offer</span>}</td>
      <td><span className={`pill ${good ? "success" : "neutral"}`}>{request.outcome}</span></td>
      <td className={styles.numeric}>{request.unanswered.length || "—"}</td>
      <td className={styles.toggleCell}>
        <button type="button" className={styles.rowToggle} aria-expanded={open} onClick={() => setOpen(!open)}
          aria-label={open ? "Hide details" : "Show details"}>
          <ChevronDown size={16} style={{ transform: open ? "rotate(180deg)" : undefined }} />
        </button>
      </td>
    </tr>
    {open && <tr className={styles.detailRow}><td colSpan={6}><RequestDetails request={request} /></td></tr>}
  </Fragment>;
}

export default function ShoppingInsightsPage() {
  const merchant = useSelectedMerchant();
  return <MerchantInsights key={merchant ?? "none"} merchant={merchant} />;
}

function MerchantInsights({ merchant }: { merchant: string | null }) {
  const [days, setDays] = useState(30);
  const [mode, setMode] = useState<ComparisonMode>("enabled");
  const [focus, setFocus] = useState<Focus>(null);
  const [visible, setVisible] = useState(10);
  const { data, error, loading, reload } = useShoppingInsights(merchant, days, mode);

  function showRequests(title: string, ids: string[]) {
    setFocus({ title, ids }); setVisible(10);
    document.getElementById("shopping-requests")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }
  function resetView() { setFocus(null); setVisible(10); }

  const recent = data?.recent.filter((r) => !focus || focus.ids.includes(r.request_id)) ?? [];

  return <div className={`content ${styles.page}`}>
    <div className={`page-heading ${styles.heading}`}>
      <div><h1>Shopping insights</h1><p>What shoppers asked for, and what to improve.</p></div>
    </div>

    <div className={styles.filters}>
      <label>Period<select aria-label="Period" value={days} onChange={(e) => { setDays(Number(e.target.value)); resetView(); }}><option value={7}>Last 7 days</option><option value={30}>Last 30 days</option><option value={90}>Last 90 days</option><option value={0}>All time</option></select></label>
      <label>View<select aria-label="View" value={mode} onChange={(e) => { setMode(e.target.value as ComparisonMode); resetView(); }}><option value="enabled">With benefits</option><option value="control">Catalogue only</option><option value="all">All runs</option></select></label>
      <div className={styles.filterEnd}>
        {data && <span className={styles.updated}>As of {dateTime(data.period.until)}</span>}
        <button className={styles.refresh} disabled={loading || !merchant} onClick={reload}><RefreshCw size={15} /> {loading ? "Updating…" : "Refresh"}</button>
      </div>
    </div>

    {error && <Failed what="shopping insights" error={error} />}
    {!data && !error && <Loading what="shopping insights" />}
    {data && <Dashboard data={data} mode={mode} loading={loading} focus={focus} recent={recent} visible={visible}
      onShowRequests={showRequests} onClearFocus={resetView} onMore={() => setVisible(visible + 10)} />}
  </div>;
}

function Dashboard({ data, mode, loading, focus, recent, visible, onShowRequests, onClearFocus, onMore }: {
  data: ShoppingInsights; mode: ComparisonMode; loading: boolean; focus: Focus; recent: ShoppingRequest[]; visible: number;
  onShowRequests: (title: string, ids: string[]) => void; onClearFocus: () => void; onMore: () => void;
}) {
  const m = data.metrics;
  if (m.requests === 0) {
    return <section className={`panel ${styles.empty}`}><Search size={28} /><h2>No insights yet</h2>
      <p>Run the buyer agent against this store, then refresh.</p>
      <div><Link className="upload-button" href="/catalogue/">Review catalogue</Link><Link href="/benefits/">Add benefits <ArrowRight size={14} /></Link></div>
    </section>;
  }

  const trend = timeline(data);
  const outcomes = OUTCOMES.map((o, i) => ({
    label: o.label, color: SERIES[i], value: data.recent.filter((r) => r.outcome === o.key).length,
  }));
  const benefitRows = Object.values(data.benefits.reduce<Record<string, { label: string; values: number[] }>>((acc, b) => {
    const row = acc[b.label] ?? { label: b.label, values: BENEFIT_GROUPS.map(() => 0) };
    const group = BENEFIT_GROUPS.findIndex((g) => g.states.includes(b.state));
    if (group >= 0) row.values[group] += b.requests;
    acc[b.label] = row;
    return acc;
  }, {})).sort((a, b) => b.values.reduce((x, y) => x + y, 0) - a.values.reduce((x, y) => x + y, 0));
  const topOpportunities = data.opportunities.slice(0, 5);
  const maxOpportunity = Math.max(1, ...topOpportunities.map((o) => o.requests));

  return <div className={`${styles.dashboard} ${loading ? styles.refetching : ""}`} aria-busy={loading}>
    <section className={styles.kpis} aria-label="Summary">
      <StatTile label="Requests" value={String(m.requests)} detail={trend.weekly ? "Per week" : "Per day"}>
        <Sparkline values={trend.all} />
      </StatTile>
      <StatTile label="Offer rate" value={percent(m.with_offers, m.requests)} detail={`${m.with_offers} of ${m.requests} had your offer`}>
        <Meter value={m.requests ? m.with_offers / m.requests : 0} />
      </StatTile>
      <StatTile label="Needs answered" value={percent(m.requests - m.unanswered, m.requests)} detail={`${m.unanswered} with unanswered needs`}>
        <Meter value={m.requests ? (m.requests - m.unanswered) / m.requests : 0} />
      </StatTile>
      <StatTile label="Chosen by agent" value={m.selection_known ? percent(m.selected, m.selection_known) : "—"}
        detail={m.selection_known ? `${m.selected} of ${m.selection_known} runs` : "No selections reported"}>
        <Meter value={m.selection_known ? m.selected / m.selection_known : 0} />
      </StatTile>
    </section>

    <ChartCard className={styles.span8} title="Requests over time"
      subtitle={`${trend.weekly ? "Weekly" : "Daily"} · hover to see how many had your offer`}
      table={{ columns: [trend.weekly ? "Week of" : "Day", "Requests", "With your offer"], rows: trend.labels.map((l, i) => [l, trend.all[i], trend.offers[i]]) }}>
      <LineChart height={320} labels={trend.labels} series={[
        { name: "Requests", color: SERIES[0], values: trend.all },
        { name: "With your offer", color: SERIES[1], values: trend.offers, hidden: true },
      ]} />
    </ChartCard>

    <ChartCard className={styles.span4} title="Agent outcomes" subtitle="What the agent did after comparing"
      table={{ columns: ["Outcome", "Requests", "Share"], rows: outcomes.map((o) => [o.label, o.value, percent(o.value, m.requests)]) }}>
      <Donut slices={outcomes} centerLabel="requests" />
      <p className={styles.footnote}>Checkouts are confirmations, not paid sales.</p>
    </ChartCard>

    <ChartCard className={styles.span7} title="Next improvements" subtitle="Ranked by requests affected"
      table={{ columns: ["Issue", "Type", "Requests"], rows: data.opportunities.map((o) => [o.title, GAP_LABELS[o.kind] ?? o.kind, o.requests]) }}>
      {topOpportunities.length === 0 ? <p className={styles.muted}>No issues in this view.</p> :
        <ol className={styles.opportunityList}>{topOpportunities.map((item, i) => <li key={item.id}>
          <span className={styles.rank}>{i + 1}</span>
          <div className={styles.opportunityBody}>
            <div className={styles.opportunityTitle}><strong>{item.title}</strong><span className="pill neutral">{GAP_LABELS[item.kind] ?? item.kind}</span></div>
            <p>{gapExplanation({ kind: item.kind, reason: item.examples[0]?.reason || "" })}</p>
            <div className={styles.impactRow}>
              <span className={styles.impactTrack}><span style={{ width: `${(item.requests / maxOpportunity) * 100}%`, background: SERIES[1] }} /></span>
              <small>{plural(item.requests, "request")}</small>
            </div>
          </div>
          <div className={styles.opportunityActions}>
            <Link href={item.href}>{item.action} <ArrowRight size={13} /></Link>
            <button type="button" onClick={() => onShowRequests(item.title, item.request_ids)}>View requests</button>
          </div>
        </li>)}</ol>}
      {data.opportunities.length > 5 && <p className={styles.footnote}>{data.opportunities.length - 5} more in the table view.</p>}
    </ChartCard>

    <ChartCard className={styles.span5} title="Benefit recognition" subtitle="Agent decisions per benefit. A request can involve several."
      action={<Link href="/benefits/">Manage <ArrowRight size={13} /></Link>}
      table={{ columns: ["Benefit", ...BENEFIT_GROUPS.map((g) => g.name)], rows: benefitRows.map((r) => [r.label, ...r.values]) }}>
      {benefitRows.length === 0
        ? <div className={styles.cardEmpty}>
            <p>{mode === "control" ? "Benefits aren't requested in catalogue-only runs." : "No benefit data yet."}</p>
            {mode !== "control" && <Link href="/benefits/">Publish benefits <ArrowRight size={13} /></Link>}
          </div>
        : <StackedBars rows={benefitRows} unit="decisions" keys={BENEFIT_GROUPS.map((g, i) => ({ name: g.name, color: SERIES[i] }))} />}
    </ChartCard>

    <ChartCard className={styles.span4} title="Top categories" subtitle="Click a bar to see requests"
      table={{ columns: ["Category", "Requests"], rows: data.demand.categories.map((d) => [d.label, d.requests]) }}>
      <BarList items={data.demand.categories.map((d) => ({ label: d.label, value: d.requests, ids: d.request_ids }))} onSelect={onShowRequests} />
    </ChartCard>
    <ChartCard className={styles.span4} title="Budgets" subtitle="Price ceilings shoppers set"
      table={{ columns: ["Budget", "Requests"], rows: data.demand.budgets.map((d) => [d.label, d.requests]) }}>
      <BarList items={data.demand.budgets.map((d) => ({ label: d.label.replace("Budget ceiling: ", "Under "), value: d.requests, ids: d.request_ids }))} onSelect={onShowRequests} />
    </ChartCard>
    <ChartCard className={styles.span4} title="Specs and services" subtitle="What else shoppers asked for"
      table={{ columns: ["Need", "Requests"], rows: data.demand.needs.map((d) => [d.label, d.requests]) }}>
      <BarList items={data.demand.needs.map((d) => ({ label: d.label, value: d.requests, ids: d.request_ids }))} onSelect={onShowRequests} />
    </ChartCard>

    <section id="shopping-requests" className={`${styles.span12} ${styles.requestsCard}`} aria-labelledby="requests-title">
      <header className={styles.requestsHeader}>
        <div><h2 id="requests-title">Recent requests</h2><p>{focus ? <>Showing <strong>{focus.title}</strong> · {recent.length}</> : plural(recent.length, "request")}</p></div>
        {focus && <button type="button" className={styles.clearFocus} onClick={onClearFocus}>Show all</button>}
      </header>
      <div className={styles.tableScroll}>
        <table className={styles.requestTable}>
          <thead><tr><th>Date</th><th>Request</th><th>Your offer</th><th>Outcome</th><th className={styles.numeric}>Unanswered</th><th><span className="sr-only">Details</span></th></tr></thead>
          <tbody>{recent.slice(0, visible).map((r) => <RequestRow key={r.request_id} request={r} />)}</tbody>
        </table>
      </div>
      {visible < recent.length && <button type="button" className={styles.loadMore} onClick={onMore}>Show more ({recent.length - visible})</button>}
    </section>

    <footer className={`${styles.span12} ${styles.coverage}`}><p>{data.coverage.note}</p>
      {data.coverage.excluded_undated_or_future > 0 && <p>{plural(data.coverage.excluded_undated_or_future, "undated report")} excluded.</p>}
    </footer>
  </div>;
}

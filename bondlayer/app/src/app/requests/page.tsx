"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowRight, CheckCircle2, ChevronDown, Lightbulb, RefreshCw, Search, ShoppingBag } from "lucide-react";
import { Failed, Loading } from "@/components/states";
import { money, useSelectedMerchant } from "@/lib/api";
import { BENEFIT_STATES, GAP_LABELS, gapExplanation, useShoppingInsights,
  type ComparisonMode, type Demand, type ShoppingRequest } from "@/lib/insights";
import styles from "./insights.module.css";

type Focus = { title: string; ids: string[] } | null;

function date(value: string) {
  return new Intl.DateTimeFormat("en-AU", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function DemandList({ title, items, total, onFocus }: {
  title: string; items: Demand[]; total: number; onFocus: (title: string, ids: string[]) => void;
}) {
  return <section className={`panel ${styles.demandPanel}`}>
    <h3>{title}</h3>
    {items.length === 0 ? <p className={styles.muted}>No {title.toLowerCase()} were recorded.</p> :
      <ul className={styles.demandList}>{items.slice(0, 6).map(item => <li key={item.label}>
        <button onClick={() => onFocus(item.label, item.request_ids)}>
          <span>{item.label}</span><strong>{item.requests} <small>{item.requests === 1 ? "request" : "requests"}</small></strong>
        </button>
        <div className={styles.track} aria-hidden="true"><span style={{ width: `${Math.min(100, total ? item.requests / total * 100 : 0)}%` }} /></div>
      </li>)}</ul>}
  </section>;
}

function RequestCard({ request }: { request: ShoppingRequest }) {
  const [open, setOpen] = useState(false);
  const confirmed = request.checkout.status === "confirmed";
  return <article className={`panel ${styles.request}`} id={`request-${request.request_id}`}>
    <header className={styles.requestHeader}>
      <time dateTime={request.created_at}>{date(request.created_at)}</time>
      <span className={`pill ${confirmed || request.selected === true ? "success" : "neutral"}`}>{request.outcome}</span>
    </header>
    <h3>“{request.question}”</h3>
    <div className={styles.requestSummary}>
      <span><ShoppingBag size={15} /> {request.has_offer ? "Your store returned an offer" : "No matching offer returned"}</span>
      {request.unanswered.length > 0 && <span>{request.unanswered.length} {request.unanswered.length === 1 ? "need" : "needs"} unanswered</span>}
    </div>
    {request.product && <p className={styles.product}>{request.product.title || request.product.sku_id} <strong>{money(request.product.price)}</strong> <small>shelf price</small></p>}
    {confirmed && <p className={styles.muted}>A checkout confirmation was returned. This is not evidence of a paid sale.</p>}
    {request.gaps[0] && <div className={styles.nextAction}><Lightbulb size={17} /><span><b>{request.gaps[0].title}</b> · {gapExplanation(request.gaps[0])}</span></div>}
    <button className={styles.evidenceToggle} aria-expanded={open} onClick={() => setOpen(!open)}>
      {open ? "Hide supporting evidence" : "See supporting evidence"} <ChevronDown size={16} style={{ transform: open ? "rotate(180deg)" : undefined }} />
    </button>
    {open && <div className={styles.evidence}>
      <h4>What your offer could answer</h4>
      {request.requirements.length > 0 ? <ul className={styles.requirements}>{request.requirements.map((r, i) => <li key={i}>
        <span className={`pill ${r.satisfied ? "success" : "warning"}`}>{r.satisfied ? "Evidence available" : "Unanswered"}</span><span>{r.text}</span>
      </li>)}</ul> : <p className={styles.muted}>Detailed requirement checks were not saved for this offer.</p>}
      {request.unanswered.length > 0 && <><h4>Needs left unanswered</h4><ul>{request.unanswered.map((need, i) => <li key={i}>{need}</li>)}</ul></>}
      <h4>Benefits considered</h4>
      {request.benefits.length ? <ul className={styles.requirements}>{request.benefits.map((b, i) => <li key={`${b.record_id}-${i}`}><span>{b.label}</span><span className="pill neutral">{BENEFIT_STATES[b.state] ?? b.state}</span></li>)}</ul> :
        <p className={styles.muted}>{request.technical.benefits_enabled === false ? "Benefits were not requested in this baseline run." : "No detailed benefit decisions were saved for this offer."}</p>}
      {request.gaps.length > 0 && <><h4>What you can do next</h4><ul className={styles.gapList}>{request.gaps.map((g, i) => <li key={`${g.key}-${i}`}>
        <strong>{g.title}</strong><p>{gapExplanation(g)}</p>
        {g.sku_ids?.length ? <p className={styles.muted}>Affected products: {g.sku_ids.slice(0, 10).join(", ")}{g.sku_ids.length > 10 ? " …" : ""}</p> : null}
        <Link href={g.href}>{g.action} <ArrowRight size={13} /></Link>
      </li>)}</ul></>}
      <details className={styles.technical}><summary>Technical details</summary>
        <dl><dt>Report reference</dt><dd><code>{request.request_id}</code></dd><dt>Source</dt><dd>Saved buyer-agent comparison</dd>
          <dt>Evidence detail</dt><dd>{request.technical.evidence_version ? "Captured when the request ran" : "Older summary report"}</dd>
          <dt>Checkout reference</dt><dd>{request.checkout.order_id || "Not observed for this merchant"}</dd></dl>
        {request.requirements.map((r, i) => <p key={i}>{r.note}{r.record_id && <> · <code>{r.record_id}</code></>}</p>)}
        {request.benefits.map((b, i) => <p key={i}><code>{b.record_id}</code> · {b.reason}</p>)}
      </details>
    </div>}
  </article>;
}

export default function ShoppingInsightsPage() {
  const merchant = useSelectedMerchant();
  return <MerchantInsights key={merchant ?? "none"} merchant={merchant} />;
}

function MerchantInsights({ merchant }: { merchant: string | null }) {
  const [days, setDays] = useState(30);
  const [mode, setMode] = useState<ComparisonMode>("enabled");
  const [focus, setFocus] = useState<Focus>(null);
  const [visible, setVisible] = useState(8);
  const { data, error, loading, reload } = useShoppingInsights(merchant, days, mode);
  function showEvidence(title: string, ids: string[]) {
    setFocus({ title, ids }); setVisible(8);
    document.getElementById("shopping-requests")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }
  const recent = data?.recent.filter(r => !focus || focus.ids.includes(r.request_id)) ?? [];

  return <div className={`content ${styles.page}`}>
    <div className={`page-heading ${styles.heading}`}><div><p className={styles.eyebrow}>Understand demand. Improve your offer.</p><h1>Shopping insights</h1>
      <p>What shoppers asked for, how {data?.display_name || "your store"} responded, and what to improve next.</p></div>
      <button className={styles.refresh} disabled={loading || !merchant} onClick={reload}><RefreshCw size={15} /> {loading ? "Updating…" : "Refresh insights"}</button>
    </div>
    <div className={styles.filters}>
      <label>Reporting period<select aria-label="Reporting period" value={days} onChange={e => { setDays(Number(e.target.value)); setFocus(null); setVisible(8); }}><option value={7}>Last 7 days</option><option value={30}>Last 30 days</option><option value={90}>Last 90 days</option><option value={0}>All retained history</option></select></label>
      <label>Comparison view<select aria-label="Comparison view" value={mode} onChange={e => { setMode(e.target.value as ComparisonMode); setFocus(null); setVisible(8); }}><option value="enabled">Benefits enabled</option><option value="control">Baseline — catalogue only</option><option value="all">All comparison runs</option></select></label>
      {data && <span className={styles.updated}>As of {date(data.period.until)}</span>}
    </div>
    {error && <Failed what="shopping insights" error={error} />}
    {!data && !error && <Loading what="shopping insights" />}
    {data && <>
      <section className={`metrics ${styles.metrics}`} aria-label="Merchant insight summary">
        <article className="metric"><p>Shopping requests observed</p><strong>{data.metrics.requests}</strong><small>Saved comparison runs for this store</small></article>
        <article className="metric"><p>Requests with offers</p><strong>{data.metrics.with_offers}</strong><small>Your store returned at least one candidate</small></article>
        <article className="metric"><p>Requests with unanswered needs</p><strong>{data.metrics.unanswered}</strong><small>Some requirements lacked a satisfied answer</small></article>
        <article className="metric"><p>Checkout confirmations</p><strong>{data.metrics.checkout_confirmations}</strong><small>Confirmed responses, not paid sales</small></article>
      </section>
      <p className={styles.selection}>{data.metrics.selection_known > 0 ? <><CheckCircle2 size={15} /> Your offer was selected in <strong>{data.metrics.selected} of {data.metrics.selection_known}</strong> runs with an agent-reported selection.</> : "No agent-reported selections in this view. Purchase outcomes are unknown."}</p>
      {data.metrics.requests === 0 ? <section className={`panel ${styles.empty}`}><Search size={28} /><h2>No shopping insights yet</h2>
        <p>There are no saved comparisons for this merchant in the selected period and view. Publish your catalogue, run a buyer-agent comparison, then refresh insights.</p>
        <div><Link className="upload-button" href="/catalogue/">Review catalogue</Link><Link href="/benefits/">Prepare your benefits <ArrowRight size={14} /></Link></div>
      </section> : <>
        <section aria-labelledby="opportunities-title"><div className={styles.sectionHeading}><div><h2 id="opportunities-title">Your next improvements</h2><p>Prioritised by how many observed requests contained each issue. Open the evidence before making changes.</p></div><Lightbulb size={21} /></div>
          {data.opportunities.length === 0 ? <div className={`panel ${styles.noIssues}`}><CheckCircle2 size={20} /><p>No actionable issues were recorded in this view. This does not establish that every shopping need was met.</p></div> :
            <div className={styles.opportunities}>{data.opportunities.slice(0, 3).map(item => <article className={`panel ${styles.opportunity}`} key={item.id}>
              <span className="pill neutral">{GAP_LABELS[item.kind] ?? item.kind}</span><h3>{item.title}</h3>
              <p>{gapExplanation({ kind: item.kind, reason: item.examples[0]?.reason || "" })}</p>
              <strong className={styles.impact}>{item.requests} {item.requests === 1 ? "request" : "requests"} observed</strong>
              <footer><Link href={item.href}>{item.action} <ArrowRight size={14} /></Link><button onClick={() => showEvidence(item.title, item.request_ids)}>View evidence</button></footer>
            </article>)}</div>}
          {data.opportunities.length > 3 && <details className={styles.moreIssues}><summary>{data.opportunities.length - 3} more recorded opportunities</summary>{data.opportunities.slice(3).map(item => <button key={item.id} onClick={() => showEvidence(item.title, item.request_ids)}>{item.title}<span>{item.requests} requests →</span></button>)}</details>}
        </section>
        <section aria-labelledby="demand-title"><div className={styles.sectionHeading}><div><h2 id="demand-title">What shoppers are looking for</h2><p>Based on the needs recorded in these comparisons. A request can mention several needs.</p></div></div>
          <div className={styles.demandGrid}><DemandList title="Product categories" items={data.demand.categories} total={data.metrics.requests} onFocus={showEvidence} /><DemandList title="Budget ceilings" items={data.demand.budgets} total={data.metrics.requests} onFocus={showEvidence} /><DemandList title="Specifications and services" items={data.demand.needs} total={data.metrics.requests} onFocus={showEvidence} /></div>
        </section>
        <section className={`panel ${styles.benefits}`} aria-labelledby="benefits-title"><div className={styles.sectionHeading}><div><h2 id="benefits-title">Are your benefits being understood?</h2><p>Each count is the number of requests recording that decision for your offer.</p></div><Link href="/benefits/">Manage benefits <ArrowRight size={14} /></Link></div>
          {data.benefits.length ? <div className={styles.benefitRows}>{data.benefits.map(b => <button key={`${b.label}:${b.state}`} onClick={() => showEvidence(`${b.label}: ${b.state_label}`, b.request_ids)}><strong>{b.label}</strong><span className="pill neutral">{b.state_label}</span><span>{b.requests} {b.requests === 1 ? "request" : "requests"} <ArrowRight size={13} /></span></button>)}</div> : <p className={styles.muted}>{mode === "control" ? "Baseline comparisons do not request benefit records." : "No detailed benefit decisions were saved in this view. Older reports may not include this evidence."}</p>}
        </section>
        <section id="shopping-requests" aria-labelledby="requests-title" className={styles.recent}><div className={styles.sectionHeading}><div><h2 id="requests-title">Recent shopping opportunities</h2><p>What your store could offer and what the agent reported afterwards.</p></div></div>
          {focus && <div className={styles.focus}><span>Evidence for <strong>{focus.title}</strong> · {recent.length} requests</span><button onClick={() => { setFocus(null); setVisible(8); }}>Show all requests</button></div>}
          {recent.slice(0, visible).map(r => <RequestCard key={r.request_id} request={r} />)}
          {visible < recent.length && <button className={styles.loadMore} onClick={() => setVisible(visible + 8)}>Show more requests ({recent.length - visible} remaining)</button>}
        </section>
      </>}
      <footer className={styles.coverage}><strong>How to read these insights</strong><p>{data.coverage.note}</p><p>Source: {data.coverage.source}, from up to {data.coverage.retained_report_limit} retained runs. {data.metrics.detailed_reports} of {data.metrics.requests} reports include detailed evidence captured at the time.</p>
        {data.coverage.excluded_undated_or_future > 0 && <p>{data.coverage.excluded_undated_or_future} reports with missing or future dates were excluded.</p>}
      </footer>
    </>}
  </div>;
}

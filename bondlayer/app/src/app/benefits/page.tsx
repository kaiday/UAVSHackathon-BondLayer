"use client";

import { useEffect, useState } from "react";
import { humanise, useSelectedMerchant } from "@/lib/api";
import { ShieldCheck, Truck, RotateCcw, Wrench, Gift, ArrowLeftRight, FileText, Upload, ChevronDown } from "lucide-react";
import styles from "./page.module.css";

const benefitIcons = { warranty: ShieldCheck, delivery: Truck, free_returns: RotateCcw, repairability: Wrench, points_earn: Gift, trade_in_credit: ArrowLeftRight };

type RecordData = { record_id: string; benefit_type: string; fact: Record<string, string | number>; conditions: string[]; source_span: string; value_ceiling_aud: string | number | null };
type Draft = { draft_id: string; status: string; record: RecordData; section: string };
type PolicyState = { merchant: string; drafts: Draft[]; published_records: { record: RecordData; signed: boolean }[] };

async function request(path: string, options?: RequestInit) {
  const response = await fetch(path, options);
  const body = await response.json();
  if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : `Request failed (${response.status}).`);
  return body;
}

function DraftCard({ draft, merchant, reload }: { draft: Draft; merchant: string; reload: () => Promise<void> }) {
  const [facts, setFacts] = useState(draft.record.fact);
  const [conditions, setConditions] = useState(draft.record.conditions.join("\n"));
  const [ceiling, setCeiling] = useState(String(draft.record.value_ceiling_aud ?? ""));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pending = draft.status === "pending";
  const unpriced = ["repairability", "durability", "sustainability", "ethical_sourcing"].includes(draft.record.benefit_type);
  const Icon = benefitIcons[draft.record.benefit_type as keyof typeof benefitIcons] ?? FileText;

  async function act(decision: "save" | "approve" | "reject") {
    setBusy(true); setError(null);
    const path = `/onboard/policies/${encodeURIComponent(merchant)}/drafts/${encodeURIComponent(draft.draft_id)}`;
    try {
      if (decision !== "reject") await request(path, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({
        fact: facts, conditions: conditions.split("\n").map(c => c.trim()).filter(Boolean), value_ceiling_aud: unpriced || !ceiling ? null : ceiling,
      }) });
      if (decision !== "save") await request(`${path}/${decision}`, { method: "POST" });
      await reload();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Couldn't update draft."); }
    finally { setBusy(false); }
  }

  return <article className={styles.card}>
    <div className={styles.cardTop}><span className={styles.icon}><Icon size={20} strokeWidth={1.7} /></span><span className={`${styles.status} ${draft.status === "approved" ? styles.approved : draft.status === "rejected" ? styles.rejected : styles.pending}`}>{humanise(draft.status)}</span></div>
    <h3>{humanise(draft.record.benefit_type)}</h3>
    <p className={styles.source}>{draft.section}</p>
    <dl className={styles.facts}>{Object.entries(draft.record.fact).map(([key, value]) => <div key={key}><dt>{humanise(key)}</dt><dd>{String(value)}</dd></div>)}</dl>
    <p className={styles.note}>Subject to the policy’s eligibility and conditions.</p>
    <details className={styles.review}>
    <summary>{pending ? "Review & edit" : "View policy details"}<ChevronDown size={16} /></summary>
    <div className={styles.reviewBody}>
    <h4>Original policy</h4><blockquote className={styles.quote}>{draft.record.source_span}</blockquote>
    <div className={styles.fields}>{Object.entries(facts).map(([key, value]) => <label key={key}><span>{humanise(key)}</span><input disabled={!pending || busy} value={value} onChange={e => setFacts({ ...facts, [key]: typeof value === "number" && e.target.value !== "" ? Number(e.target.value) : e.target.value })} /></label>)}</div>
    <label className={styles.field}><span>Conditions (one per line)</span><textarea disabled={!pending || busy} value={conditions} onChange={e => setConditions(e.target.value)} rows={5} /></label>
    {!unpriced && <label className={styles.field}><span>Max value (AUD, optional)</span><input type="number" min="0" step="0.01" value={ceiling} disabled={!pending || busy} onChange={e => setCeiling(e.target.value)} /></label>}
    <p className="state-note">{unpriced ? "Published without a dollar value." : "Leave blank to publish without a dollar value."}</p>
    {error && <p className="state-error" role="alert">{error}</p>}
    {pending && <div className={styles.actions}><button className={styles.secondary} disabled={busy} onClick={() => act("save")}>Save draft</button><button className="upload-button" disabled={busy} onClick={() => act("approve")}>Approve and sign</button><button className={styles.reject} disabled={busy} onClick={() => act("reject")}>Reject</button></div>}
    </div></details>
  </article>;
}

export default function BenefitsPage() {
  const merchant = useSelectedMerchant();
  return <MerchantBenefits key={merchant ?? "none"} merchant={merchant} />;
}

function MerchantBenefits({ merchant }: { merchant: string | null }) {
  const [state, setState] = useState<PolicyState | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  async function reload() { if (merchant) setState(await request(`/onboard/policies/${encodeURIComponent(merchant)}`)); }
  useEffect(() => {
    let active = true;
    if (merchant) request(`/onboard/policies/${encodeURIComponent(merchant)}`).then(body => { if (active) setState(body); }).catch(cause => { if (active) setError(cause.message); });
    return () => { active = false; };
  }, [merchant]);

  async function upload(file: File) {
    if (!merchant) return;
    setBusy(true); setError(null); setMessage("");
    const form = new FormData(); form.append("file", file);
    try {
      const body = await request(`/onboard/policies/${encodeURIComponent(merchant)}`, { method: "POST", body: form });
      setState(body); setMessage(`${body.drafts.length} drafts found. Review them below.`);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Upload failed."); }
    finally { setBusy(false); }
  }
  async function publish() {
    if (!merchant) return;
    setBusy(true); setError(null);
    try { const body = await request(`/onboard/policies/${encodeURIComponent(merchant)}/publish`, { method: "POST" }); await reload(); setMessage(`${body.published} benefits published.`); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Publish failed."); }
    finally { setBusy(false); }
  }

  return <div className="content">
    <section className={styles.upload}>
      <span className={styles.icon}><FileText size={22} /></span><div className={styles.uploadCopy}><h2>Store policies</h2>
      <p>Upload your terms, review each benefit, then publish.</p>
      <p className={styles.note}>PDF, TXT or Markdown · up to 10 MB. Replaces drafts, not live benefits. AI mode sends text to OpenAI; offline mode uses the bundled demo policy.</p></div>
      <label className="upload-button"><Upload size={16} /><input type="file" accept=".pdf,.txt,.md" disabled={busy || !merchant} onChange={e => { const file = e.target.files?.[0]; if (file) void upload(file); e.target.value = ""; }} />{busy ? "Processing…" : "Upload policy"}</label>
    </section>
    {error && <p className="state-error" role="alert">{error}</p>}{message && <p className="state-note" role="status">{message}</p>}
    {state && merchant && <>
      <div className={styles.sectionHeading}><h2>Policy drafts <span>{state.drafts.length}</span></h2><p>Review original terms before approving.</p></div>
      {state.drafts.length === 0 && <p className={styles.empty}>Upload a policy to create benefit cards.</p>}
      <div className={styles.grid}>{state.drafts.map(draft => <DraftCard key={`${merchant}:${draft.draft_id}:${draft.status}`} draft={draft} merchant={merchant} reload={reload} />)}</div>
      {state.drafts.length > 0 && <section className={styles.publish}><div><h3>Ready to go live?</h3><p>{state.drafts.filter(d => d.status === "approved").length} approved · only approved drafts will be published.</p></div><button className="upload-button" disabled={busy || !state.drafts.some(d => d.status === "approved")} onClick={publish}>Publish approved</button></section>}
      <div className={styles.sectionHeading}><h2>Published benefits <span>{state.published_records.length}</span></h2></div>
      {state.published_records.length === 0 && <p className={styles.empty}>No published benefits yet. Approved drafts stay private until you publish.</p>}
      <div className={styles.grid}>{state.published_records.map(({ record, signed }) => <article className={styles.card} key={record.record_id}><div className={styles.cardTop}><span className={styles.icon}><ShieldCheck size={20} /></span><span className={`${styles.status} ${styles.approved}`}>{signed ? "Signed" : "Unsigned"}</span></div><h3>{humanise(record.benefit_type)}</h3><details className={styles.review}><summary>View published terms<ChevronDown size={16} /></summary><blockquote className={styles.quote}>{record.source_span}</blockquote><small className={styles.recordId}>{record.record_id}</small></details></article>)}</div>
    </>}
  </div>;
}

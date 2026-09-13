"use client";

import { useEffect, useState } from "react";
import { humanise, useSelectedMerchant } from "@/lib/api";

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

  async function act(decision: "save" | "approve" | "reject") {
    setBusy(true); setError(null);
    const path = `/onboard/policies/${encodeURIComponent(merchant)}/drafts/${encodeURIComponent(draft.draft_id)}`;
    try {
      if (decision !== "reject") await request(path, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({
        fact: facts, conditions: conditions.split("\n").map(c => c.trim()).filter(Boolean), value_ceiling_aud: unpriced || !ceiling ? null : ceiling,
      }) });
      if (decision !== "save") await request(`${path}/${decision}`, { method: "POST" });
      await reload();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not update draft."); }
    finally { setBusy(false); }
  }

  return <article className="panel" style={{ padding: 20, marginBottom: 16 }}>
    <div className="panel-heading"><h3>{humanise(draft.record.benefit_type)}</h3><span className="pill neutral">{draft.status}</span></div>
    <p>Source: {draft.section}</p><blockquote style={{ whiteSpace: "pre-wrap", margin: "12px 0" }}>{draft.record.source_span}</blockquote>
    <div className="setting-list">{Object.entries(facts).map(([key, value]) => <label key={key}><span>{humanise(key)}</span><input disabled={!pending || busy} value={value} onChange={e => setFacts({ ...facts, [key]: typeof value === "number" && e.target.value !== "" ? Number(e.target.value) : e.target.value })} /></label>)}</div>
    <label style={{ display: "block", marginTop: 12 }}>Conditions (one per line)<textarea disabled={!pending || busy} value={conditions} onChange={e => setConditions(e.target.value)} rows={3} style={{ width: "100%" }} /></label>
    {!unpriced && <label style={{ display: "block", margin: "12px 0" }}>Your maximum indicative benefit value (AUD, optional) <input type="number" min="0" step="0.01" value={ceiling} disabled={!pending || busy} onChange={e => setCeiling(e.target.value)} /></label>}
    <p className="state-note">{unpriced ? "This values claim is never converted into dollars." : "Leaving the value blank publishes a factual benefit with no monetary credit. The shopper's own valuation also caps any credit."}</p>
    {error && <p className="state-error" role="alert">{error}</p>}
    {pending && <div style={{ display: "flex", gap: 12 }}><button className="upload-button" disabled={busy} onClick={() => act("save")}>Save draft</button><button className="upload-button" disabled={busy} onClick={() => act("approve")}>Approve and sign</button><button className="pill neutral" disabled={busy} onClick={() => act("reject")}>Reject</button></div>}
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
      setState(body); setMessage(`OpenAI ${body.ai.model} extracted ${body.drafts.length} drafts. Response: ${body.ai.response_id}`);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Policy extraction failed."); }
    finally { setBusy(false); }
  }
  async function publish() {
    if (!merchant) return;
    setBusy(true); setError(null);
    try { const body = await request(`/onboard/policies/${encodeURIComponent(merchant)}/publish`, { method: "POST" }); await reload(); setMessage(`${body.published} approved benefit records published to your catalogue.`); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Publication failed."); }
    finally { setBusy(false); }
  }

  return <div className="content">
    <div className="page-heading"><div><h1>Policies and benefit records</h1><p>Upload your actual terms. OpenAI extracts drafts; you review, sign and publish them.</p></div></div>
    <section className="panel" style={{ padding: 20, marginBottom: 20 }}>
      <h2>Upload a combined policy document</h2>
      <p>PDF with selectable text, TXT or Markdown; up to 10 MB and 60,000 extracted characters. Include returns, warranty, delivery and loyalty terms as relevant.</p>
      <p className="state-note">A new upload replaces the draft set. Existing published benefits stay live until you publish the reviewed replacement. Policy text is sent to OpenAI for extraction.</p>
      <label className="upload-button"><input type="file" accept=".pdf,.txt,.md" disabled={busy || !merchant} onChange={e => { const file = e.target.files?.[0]; if (file) void upload(file); e.target.value = ""; }} />{busy ? "Processing…" : "Upload policy"}</label>
    </section>
    {error && <p className="state-error" role="alert">{error}</p>}{message && <p className="state-note" role="status">{message}</p>}
    {state && merchant && <>
      <h2>Review drafts ({state.drafts.length})</h2>
      {state.drafts.length === 0 && <p>No drafts yet. Upload a policy to extract its actual benefits.</p>}
      {state.drafts.map(draft => <DraftCard key={`${merchant}:${draft.draft_id}:${draft.status}`} draft={draft} merchant={merchant} reload={reload} />)}
      {state.drafts.length > 0 && <section className="panel" style={{ padding: 20, marginBottom: 20 }}><p>Publishing replaces the live set with approved records only; pending and rejected drafts are excluded.</p><button className="upload-button" disabled={busy || !state.drafts.some(d => d.status === "approved")} onClick={publish}>Publish approved benefits</button></section>}
      <h2>Published records ({state.published_records.length})</h2>
      {state.published_records.map(({ record, signed }) => <article className="panel" style={{ padding: 16, marginBottom: 12 }} key={record.record_id}><strong>{humanise(record.benefit_type)} · {signed ? "Signed" : "Unsigned"}</strong><p>{record.source_span}</p><small>{record.record_id}</small></article>)}
    </>}
  </div>;
}

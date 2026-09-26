"use client";

import { FormEvent, useEffect, useState } from "react";
import { refreshMerchants, useMerchants, useSelectedMerchant } from "@/lib/api";

type AIStatus = { mode: string; model: string; configured: boolean; live_verified: boolean; ai?: { response_id: string } };

function ProfileForm({ merchant, name: initialName, website }: { merchant: string; name: string; website: string }) {
  const [name, setName] = useState(initialName);
  const [domain, setDomain] = useState(website);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  async function save(event: FormEvent) {
    event.preventDefault(); setBusy(true); setMessage("");
    try {
      const response = await fetch(`/onboard/merchants/${encodeURIComponent(merchant)}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ display_name: name, domain }) });
      const body = await response.json();
      if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Couldn't save profile.");
      setMessage("Saved."); refreshMerchants();
    } catch (cause) { setMessage(cause instanceof Error ? cause.message : "Couldn't save profile."); }
    finally { setBusy(false); }
  }
  return <form className="setting-list" onSubmit={save}>
    <label><span>Business name</span><input required maxLength={120} value={name} onChange={e => setName(e.target.value)} /></label>
    <label><span>Website</span><input value={domain} onChange={e => setDomain(e.target.value)} /></label>
    <button className="upload-button" disabled={busy}>{busy ? "Saving…" : "Save profile"}</button>
    {message && <p role="status">{message}</p>}
  </form>;
}

export default function SettingsPage() {
  const merchant = useSelectedMerchant();
  const { data: merchants } = useMerchants();
  const profile = merchants?.find(entry => entry.merchant === merchant);
  const [status, setStatus] = useState<AIStatus | null>(null);
  const [error, setError] = useState("");
  const [checking, setChecking] = useState(false);
  useEffect(() => { fetch("/onboard/ai").then(r => r.json()).then(setStatus).catch(() => setError("Couldn't load AI status.")); }, []);
  async function check() {
    setChecking(true); setError("");
    try {
      const response = await fetch("/onboard/ai/check", { method: "POST" }); const body = await response.json();
      if (!response.ok) throw new Error(body.detail ?? "Connection test failed.");
      setStatus(body);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Connection test failed."); }
    finally { setChecking(false); }
  }
  return <div className="content">
    <div className="page-heading"><div><h1>Settings</h1></div></div>
    <div className="settings-grid">
      <section className="panel" style={{ padding: 20 }}><h2>Merchant profile</h2>{profile && merchant && <ProfileForm key={merchant} merchant={merchant} name={profile.display_name} website={profile.domain} />}</section>
      <section className="panel" style={{ padding: 20 }}><h2>OpenAI connection</h2>
        {status && <><p>Mode: {status.mode} · Model: {status.model}</p><p>{status.live_verified ? "Connected" : status.configured ? "Key set. Test to confirm." : "No API key. Set OPENAI_API_KEY on the server and restart."}</p>{status.ai && <code>{status.ai.response_id}</code>}</>}
        <button className="upload-button" disabled={checking} onClick={check}>{checking ? "Testing…" : "Test OpenAI connection"}</button>
        {error && <p className="state-error" role="alert">{error}</p>}
      </section>
      <section className="panel" style={{ padding: 20 }}><h2>Agent access</h2>{merchant && <div className="setting-list"><a href={`/${merchant}/.well-known/ucp`}>UCP profile</a><a href={`/${merchant}/ucp/catalog/search`}>Catalogue search</a><a href={`/onboard/report/${merchant}`}>Readiness report</a></div>}</section>
    </div>
  </div>;
}

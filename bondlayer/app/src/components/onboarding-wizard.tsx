"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { Check, Upload } from "lucide-react";
import { refreshMerchants, setMerchant, uploadCatalogue, type CatalogueUpload } from "@/lib/api";
import styles from "./onboarding-wizard.module.css";

const STEPS = ["Business details", "Upload catalogue", "Review and publish"];

export function OnboardingWizard() {
  const [step, setStep] = useState(0);
  const [name, setName] = useState("");
  const [merchant, setId] = useState("");
  const [domain, setDomain] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<CatalogueUpload | null>(null);
  const [published, setPublished] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function send(publish: boolean) {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const result = await uploadCatalogue(file, {
        merchant, displayName: name.trim(), domain: domain.trim(), preview: !publish, create: true,
      });
      setPreview(result);
      if (publish) {
        setMerchant(result.merchant);
        refreshMerchants();
        setPublished(true);
      } else setStep(2);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not upload catalogue. Please retry.");
    } finally { setBusy(false); }
  }

  function details(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setStep(1);
  }

  if (published && preview) return (
    <section className={styles.complete}>
      <span><Check size={27} /></span><p>Merchant published</p>
      <h1>{preview.display_name} is ready to browse.</h1>
      <div>{preview.report.skus} products saved. Readiness: {preview.report.readiness}%.</div>
      <p className="state-note">Your catalogue and business details are saved on the server and will load again after a restart.</p>
      <Link href="/catalogue/">Open your catalogue</Link>
    </section>
  );

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <Link className={styles.brand} href="/"><span>B</span>BondLayer</Link>
        <div><p>Merchant onboarding</p><h1>Add your business</h1></div>
        <aside><Link href="/">Back to console</Link></aside>
      </header>
      <div className={styles.layout}>
        <nav className={styles.steps} aria-label="Onboarding steps">
          {STEPS.map((label, i) => <button key={label} disabled={busy || i > step} className={i === step ? styles.active : i < step ? styles.done : ""} onClick={() => { setStep(i); setError(null); }}><i>{i < step ? <Check size={13} /> : i + 1}</i><span>{label}</span></button>)}
        </nav>
        <section className={styles.card}>
          {error && <p className="state-error" role="alert">{error}</p>}
          {step === 0 && <form className={styles.stage} onSubmit={details}>
            <p>Step 1 of 3</p><h2>Your business details</h2>
            <div>Start with your own business and product export. Your merchant becomes available after you review and publish the catalogue.</div>
            <div className={styles.form}>
              <label>Business name<input required maxLength={120} value={name} onChange={e => setName(e.target.value)} /></label>
              <label>Merchant ID<input required pattern="[a-z0-9][a-z0-9_-]{0,63}" title="Lowercase letters, numbers, hyphens and underscores" value={merchant} onChange={e => setId(e.target.value.toLowerCase())} /><small>Used in your API URL. Use the merchant value in your CSV, if it has one.</small></label>
              <label>Business website (optional)<input value={domain} placeholder="Your business domain" onChange={e => setDomain(e.target.value)} /></label>
            </div>
            <footer className={styles.footer}><span /><button type="submit">Continue to catalogue</button></footer>
          </form>}
          {step === 1 && <section className={styles.stage}>
            <p>Step 2 of 3</p><h2>Upload your product catalogue</h2>
            <div>UTF-8 CSV, up to 10 MB. Required columns: <code>sku, title, category, price</code>. Prices are in AUD. The merchant column is optional; if present, it must include <strong>{merchant}</strong>.</div>
            <p className="state-note">Optional: currency, brand, stock, ram, storage, weight_kg and other product attributes.</p>
            <a href="/onboard/catalog/template" download>Download empty CSV template</a>
            <label className={styles.filePicker}>
              <input aria-label="Upload product catalogue" type="file" accept=".csv,text/csv" disabled={busy} onChange={e => { setFile(e.target.files?.[0] ?? null); setPreview(null); setError(null); }} />
              <span className={styles.uploadIcon}><Upload size={18} /></span>
              <span><strong>{file?.name ?? "Choose your CSV"}</strong><small>{file ? "Selected — validate to preview" : "Only your uploaded products will be published"}</small></span>
            </label>
            <footer className={styles.footer}><button className={styles.quiet} disabled={busy} onClick={() => setStep(0)}>Back</button><button disabled={busy || !file} onClick={() => send(false)}>{busy ? "Validating…" : "Validate catalogue"}</button></footer>
          </section>}
          {step === 2 && preview && <section className={styles.stage}>
            <p>Step 3 of 3</p><h2>Review {name}</h2>
            <div>This preview was calculated from <strong>{file?.name}</strong>. Publishing saves the business profile and catalogue and makes these products available to agents.</div>
            <div className={styles.readinessSummary}>
              <article><strong>{preview.report.skus}</strong><small>Products accepted</small></article>
              <article><strong>{preview.report.rows_rejected}</strong><small>Rows rejected</small></article>
              <article><strong>{preview.report.readiness}%</strong><small>Catalogue readiness</small></article>
            </div>
            {preview.report.rows_rejected > 0 && <p className="state-note">Rejected rows will not be served. Go back to choose a corrected file, or publish the accepted products.</p>}
            <div className="table-wrap"><table><thead><tr><th>Row</th><th>SKU</th><th>Diagnostic</th></tr></thead><tbody>{preview.report.diagnostics.slice(0, 12).map((d, i) => <tr key={i}><td>{d.row}</td><td>{d.sku_id}</td><td>{d.message}</td></tr>)}</tbody></table></div>
            <p className="state-note">This publishes catalogue data. Benefits will only appear when you publish your own benefit records.</p>
            <footer className={styles.footer}><button className={styles.quiet} disabled={busy} onClick={() => setStep(1)}>Back</button><button disabled={busy} onClick={() => send(true)}>{busy ? "Publishing…" : "Publish merchant"}</button></footer>
          </section>}
        </section>
      </div>
    </main>
  );
}

"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { Check, Upload } from "lucide-react";
import { refreshMerchants, setMerchant, uploadCatalogue, useMerchants, type CatalogueUpload } from "@/lib/api";
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
  // The console sends a visitor with no merchants straight back here, so the
  // link only appears once there is a console to go back to.
  const { data: merchants } = useMerchants();
  const hasConsole = (merchants?.length ?? 0) > 0;

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
      setError(cause instanceof Error ? cause.message : "Upload failed. Try again.");
    } finally { setBusy(false); }
  }

  function details(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setStep(1);
  }

  if (published && preview) return (
    <section className={styles.complete}>
      <span><Check size={27} /></span><p>Published</p>
      <h1>{preview.display_name} is live.</h1>
      <div>{preview.report.skus} products · {preview.report.readiness}% ready</div>
      <Link href="/catalogue/">Open catalogue</Link>
      <Link href="/benefits/">Next: add benefits</Link>
    </section>
  );

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <Link className={styles.brand} href="/"><span>B</span>BondLayer</Link>
        <div><p>Merchant onboarding</p><h1>Add your business</h1></div>
        <aside>{hasConsole && <Link href="/">Back to console</Link>}</aside>
      </header>
      <div className={styles.layout}>
        <nav className={styles.steps} aria-label="Onboarding steps">
          {STEPS.map((label, i) => <button key={label} disabled={busy || i > step} className={i === step ? styles.active : i < step ? styles.done : ""} onClick={() => { setStep(i); setError(null); }}><i>{i < step ? <Check size={13} /> : i + 1}</i><span>{label}</span></button>)}
        </nav>
        <section className={styles.card}>
          {error && <p className="state-error" role="alert">{error}</p>}
          {step === 0 && <form className={styles.stage} onSubmit={details}>
            <p>Step 1 of 3</p><h2>Business details</h2>
            <div className={styles.form}>
              <label>Business name<input required maxLength={120} value={name} onChange={e => setName(e.target.value)} /></label>
              <label>Merchant ID<input required pattern="[a-z0-9][a-z0-9_-]{0,63}" title="Lowercase letters, numbers, hyphens and underscores" value={merchant} onChange={e => setId(e.target.value.toLowerCase())} /><small>Lowercase, used in your URLs. Must match the CSV merchant column, if you have one.</small></label>
              <label>Website (optional)<input value={domain} placeholder="example.com.au" onChange={e => setDomain(e.target.value)} /></label>
            </div>
            <footer className={styles.footer}><span /><button type="submit">Continue</button></footer>
          </form>}
          {step === 1 && <section className={styles.stage}>
            <p>Step 2 of 3</p><h2>Upload catalogue</h2>
            <div>CSV, up to 10 MB, prices in AUD. Required columns: <code>sku, title, category, price</code>.</div>
            <p className="state-note">Optional: brand, stock, ram, storage, weight_kg.</p>
            <a href="/onboard/catalog/template" download>Download template</a>
            <label className={styles.filePicker}>
              <input aria-label="Upload product catalogue" type="file" accept=".csv,text/csv" disabled={busy} onChange={e => { setFile(e.target.files?.[0] ?? null); setPreview(null); setError(null); }} />
              <span className={styles.uploadIcon}><Upload size={18} /></span>
              <span><strong>{file?.name ?? "Choose CSV"}</strong><small>{file ? "Ready to validate" : "CSV files only"}</small></span>
            </label>
            <footer className={styles.footer}><button className={styles.quiet} disabled={busy} onClick={() => setStep(0)}>Back</button><button disabled={busy || !file} onClick={() => send(false)}>{busy ? "Validating…" : "Validate"}</button></footer>
          </section>}
          {step === 2 && preview && <section className={styles.stage}>
            <p>Step 3 of 3</p><h2>Review {name}</h2>
            <div>Publishing makes these products visible to agents.</div>
            <div className={styles.readinessSummary}>
              <article><strong>{preview.report.skus}</strong><small>Products accepted</small></article>
              <article><strong>{preview.report.rows_rejected}</strong><small>Rows rejected</small></article>
              <article><strong>{preview.report.readiness}%</strong><small>Readiness</small></article>
            </div>
            {preview.report.rows_rejected > 0 && <p className="state-note">Rejected rows won&apos;t be published. Fix the file, or publish the rest.</p>}
            <div className="table-wrap"><table><thead><tr><th>Row</th><th>SKU</th><th>What to do</th></tr></thead><tbody>{preview.report.diagnostics.slice(0, 12).map((d, i) => <tr key={i}><td>{d.row}</td><td>{d.sku_id}</td><td>{d.message}</td></tr>)}</tbody></table></div>
            <footer className={styles.footer}><button className={styles.quiet} disabled={busy} onClick={() => setStep(1)}>Back</button><button disabled={busy} onClick={() => send(true)}>{busy ? "Publishing…" : "Publish"}</button></footer>
          </section>}
        </section>
      </div>
    </main>
  );
}

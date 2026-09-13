"use client";

import { ChangeEvent, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Check, ChevronRight, CircleAlert, Clock3, Upload } from "lucide-react";
import styles from "./onboarding-wizard.module.css";

type Step = "welcome" | "profile" | "files" | "data" | "catalogue" | "readiness" | "policies" | "membership" | "review";

const STEPS: { id: Step; label: string }[] = [
  { id: "welcome", label: "Welcome" }, { id: "profile", label: "Business profile" },
  { id: "files", label: "Business files" }, { id: "data", label: "Data import" },
  { id: "catalogue", label: "Catalogue" }, { id: "readiness", label: "Catalogue review" }, { id: "policies", label: "Policies" },
  { id: "membership", label: "Membership" }, { id: "review", label: "Review" },
];

type Draft = { business: string; registration: string; contact: string; verification: string; data: string; catalogue: string; policies: Record<string, string>; membershipOffer: string; accepted: boolean; submitted: boolean };
const emptyDraft: Draft = { business: "", registration: "", contact: "", verification: "", data: "", catalogue: "", policies: {}, membershipOffer: "", accepted: false, submitted: false };
const draftKey = "bondlayer-onboarding-draft";
const nameOf = (event: ChangeEvent<HTMLInputElement>) => event.target.files?.[0]?.name ?? "";

function FilePicker({ title, hint, file, required, onPick }: { title: string; hint: string; file: string; required?: boolean; onPick: (value: string) => void }) {
  return <label className={`${styles.filePicker} ${file ? styles.uploaded : ""}`}>
    <input type="file" aria-label={`Upload ${title}`} onChange={(event) => onPick(nameOf(event))} />
    <span className={styles.uploadIcon}><Upload size={16} strokeWidth={2.25} /></span><span><strong>{file || title}</strong><small>{file ? "Selected - click to replace" : hint}</small></span>
    {file ? <em>Uploaded</em> : required ? <em className={styles.required}>Required</em> : null}
  </label>;
}

export function OnboardingWizard() {
  const [step, setStep] = useState<Step>("welcome");
  const [draft, setDraft] = useState<Draft>(() => {
    if (typeof window === "undefined") return emptyDraft;
    const saved = window.sessionStorage.getItem(draftKey);
    if (!saved) return emptyDraft;
    try { return { ...emptyDraft, ...JSON.parse(saved) }; } catch { window.sessionStorage.removeItem(draftKey); return emptyDraft; }
  });
  const index = STEPS.findIndex((item) => item.id === step);
  const patch = (value: Partial<Draft>) => setDraft((previous) => ({ ...previous, ...value }));

  useEffect(() => { window.sessionStorage.setItem(draftKey, JSON.stringify(draft)); }, [draft]);

  const requirements = useMemo(() => [
    { label: "Business profile", complete: Boolean(draft.business && draft.registration && draft.contact), to: "profile" as Step },
    { label: "Business verification file", complete: Boolean(draft.verification), to: "files" as Step },
    { label: "Product catalogue", complete: Boolean(draft.catalogue), to: "catalogue" as Step },
    { label: "Shipping, returns and privacy policies", complete: ["Shipping policy", "Returns policy", "Privacy policy"].every((policy) => draft.policies[policy]), to: "policies" as Step },
    { label: "Customer member offer", complete: Boolean(draft.membershipOffer.trim()), to: "membership" as Step },
  ], [draft]);
  const complete = requirements.every((item) => item.complete);
  const next = () => setStep(STEPS[Math.min(index + 1, STEPS.length - 1)].id);
  const back = () => setStep(STEPS[Math.max(index - 1, 0)].id);

  if (draft.submitted) return <section className={styles.complete}><span><Check size={27} strokeWidth={2.5} /></span><p>Draft complete</p><h1>Submitting is not in this prototype.</h1><div>Nothing was sent or saved to a server; this draft lives only in this browser tab.</div><Link href="/">Return to dashboard</Link></section>;

  return <main className={styles.page}>
    <header className={styles.header}><Link className={styles.brand} href="/"><span>B</span>BondLayer</Link><div><p>Merchant setup</p><h1>Set up your BondLayer workspace</h1></div><aside><small><Clock3 size={13} /> About 5 minutes</small><Link href="/">Save and exit</Link></aside></header>
    <div className={styles.layout}>
      <aside className={styles.steps} aria-label="Onboarding steps">{STEPS.map((item, itemIndex) => <button key={item.id} className={step === item.id ? styles.active : itemIndex < index ? styles.done : ""} onClick={() => setStep(item.id)}><i>{itemIndex < index ? <Check size={13} strokeWidth={3} /> : itemIndex + 1}</i><span>{item.label}</span></button>)}</aside>
      <section className={styles.card} key={step}>
        {step === "welcome" && <div className={`${styles.stage} ${styles.welcome}`}><p>Welcome to BondLayer</p><h2>Make your catalogue ready for the next generation of shopping.</h2><div>Complete a few essentials so agents can discover your products, understand your policies and represent your business accurately.</div><ol><li><b>Bring your data</b><small>Upload files or your product catalogue when ready.</small></li><li><b>Set clear policies</b><small>Help customers and agents know what to expect.</small></li><li><b>Submit with confidence</b><small>Review requirements before assessment.</small></li></ol><footer><Link href="/">Save for later</Link><button onClick={next}>Start setup</button></footer></div>}
        {step === "profile" && <div className={styles.stage}><p>Step 1 of 7</p><h2>Tell us about your business</h2><div>These details identify your merchant workspace and catalogue.</div><div className={styles.form}><label>Business name<input value={draft.business} onChange={(e) => patch({ business: e.target.value })} /></label><label>Registration or ABN<input placeholder="e.g. 51 824 753 556" value={draft.registration} onChange={(e) => patch({ registration: e.target.value })} /></label><label>Primary contact<input placeholder="Full name" value={draft.contact} onChange={(e) => patch({ contact: e.target.value })} /></label><label>Business category<select defaultValue="Consumer electronics"><option>Consumer electronics</option><option>Home and lifestyle</option><option>Health and beauty</option><option>Other</option></select></label></div><Footer back={back} next={next} /></div>}
        {step === "files" && <div className={styles.stage}><p>Step 2 of 7</p><h2>Verify your business</h2><div>Upload a registration document or other supporting file. You can add more later.</div><div className={styles.grid}><FilePicker title="Business registration document" hint="PDF, JPG or PNG - up to 10 MB" required file={draft.verification} onPick={(verification) => patch({ verification })} /><FilePicker title="Brand logo" hint="Optional - PNG, JPG or SVG" file="" onPick={() => undefined} /></div><small className={styles.note}>Uploading files is not in this prototype: the file name is kept in this browser tab only.</small><Footer back={back} next={next} /></div>}
        {step === "data" && <div className={styles.stage}><p>Step 3 of 7</p><h2>Bring in your data</h2><div>Start with a CSV or XLSX file. You will map fields before import.</div><aside className={styles.callout}><span><b>Need a starting point?</b><small>Download the template with recommended product fields.</small></span><button>Download template</button></aside><FilePicker title="Upload data file" hint="CSV or XLSX - up to 25 MB" file={draft.data} onPick={(data) => patch({ data })} /><Footer back={back} next={next} /></div>}
        {step === "catalogue" && <div className={styles.stage}><p>Step 4 of 8</p><h2>Add your catalogue</h2><div>Upload products now or add them individually after onboarding.</div><FilePicker title="Upload product catalogue" hint="CSV or XLSX - one or more products" required file={draft.catalogue} onPick={(catalogue) => patch({ catalogue })} /><div className={styles.or}>or</div><button className={styles.manual}><i>+</i><span><b>Add your first product manually</b><small>Name, SKU, price, stock and category</small></span><ChevronRight size={18} /></button><Footer back={back} next={next} /></div>}
        {step === "readiness" && <div className={styles.stage}><p>Step 5 of 8</p><h2>Review catalogue readiness</h2><div>We will prepare your catalogue for agent discovery. Review the items that need your attention before publishing.</div>{draft.catalogue ? <><section className={styles.readinessIssues}><h3>Readiness for a file chosen here</h3><button onClick={() => setStep("catalogue")}><span><CircleAlert size={14} strokeWidth={2.4} /></span><p><b>Not in this prototype</b><small>This wizard does not upload the file. The real readiness report for each seeded merchant is on the Catalogue page.</small></p><i><ChevronRight size={18} /></i></button><aside><b>See a real report</b><small><Link href="/catalogue/">Open the catalogue readiness report</Link></small></aside></section></> : <section className={styles.emptyReview}><span><Upload size={18} /></span><h3>Upload a catalogue to see readiness results.</h3><p>Once your import is processed, this step will show recognised products, mapped fields and anything that needs your review.</p><button onClick={() => setStep("catalogue")}>Go to catalogue upload</button></section>}<Footer back={back} next={next} /></div>}        {step === "policies" && <div className={styles.stage}><p>Step 6 of 8</p><h2>Publish your merchant policies</h2><div>Clear policies make buying more reliable for customers and agents.</div><div className={styles.policyList}>{["Shipping policy", "Returns policy", "Privacy policy", "Terms of sale"].map((policy, i) => <FilePicker key={policy} title={policy} hint={i < 3 ? "PDF or policy text" : "Optional - PDF or policy text"} required={i < 3} file={draft.policies[policy] ?? ""} onPick={(file) => patch({ policies: { ...draft.policies, [policy]: file } })} />)}</div><Footer back={back} next={next} /></div>}
        {step === "membership" && <div className={styles.stage}><p>Step 7 of 8</p><h2>Describe your customer membership offer</h2><div>Tell agents what shoppers receive when they join your loyalty or member programme.</div><article className={styles.policy}><h3>Customer membership offer</h3><div>Include the benefits, eligibility and any important conditions. This information can be shown alongside eligible products.</div></article><label className={styles.offerField}>Membership or loyalty offer<textarea value={draft.membershipOffer} onChange={(e) => patch({ membershipOffer: e.target.value })} placeholder="e.g. Members receive free shipping and 2× points on electronics." rows={4} /></label><Footer back={back} next={next} /></div>}
        {step === "review" && <div className={styles.stage}><p>Step 8 of 8</p><h2>Review your setup</h2><div>Resolve outstanding requirements before submitting your merchant information.</div><div className={styles.review}>{requirements.map((item) => <button key={item.label} onClick={() => setStep(item.to)}><i className={item.complete ? styles.checked : ""}>{item.complete ? <Check size={12} strokeWidth={3} /> : null}</i><span><b>{item.label}</b><small>{item.complete ? "Complete" : "Required before submission"}</small></span><ChevronRight size={18} /></button>)}</div><Footer back={back} next={() => patch({ submitted: true })} label="Submit for review" disabled={!complete} /></div>}
      </section>
    </div>
  </main>;
}

function Footer({ back, next, label = "Save and continue", disabled = false }: { back: () => void; next: () => void; label?: string; disabled?: boolean }) { return <footer className={styles.footer}><button className={styles.quiet} onClick={back}>Back</button><button disabled={disabled} onClick={next}>{label}</button></footer>; }

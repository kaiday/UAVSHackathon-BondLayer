"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { ArrowUp, X } from "lucide-react";
import { humanise, severityTone, useReport, useSelectedMerchant } from "@/lib/api";
import { answer, type AskAnswer } from "@/lib/ask";
import styles from "./ask-bar.module.css";

const HEADINGS: Record<AskAnswer["intent"], string> = {
  fixes: "Fix these first, worst first",
  blockers: "Blockers: these listings are dropped by an agent's filter",
  field: "What the report says about that field",
  fallback: "I answer from this merchant's catalogue readiness report. The top fixes are",
};

export function AskBar() {
  const merchant = useSelectedMerchant();
  const report = useReport(merchant);
  const [question, setQuestion] = useState("");
  const [asked, setAsked] = useState<string | null>(null);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!question.trim()) return;
    setAsked(question.trim());
    setQuestion("");
  }

  const result = asked && report.data ? answer(asked, report.data) : null;

  return (
    <>
      {asked && (
        <section className={styles.panel} aria-live="polite">
          <header className={styles.header}>
            <div>
              <p className={styles.question}>{asked}</p>
              {merchant && report.data && (
                <p className={styles.meta}>
                  {humanise(merchant)} · readiness {report.data.readiness} · {report.data.skus} SKUs
                </p>
              )}
            </div>
            <button type="button" className={styles.close} aria-label="Close answer" onClick={() => setAsked(null)}>
              <X size={15} strokeWidth={2.2} />
            </button>
          </header>

          {merchant === null && <p className={styles.note}>Select a merchant first.</p>}
          {merchant !== null && report.loading && <p className={styles.note}>Reading the readiness report…</p>}
          {report.error && <p className={styles.note}>Could not read the report: {report.error}</p>}

          {result && (
            <>
              <p className={styles.heading}>{HEADINGS[result.intent]}</p>
              {result.groups.length === 0 ? (
                <p className={styles.note}>
                  {result.intent === "blockers"
                    ? "No blockers in this catalogue."
                    : result.intent === "field"
                      ? `No diagnostics for ${result.fields.join(", ")}.`
                      : "No diagnostics that need action."}
                </p>
              ) : (
                <ol className={styles.list}>
                  {result.groups.map((g) => (
                    <li key={`${g.severity}|${g.rule}|${g.field}`}>
                      <div className={styles.row}>
                        <span className={`pill ${severityTone(g.severity)}`}>{humanise(g.severity)}</span>
                        <strong>{humanise(g.rule)}</strong>
                        <code>{g.field}</code>
                        <span className={styles.count}>
                          {g.rows} {g.rows === 1 ? "row" : "rows"}
                          {g.autofixed > 0 && ` · ${g.autofixed} normalised on read`}
                        </span>
                      </div>
                      <p>{g.example}</p>
                    </li>
                  ))}
                </ol>
              )}
              <footer className={styles.footer}>
                <span>
                  Matched {result.matched}. Answered from <code>GET /onboard/report/{merchant}</code>, no AI model.
                </span>
                <Link href="/quality/" onClick={() => setAsked(null)}>Open data quality →</Link>
              </footer>
            </>
          )}
        </section>
      )}

      <form className="prompt-bar" onSubmit={submit}>
        <span className="prompt-mark" aria-hidden="true">✦</span>
        <input
          aria-label="Ask BondLayer"
          placeholder="Ask about this merchant's catalogue, e.g. how do I improve my performance?"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
        />
        <button type="submit" aria-label="Send prompt" title="Send prompt" disabled={!question.trim()}>
          <ArrowUp size={16} strokeWidth={2.4} />
        </button>
      </form>
    </>
  );
}

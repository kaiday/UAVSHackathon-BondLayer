"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ArrowUp, X } from "lucide-react";
import { humanise, useSelectedMerchant, type Diagnostic } from "@/lib/api";
import styles from "./ask-bar.module.css";

type Answer = { answer: string; citations: Diagnostic[]; source: string; ai: { model: string; response_id: string } };

export function AskBar() {
  const merchant = useSelectedMerchant();
  return <MerchantAskBar key={merchant ?? "none"} merchant={merchant} />;
}

function MerchantAskBar({ merchant }: { merchant: string | null }) {
  const [question, setQuestion] = useState("");
  const [asked, setAsked] = useState<string | null>(null);
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const generation = useRef(0);

  useEffect(() => () => { generation.current++; }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!question.trim() || !merchant || busy) return;
    const request = ++generation.current;
    setAsked(question.trim()); setAnswer(null); setError(null); setBusy(true);
    try {
      const response = await fetch(`/onboard/ask/${encodeURIComponent(merchant)}`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: question.trim() }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail ?? "The AI request failed. Please retry.");
      if (generation.current === request) { setAnswer(body); setQuestion(""); }
    } catch (cause) {
      if (generation.current === request) setError(cause instanceof Error ? cause.message : "Request failed.");
    } finally { if (generation.current === request) setBusy(false); }
  }

  return <>
    {asked && <section className={styles.panel} aria-live="polite">
      <header className={styles.header}>
        <div><p className={styles.question}>{asked}</p><p className={styles.meta}>{merchant && humanise(merchant)}</p></div>
        <button type="button" className={styles.close} aria-label="Close answer" onClick={() => { generation.current++; setAsked(null); setBusy(false); }}><X size={15} /></button>
      </header>
      {busy && <p className={styles.note}>Thinking…</p>}
      {error && <p className="state-error" role="alert">{error}</p>}
      {answer && <>
        <p className={styles.note} style={{ whiteSpace: "pre-wrap" }}>{answer.answer}</p>
        {answer.citations.length > 0 && <ol className={styles.list}>{answer.citations.map((d, i) => <li key={i}><strong>Row {d.row} · {d.sku_id} · {d.field}</strong><p>{d.message}</p></li>)}</ol>}
        <footer className={styles.footer}><span title={`${answer.ai.model} · ${answer.ai.response_id}`}>Based on your catalogue report</span><Link href="/quality/">Data quality →</Link></footer>
      </>}
    </section>}
    <form className="prompt-bar" data-tour="prompt" onSubmit={submit}>
      <span className="prompt-mark" aria-hidden="true">✦</span>
      <input aria-label="Ask BondLayer" placeholder="Ask about your catalogue, e.g. what should I fix first?" value={question} maxLength={3000} onChange={e => setQuestion(e.target.value)} />
      <button type="submit" aria-label="Send prompt" disabled={!question.trim() || !merchant || busy}><ArrowUp size={16} /></button>
    </form>
  </>;
}

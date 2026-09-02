/* /evidence — the material a sceptical judge should be able to check.

   Nothing here is authored prose about the system: every check, exchange,
   prompt and number is fetched from /api/evidence, which produces it by
   running the real thing. */

const $ = (id) => document.getElementById(id);
const esc = (s) =>
  String(s ?? "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
const money = (n) => Number(n).toFixed(2);

let DATA = null;
let wireSide = "off";

// ── architecture: stated once, here, and nowhere else ────────────────
const ARCHITECTURE = [
  {
    who: "Shopper",
    what: "A person typing into the chat on the demo screen.",
    badge: ["real", "you"],
  },
  {
    who: "Shopping agent",
    what: "An LLM given a shopping-agent system prompt. It has no BondLayer code, no knowledge of our schema, and speaks only UCP.",
    badge: ["sim", "simulated"],
  },
  {
    who: "UCP over HTTP",
    what: "Real requests to three separate services on ports 8101–8103. Capability negotiation via the <code>UCP-Agent</code> header.",
    badge: ["real", "real"],
  },
  {
    who: "BondLayer service",
    what: "The product. Serves <code>/.well-known/ucp</code>, <code>catalog.search</code>, <code>catalog.lookup</code>, <code>identity_linking</code> and the signed <code>org.bondlayer.benefit_value</code> extension. Ed25519 signing. <b>A server, not an agent — deliberately.</b>",
    badge: ["real", "real"],
  },
  {
    who: "Merchant systems",
    what: "Messy CSV exports and human-written policy documents, standing in for a real retailer's catalogue and terms.",
    badge: ["mock", "mocked"],
  },
  {
    who: "Valuation library",
    what: "Optional, agent-side, deterministic. The headline demo does <b>not</b> depend on it — assuming agents adopt our library would assume away the problem.",
    badge: ["real", "real · optional"],
  },
];

function renderArchitecture() {
  $("archgrid").innerHTML = ARCHITECTURE.map(
    (r, i) => `
    <div class="archrow">
      <span class="who">${esc(r.who)}</span>
      <span class="what">${r.what}</span>
      <span class="badge ${r.badge[0]}">${esc(r.badge[1])}</span>
    </div>
    ${i < ARCHITECTURE.length - 1 ? '<div class="archarrow">↓</div>' : ""}`
  ).join("");
}

// ── the wire ────────────────────────────────────────────────────────
function renderWire() {
  const rows = DATA.wire[wireSide];
  $("wire-body").innerHTML = rows
    .map((e) => {
      const caps = e.active_capabilities.length
        ? e.active_capabilities
            .map(
              (c) =>
                `<span class="capchip ${c.startsWith("org.") ? "ext" : ""}">${esc(c)}</span>`
            )
            .join("")
        : `<span class="capchip none">not applicable — this is the declaration</span>`;
      const short = e.url.replace(/^https?:\/\/127\.0\.0\.1:/, ":");
      return `<details class="exchange">
        <summary>
          <span class="m">${esc(e.merchant_id)}</span>
          <span class="u">${esc(e.method)} ${esc(short)}</span>
          <span class="st ${e.status >= 400 ? "err" : ""}">${e.status}</span>
          <span class="ms">${e.elapsed_ms} ms</span>
        </summary>
        <div class="exdetail">
          <p class="exlabel">Request headers</p>
          <pre class="code">${esc(
            Object.entries(e.request_headers).map(([k, v]) => `${k}: ${v}`).join("\n")
          )}</pre>
          <p class="exlabel">Capabilities the merchant activated</p>
          <div class="activecaps">${caps}</div>
          <p class="exlabel">Response body</p>
          <pre class="code">${esc(e.body)}</pre>
          <p class="exlabel">Run it yourself</p>
          <pre class="code">${esc(e.curl)}</pre>
        </div>
      </details>`;
    })
    .join("");
}

// ── conformance ─────────────────────────────────────────────────────
function renderConformance() {
  const c = DATA.conformance;
  const score = $("conf-score");
  score.textContent = c.headline;
  score.className = "score " + (c.ok ? "ok" : "bad");
  $("conf-body").innerHTML = c.checks
    .map(
      (x) => `<div class="check">
        <span class="verdictchip ${x.passed ? "pass" : "fail"}">${x.passed ? "PASS" : "FAIL"}</span>
        <div>
          <div class="cname">${esc(x.name)}</div>
          <div class="cdetail">${esc(x.detail)}</div>
          ${x.citation ? `<div class="ccite">${esc(x.citation)}</div>` : ""}
        </div>
      </div>`
    )
    .join("");
}

// ── prompts ─────────────────────────────────────────────────────────
function renderPrompts() {
  const agentSide = DATA.prompts.filter((p) => p.agent_side);
  const leaking = agentSide.filter((p) => p.mentions_bondlayer);
  const box = $("leak-callout");
  box.className = "callout " + (leaking.length ? "warn" : "");
  box.innerHTML = leaking.length
    ? `<h3>A prompt names us</h3><p>${leaking
        .map((p) => `<b>${esc(p.name)}</b> contains ${esc(p.leaks.join(", "))}`)
        .join("; ")}. The agent is being told the answer — this invalidates the claim.</p>`
    : `<h3>None of the ${agentSide.length} agent-side prompts mention BondLayer</h3>
       <p>Checked live, on this page load, against
       <code>bondlayer</code>, <code>benefit_value</code> and
       <code>org.bondlayer</code> — and asserted in
       <code>tests/test_flow_v2.py</code>. The agent is never told our schema
       exists. The merchant-side policy converter names it, correctly, because
       that is our own onboarding tooling rather than a third party's agent.</p>`;

  $("prompt-body").innerHTML = DATA.prompts
    .map(
      (p) => `<details class="prompt">
        <summary>
          <span class="pname">${esc(p.name)}</span>
          <span class="pused">${esc(p.used_for)}</span>
          <span class="pstat ${
            !p.agent_side ? "side" : p.mentions_bondlayer ? "leak" : "clean"
          }">${
            !p.agent_side
              ? "merchant-side"
              : p.mentions_bondlayer
              ? "MENTIONS BONDLAYER"
              : "never mentions BondLayer"
          }</span>
        </summary>
        <div class="pbody">
          <p class="pwhy">${esc(p.why)}</p>
          <p class="exlabel">Verbatim</p>
          <pre class="code">${esc(p.text)}</pre>
        </div>
      </details>`
    )
    .join("");
}

// ── fairness ────────────────────────────────────────────────────────
function renderFairness() {
  const f = DATA.fairness;
  $("fair-table").innerHTML = `
    <table class="ftable">
      <thead><tr>
        <th>Merchant</th><th>Has a real policy</th>
        <th>Published to agents</th><th>Signed</th>
        <th>Value stranded in prose</th>
      </tr></thead>
      <tbody>${f.merchants
        .map((m) => {
          const stranded = m.total_aud > 0;
          return `<tr>
            <td class="mname">${esc(m.merchant_id)}</td>
            <td>${m.has_policy_document ? "yes" : "<span class='bad'>no</span>"}</td>
            <td class="num">${m.published_machine_readable}</td>
            <td class="num ${
              m.published_machine_readable && !m.signed ? "bad" : m.signed ? "good" : ""
            }">${m.signed}</td>
            <td class="num ${stranded ? "warnc" : "good"}">${
              stranded ? "$" + money(m.total_aud) : "$0.00 — all of it published"
            }</td>
          </tr>`;
        })
        .join("")}</tbody>
    </table>
    <p class="fnote">${esc(f.note)}</p>`;

  $("fair-policies").innerHTML = f.merchants
    .map((m) => {
      const prose = f.policies[m.merchant_id];
      const facts = m.facts.length
        ? `<p class="exlabel">What an agent could have been told</p>
           <div class="stranded">${m.facts
             .map(
               (x) => `<div class="sfact">
                 <span class="samt">${x.value_aud ? "$" + money(x.value_aud) : "—"}</span>
                 <span>${esc(x.title)}${
                   x.note ? `<br><span class="snote">${esc(x.note)}</span>` : ""
                 }</span>
               </div>`
             )
             .join("")}</div>`
        : "";
      return `<details class="policy">
        <summary>${esc(m.merchant_id)} — policy.md
          <span class="pmeta">${
            m.published_machine_readable
              ? `${m.signed}/${m.published_machine_readable} records signed on the wire`
              : "nothing on the wire"
          }</span>
        </summary>
        <div class="pbody2">
          ${facts}
          <p class="exlabel">The document, as customers read it</p>
          <pre class="code">${esc(prose || "(no policy document)")}</pre>
        </div>
      </details>`;
    })
    .join("");
}

// ── tabs ────────────────────────────────────────────────────────────
$("evtabs").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-sec]");
  if (!btn) return;
  document.querySelectorAll("#evtabs button").forEach((b) => b.classList.toggle("on", b === btn));
  document.querySelectorAll(".evmain > section").forEach((s) => {
    s.hidden = s.id !== "sec-" + btn.dataset.sec;
  });
  window.scrollTo({ top: 0 });
});

document.querySelector(".wiretoggle").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-wire]");
  if (!btn) return;
  wireSide = btn.dataset.wire;
  document
    .querySelectorAll(".wiretoggle button")
    .forEach((b) => b.classList.toggle("on", b === btn));
  renderWire();
});

// ── boot ────────────────────────────────────────────────────────────
(async () => {
  renderArchitecture();
  try {
    DATA = await (await fetch("/api/evidence")).json();
  } catch (err) {
    $("banner").innerHTML = `<span class="warn">could not load evidence: ${esc(err.message)}</span>`;
    return;
  }
  renderWire();
  renderConformance();
  renderPrompts();
  renderFairness();
  const c = DATA.conformance;
  $("banner").innerHTML =
    `<span class="${c.ok ? "ok" : "warn"}">UCP conformance ${c.headline}</span><br>` +
    `${DATA.wire.off.length + DATA.wire.on.length} HTTP exchanges captured live · ` +
    `${DATA.prompts.length} system prompts`;
})();

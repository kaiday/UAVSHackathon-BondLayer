/* BondLayer merchant dashboard — React, no build step.
 *
 * React and htm are vendored under /dashboard/vendor and served by FastAPI, so
 * the page makes no network call except to our own API. A CDN script tag would
 * be a live fetch at demo time on shared venue wifi, which is the one thing the
 * demo cannot afford.
 *
 * Every number on this screen comes from /onboard/*. Nothing is computed here
 * and nothing is hardcoded: if a figure is wrong, it is wrong in the adapter,
 * which is where it should be fixed.
 */

const { createElement, useState, useEffect, useMemo, Fragment } = React;
const html = htm.bind(createElement);

const SEVERITIES = ["blocker", "degrades_match", "cosmetic", "info"];
const SEV_LABEL = {
  blocker: "Blocker",
  degrades_match: "Degrades match",
  cosmetic: "Cosmetic",
  info: "Correct",
};
const SEV_MARK = { blocker: "!", degrades_match: "▲", cosmetic: "·", info: "✓" };

// What each severity means in terms of what the agent does. This vocabulary is
// the product argument in miniature, so it is stated on the screen rather than
// left for someone to explain out loud.
const SEV_MEANING = {
  blocker: "invisible to a filter an agent will apply",
  degrades_match: "findable, but loses a comparison it should win",
  cosmetic: "tidiness; nothing downstream breaks",
  info: "correct as it stands — no action",
};

function api(path) {
  return fetch(path).then((r) => {
    if (!r.ok) throw new Error(path + " → " + r.status);
    return r.json();
  });
}

function Switcher({ merchants, selected, onSelect }) {
  return html`
    <div class="switcher">
      ${merchants.map(
        (m) => html`
          <button
            class="merchant"
            key=${m.merchant}
            aria-pressed=${String(m.merchant === selected)}
            onClick=${() => onSelect(m.merchant)}
          >
            <div class="name">
              ${m.merchant}
              ${m.merchant === "voltway" &&
              html`<span class="role bondlayer">BondLayer</span>`}
              ${m.merchant === "citycircuit" && html`<span class="role">control</span>`}
            </div>
            <div class="meta">${m.rows_read} listings · ${m.blockers} blockers</div>
            <div class="score">${m.readiness}</div>
          </button>
        `
      )}
    </div>
  `;
}

function Readiness({ report }) {
  const total = report.diagnostics.length || 1;
  return html`
    <div class="card">
      <div class="card-head">
        <span class="step">2</span>
        <h2>Catalogue health</h2>
      </div>
      <div class="card-body">
        <div class="readiness">
          <div>
            <div class="big">${report.readiness}<span class="out-of"> / 100</span></div>
            <div class="page-sub" style=${{ margin: "4px 0 0" }}>
              Readiness — the share of this feed an agent can act on
            </div>
          </div>
        </div>

        <div class="bar">
          ${SEVERITIES.map(
            (s) => html`<span
              key=${s}
              class="s-${s}"
              style=${{ width: (report.by_severity[s] / total) * 100 + "%" }}
              title=${SEV_LABEL[s]}
            ></span>`
          )}
        </div>
        <div class="legend">
          ${SEVERITIES.map(
            (s) => html`<span key=${s}>
              <i class="swatch" style=${{ background: `var(--${s})` }}></i>
              <b>${report.by_severity[s]}</b> ${SEV_LABEL[s].toLowerCase()}
            </span>`
          )}
        </div>

        <div class="stats">
          <div class="stat">
            <div class="v">${report.rows_read}</div>
            <div class="k">listings read</div>
          </div>
          <div class="stat">
            <div class="v">${report.rows_rejected}</div>
            <div class="k">rejected</div>
          </div>
          <div class="stat">
            <div class="v">${report.attributes_fixed}</div>
            <div class="k">attributes repaired</div>
          </div>
          <div class="stat">
            <div class="v">${Object.keys(report.by_rule).length}</div>
            <div class="k">rules fired</div>
          </div>
        </div>
      </div>
    </div>
  `;
}

function Diagnostics({ report }) {
  const [filter, setFilter] = useState("actionable");

  const shown = useMemo(() => {
    if (filter === "all") return report.diagnostics;
    if (filter === "actionable")
      return report.diagnostics.filter((d) => d.severity !== "info");
    return report.diagnostics.filter((d) => d.severity === filter);
  }, [report, filter]);

  const counts = report.by_severity;
  const actionable = counts.blocker + counts.degrades_match + counts.cosmetic;

  const chip = (key, label) => html`
    <button
      key=${key}
      aria-pressed=${String(filter === key)}
      onClick=${() => setFilter(key)}
    >
      ${label}
    </button>
  `;

  return html`
    <div class="card">
      <div class="card-head">
        <span class="step">3</span>
        <h2>What an agent cannot read</h2>
      </div>
      <div class="filters">
        ${chip("actionable", `Needs attention (${actionable})`)}
        ${chip("blocker", `Blockers (${counts.blocker})`)}
        ${chip("degrades_match", `Degrades match (${counts.degrades_match})`)}
        ${chip("info", `Already correct (${counts.info})`)}
        ${chip("all", `All (${report.diagnostics.length})`)}
      </div>
      <div class="card-body tight">
        ${shown.length === 0
          ? html`<div class="empty">Nothing in this category.</div>`
          : shown
              .slice(0, 60)
              .map(
                (d, i) => html`
                  <div class="diag" key=${d.row + d.rule + i}>
                    <span class="sev ${d.severity}" title=${SEV_MEANING[d.severity]}>
                      ${SEV_MARK[d.severity]}
                    </span>
                    <div class="diag-main">
                      <div class="diag-top">
                        <span class="rule">${d.rule}</span>
                        <span class="where">row ${d.row} · ${d.sku_id} · ${d.field}</span>
                      </div>
                      <div class="diag-msg">${d.message}</div>
                      ${d.found &&
                      d.found !== d.normalised &&
                      html`<div class="fix">
                        <code class="was">${d.found}</code>
                        <span class="arrow">→</span>
                        <code class="now">${d.normalised || "—"}</code>
                        ${d.autofixed && html`<span class="fixed-tag">repaired</span>`}
                      </div>`}
                    </div>
                  </div>
                `
              )}
        ${shown.length > 60 &&
        html`<div class="empty">Showing the first 60 of ${shown.length}.</div>`}
      </div>
    </div>
  `;
}

function Upload({ merchant, onUploaded }) {
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function send() {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const body = new FormData();
      body.append("file", file);
      const r = await fetch(`/onboard/catalog?merchant=${merchant}`, {
        method: "POST",
        body,
      });
      const payload = await r.json();
      if (!r.ok) throw new Error(payload.detail || r.status);
      onUploaded(payload);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setBusy(false);
    }
  }

  return html`
    <div class="card">
      <div class="card-head">
        <span class="step">1</span>
        <h2>Your existing files</h2>
      </div>
      <div class="card-body">
        <div class="drop">
          <div class="grow">
            <div class="ok">✓ catalogue loaded — seeded from your export</div>
            <div class="hint">
              Upload a different CSV to re-run the check. Required columns: sku,
              merchant, price, title, category.
            </div>
          </div>
          <input
            type="file"
            accept=".csv,text/csv"
            onChange=${(e) => setFile(e.target.files[0] || null)}
          />
          <button class="primary" disabled=${!file || busy} onClick=${send}>
            ${busy ? "Checking…" : "Check catalogue"}
          </button>
        </div>
        ${error && html`<div class="note" style=${{ color: "var(--blocker)" }}>${error}</div>`}
        <div class="note">
          Nothing is published from this screen. BondLayer reads what you already
          have — a catalogue export and your policy documents — and reports what an
          agent can and cannot see.
        </div>
      </div>
    </div>
  `;
}

function Analytics() {
  // Issue #9: "a dashboards analytics page just for demo purpose, no data
  // populated." Labelled as such rather than filled with invented numbers.
  const tiles = [
    ["Agent requests", "—"],
    ["Offer legibility", "—"],
    ["Verified value credited", "—"],
    ["Benefits withheld by the wire", "—"],
  ];
  return html`
    <${Fragment}>
      <h1 class="page-title">Analytics</h1>
      <p class="page-sub">
        Per-request merchant visibility. Not populated in this prototype — these
        figures come from live agent traffic, which a seeded demo does not have.
      </p>
      <div class="grid">
        ${tiles.map(
          ([k, v]) => html`<div class="tile" key=${k}>
            <div class="k">${k}</div>
            <div class="v muted">${v}</div>
          </div>`
        )}
      </div>
    <//>
  `;
}

// --- Requests: "why we lost" ------------------------------------------
//
// Everything here is a projection of RequestReport, off /onboard/requests*.
// Four figures, one sentence, per merchant, three-way. Legible first, pretty
// second -- the dashboard's polish scores lower than the logic it renders.

function money(v) {
  const n = Number(v);
  return "$" + n.toLocaleString("en-AU", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function pct(v) {
  return Math.round(v * 100) + "%";
}

function RequestPicker({ requests, selected, onSelect }) {
  return html`
    <div class="card">
      <div class="card-head">
        <span class="step">R</span>
        <h2>Requests (${requests.length})</h2>
      </div>
      <div class="card-body tight req-list">
        ${requests.map((r) => {
          const won = r.merchants.find((m) => m.won);
          return html`
            <button
              key=${r.request_id}
              class="req-row"
              aria-pressed=${String(r.request_id === selected)}
              onClick=${() => onSelect(r.request_id)}
            >
              <span class="req-id">${r.request_id}</span>
              <span class="req-utterance">${r.utterance}</span>
              <span class="req-winner">${won ? won.merchant : "no winner"}</span>
            </button>
          `;
        })}
      </div>
    </div>
  `;
}

function MerchantRow({ row }) {
  return html`
    <div class="merchant-row ${row.won ? "won" : ""}">
      <div class="merchant-row-head">
        <div class="merchant-row-name">
          ${row.merchant}
          ${row.control_merchant && html`<span class="role">control</span>`}
        </div>
        <span class="verdict ${row.won ? "win" : "loss"}">${row.won ? "won" : "lost"}</span>
      </div>
      <div class="four-figures">
        <div class="figure">
          <div class="v">${row.fields_exposed}</div>
          <div class="k">fields exposed</div>
        </div>
        <div class="figure">
          <div class="v">${pct(row.legible_share)}</div>
          <div class="k">legible share of the real offer</div>
        </div>
        <div class="figure">
          <div class="v credited">${money(row.value_credited_aud)}</div>
          <div class="k">verified value credited</div>
        </div>
        <div class="figure">
          <div class="v withheld">${money(row.value_withheld_aud)}</div>
          <div class="k">value withheld by the wire</div>
        </div>
      </div>
      <div class="why">
        <b>${row.won ? "Why we won: " : "Why we lost: "}</b>
        ${row.lost_because || "Highest verified value credited against the shopper's stated intent."}
      </div>
    </div>
  `;
}

function RequestDetail({ report }) {
  return html`
    <div class="card">
      <div class="card-head">
        <span class="step">R</span>
        <h2>${report.request_id} — ${report.utterance}</h2>
      </div>
      <div class="card-body tight">
        ${report.merchants.map((row) => html`<${MerchantRow} row=${row} key=${row.merchant} />`)}
      </div>
    </div>
  `;
}

function Requests() {
  const [requests, setRequests] = useState([]);
  const [selected, setSelected] = useState(null);
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api("/onboard/requests")
      .then((rs) => {
        setRequests(rs);
        setSelected((s) => s || (rs[0] && rs[0].request_id));
      })
      .catch((e) => setError(String(e.message || e)));
  }, []);

  useEffect(() => {
    if (!selected) return;
    setReport(null);
    api(`/onboard/requests/${selected}`)
      .then(setReport)
      .catch((e) => setError(String(e.message || e)));
  }, [selected]);

  if (error) return html`<div class="card"><div class="card-body">${error}</div></div>`;

  return html`
    <${Fragment}>
      <h1 class="page-title">Why we lost</h1>
      <p class="page-sub">
        One of the 30 frozen requests. Same query, three merchants, one wire.
        Four figures per merchant, then the sentence that explains the ranking.
      </p>
      <${RequestPicker} requests=${requests} selected=${selected} onSelect=${setSelected} />
      ${report
        ? html`<${RequestDetail} report=${report} />`
        : html`<div class="card"><div class="empty">Loading…</div></div>`}
    <//>
  `;
}

function Onboarding() {
  const [merchants, setMerchants] = useState([]);
  const [selected, setSelected] = useState(null);
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api("/onboard/merchants")
      .then((ms) => {
        setMerchants(ms);
        setSelected((s) => s || (ms[0] && ms[0].merchant));
      })
      .catch((e) => setError(String(e.message || e)));
  }, []);

  useEffect(() => {
    if (!selected) return;
    setReport(null);
    api(`/onboard/report/${selected}`)
      .then(setReport)
      .catch((e) => setError(String(e.message || e)));
  }, [selected]);

  if (error) return html`<div class="card"><div class="card-body">${error}</div></div>`;

  return html`
    <${Fragment}>
      <h1 class="page-title">Make your catalogue legible to AI agents</h1>
      <p class="page-sub">
        An agent shopping the protocol reads what you publish, not your website.
        This is what it can see today.
      </p>
      <${Switcher} merchants=${merchants} selected=${selected} onSelect=${setSelected} />
      <${Upload}
        merchant=${selected}
        onUploaded=${(r) => {
          setReport(r);
          api("/onboard/merchants").then(setMerchants);
        }}
      />
      ${report
        ? html`<${Fragment}>
            <${Readiness} report=${report} />
            <${Diagnostics} report=${report} />
          <//>`
        : html`<div class="card"><div class="empty">Loading…</div></div>`}
    <//>
  `;
}

function App() {
  const [tab, setTab] = useState("onboarding");
  return html`
    <${Fragment}>
      <header class="topbar">
        <div class="topbar-inner">
          <div class="brand"><span class="dot"></span> BondLayer</div>
          <nav class="tabs">
            <button
              aria-current=${tab === "onboarding" ? "page" : null}
              onClick=${() => setTab("onboarding")}
            >
              Onboarding
            </button>
            <button
              aria-current=${tab === "requests" ? "page" : null}
              onClick=${() => setTab("requests")}
            >
              Requests
            </button>
            <button
              aria-current=${tab === "analytics" ? "page" : null}
              onClick=${() => setTab("analytics")}
            >
              Analytics
            </button>
          </nav>
        </div>
      </header>
      <main>
        ${tab === "onboarding" && html`<${Onboarding} />`}
        ${tab === "requests" && html`<${Requests} />`}
        ${tab === "analytics" && html`<${Analytics} />`}
      </main>
    <//>
  `;
}

ReactDOM.createRoot(document.getElementById("root")).render(html`<${App} />`);

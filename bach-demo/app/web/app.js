/* BondLayer demo v2 — one screen, two panes, one switch.

   The left pane is a real conversation with a live model, not a replayed
   script: the client holds the visible history and posts it back each turn.
   Everything numeric in the right pane arrives from the API, because a number
   computed in the browser is a number nobody can trace to a function in
   src/bondlayer/. */

const $ = (id) => document.getElementById(id);

const state = {
  extension: "on",
  levers: [],        // the merchant's own published terms
  published: null,   // Set of ids currently ticked; null = all of them
  focus: { id: "alpine", name: "Alpine Outfitters" },
  history: [],       // [{role, content}] — the visible conversation only
  vis: {},           // last visibility payload, by extension
  busy: false,
};

const money = (n) => Number(n).toFixed(2);
const escapeHtml = (s) =>
  String(s ?? "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));

const SUGGESTIONS = [
  "Find me a good waterproof jacket under $200.",
  "What happens if it doesn't fit?",
  "Is the Ridgeway warranty claim trustworthy?",
  "Which is cheapest once everything is counted?",
];

// ── banner ──────────────────────────────────────────────────────────
async function loadScenario() {
  const s = await (await fetch("/api/scenario")).json();
  state.focus = s.focus_merchant;
  $("console-h").textContent = s.focus_merchant.name;
  $("request").placeholder = s.request;

  $("suggestions").innerHTML = SUGGESTIONS.map(
    (q) => `<button type="button" class="suggest">${escapeHtml(q)}</button>`
  ).join("");
  document.querySelectorAll(".suggest").forEach((b) =>
    b.addEventListener("click", () => send(b.textContent))
  );

  const f = s.fixtures;
  const bits = [`chat is live · OpenAI`];
  bits.push(
    s.live_transport
      ? `<span class="ok">transport ${s.live_transport}</span>`
      : `<span class="warn">no live transport configured — chat will fail</span>`
  );
  bits.push(`${f.recorded} fixtures on disk for the scripted paths`);
  if (f.authored || f.unknown) {
    bits.push(`<span class="warn">${f.authored} HAND-AUTHORED — not model output</span>`);
  }
  $("banner").innerHTML = bits.join("<br>");
}

// ── rendering the thread ────────────────────────────────────────────
/** Remove the conversation but never the empty-state node itself.

    An earlier version cleared the thread with `chat.innerHTML = ""`, which
    also deleted #empty -- so the next send() dereferenced null and the whole
    turn died silently. Removing only the bubbles keeps the node identities the
    rest of this file relies on. */
function clearThread() {
  $("chat").querySelectorAll(".msg").forEach((el) => el.remove());
  state.history = [];
  $("verdict").hidden = true;
  $("outcome").textContent = "";
  $("outcome").className = "outcome";
}

/** Blank the console back to em-dashes, so it never shows one capability
    state's numbers under the other one's switch. */
function clearMetrics() {
  ["m-fields", "m-legible", "m-value", "m-withheld", "m-published"].forEach((id) => {
    $(id).textContent = "—";
    $(id).closest(".metric")?.classList.remove("up", "down");
  });
}

function bubble(role, text) {
  const el = document.createElement("div");
  el.className = "msg " + (role === "user" ? "you" : "bot");
  if (role === "user") {
    el.textContent = text;
  } else {
    el.innerHTML = `<div class="thinking on"><span></span><span></span><span></span></div>
                    <p class="reply-text"></p>
                    <div class="chips"></div>
                    <div class="provenance"></div>`;
  }
  $("chat").appendChild(el);
  el.scrollIntoView({ block: "end", behavior: "smooth" });
  return el;
}

function renderOffers(el, offers) {
  el.querySelector(".chips").innerHTML = offers
    .map((o) => {
      let cls = "chip";
      if (o.benefit_count && o.signed_count === o.benefit_count) cls += " signed";
      else if (o.benefit_count) cls += " unsigned";
      const detail = o.benefit_count
        ? `${o.signed_count}/${o.benefit_count} signed`
        : "no published terms";
      return `<span class="${cls}">${escapeHtml(o.merchant)}
        <span class="n">$${money(o.price_aud)} · ${detail}</span></span>`;
    })
    .join("");
}

function renderProvenance(el, call) {
  const box = el.querySelector(".provenance");
  if (!call || !call.available) {
    box.innerHTML = `<span class="none">no model call was made</span>`;
    return;
  }
  const kind =
    call.served_from === "fixture"
      ? `<span class="replay">replayed from ${call.fixture}</span>`
      : `<span class="live">live call</span>`;
  const bits = [kind, `<b>${escapeHtml(call.model)}</b>`, escapeHtml(call.provenance)];
  if (call.latency_ms) bits.push(`${call.latency_ms} ms`);
  if (call.usage && call.usage.output_tokens) bits.push(`${call.usage.output_tokens} output tokens`);
  box.innerHTML = bits.join(" · ");
}

// ── the console ─────────────────────────────────────────────────────
function renderVisibility(v, previous) {
  const set = (id, val, prev, better) => {
    const el = $(id);
    el.textContent = val;
    const box = el.closest(".metric");
    box.classList.remove("up", "down");
    if (prev !== undefined && prev !== null && Number(val) !== Number(prev)) {
      box.classList.add(better(Number(val), Number(prev)) ? "up" : "down");
    }
  };
  const more = (a, b) => a > b;
  const fewer = (a, b) => a < b;
  set("m-fields", v.fields_visible, previous?.fields_visible, more);
  set("m-legible", v.offer_legible_pct, previous?.offer_legible_pct, more);
  set("m-value", money(v.verified_value_aud), previous?.verified_value_aud, more);
  set("m-withheld", v.benefits_withheld, previous?.benefits_withheld, fewer);
  $("m-published").textContent = v.benefits_published;
}

function renderOutcome(winner, vis) {
  const won = winner === state.focus.id;
  const el = $("outcome");
  el.className = "outcome " + (won ? "win" : "lose");
  el.innerHTML = won
    ? `The agent would buy from <b>${escapeHtml(state.focus.name)}</b> — with
       <b>${vis.benefits_delivered} of ${vis.benefits_published}</b> published
       benefits legible and <b>$${money(vis.verified_value_aud)}</b> of verified
       value it could actually credit.`
    : `<b>${escapeHtml(state.focus.name)}</b> is not the pick. The agent could see
       <b>${vis.fields_visible} fields</b> and
       ${vis.benefits_delivered ? "" : "none"} of its ${vis.benefits_published}
       published benefits, so there was little to weigh against a cheaper
       sticker price.`;
}

// ── sending a turn ──────────────────────────────────────────────────
async function send(text) {
  if (state.busy) return;
  const content = (text ?? $("request").value).trim() || $("request").placeholder;
  $("request").value = "";
  $("empty").hidden = true;   // #empty is never removed, only toggled
  state.busy = true;
  $("send").disabled = true;

  bubble("user", content);
  state.history.push({ role: "user", content });
  const el = bubble("assistant", "");
  const reply = el.querySelector(".reply-text");
  const prev = state.vis[state.extension === "on" ? "off" : "on"];

  let acc = "";
  try {
    const resp = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: state.history, extension: state.extension }),
    });
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";

    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const frames = buf.split("\n\n");
      buf = frames.pop();

      for (const frame of frames) {
        const evt = /^event: (.+)$/m.exec(frame)?.[1];
        const raw = /^data: (.+)$/m.exec(frame)?.[1];
        if (!evt || !raw) continue;
        const d = JSON.parse(raw);

        if (evt === "offers") renderOffers(el, d);
        else if (evt === "visibility") {
          state.vis[state.extension] = d;
          renderVisibility(d, prev);
        } else if (evt === "payload") {
          $("payload-text").textContent = d.text;
          $("payload-hint").textContent =
            `${d.chars.toLocaleString()} chars · ${d.benefit_records} benefit records`;
        } else if (evt === "token") {
          el.querySelector(".thinking").classList.remove("on");
          acc += d.text;
          reply.textContent = acc;
          el.scrollIntoView({ block: "end" });
        } else if (evt === "replace") {
          acc = d.text;
          reply.textContent = acc;
        } else if (evt === "error") {
          el.querySelector(".thinking").classList.remove("on");
          reply.innerHTML = `<span class="err">The agent could not answer: ${escapeHtml(d.message)}</span>`;
        } else if (evt === "verdict") {
          el.querySelector(".thinking").classList.remove("on");
          reply.textContent = d.explanation;
          acc = d.explanation;
          state.history.push({ role: "assistant", content: d.explanation });
          renderProvenance(el, d.call);
          if (d.winner) {
            $("verdict-name").textContent = d.winner;
            $("verdict").hidden = false;
            renderOutcome(d.winner, state.vis[state.extension] || {});
          }
          const agree = $("agree");
          if (d.trv_winner && d.winner && !d.agrees) {
            agree.className = "agree split";
            agree.textContent =
              `The deterministic ledger ranks ${d.trv_winner} first, the agent would ` +
              `buy ${d.winner}. They disagree, and that is a finding rather than a ` +
              `bug — the ledger prices a stated customer policy, the agent does not.`;
          } else if (d.trv_winner) {
            agree.className = "agree ok";
            agree.textContent =
              "Same winner as the agent, arrived at without a model touching a number.";
          }
        }
      }
    }
  } catch (err) {
    el.querySelector(".thinking").classList.remove("on");
    reply.innerHTML = `<span class="err">Connection to the agent failed: ${escapeHtml(err.message)}</span>`;
  } finally {
    state.busy = false;
    $("send").disabled = false;
    $("request").focus();
  }
}


// ── the merchant's levers ───────────────────────────────────────────
/* The console used to offer two panels of controls and a merchant could act on
   neither: the adversary toggles are claims about our arithmetic, and the
   valuation sliders belong to the shopper. This panel is the merchant's own —
   one row per term they publish, and the ranking moves when they change it. */
async function loadLevers() {
  const d = await (await fetch("/api/levers")).json();
  state.levers = d.levers;
  if (state.published === null) state.published = new Set(d.levers.map((l) => l.id));

  $("lever-rows").innerHTML = d.levers
    .map(
      (l) => `<label class="lever" data-id="${escapeHtml(l.id)}">
        <input type="checkbox" class="levbox" ${state.published.has(l.id) ? "checked" : ""}>
        <span class="levtitle">${escapeHtml(l.title)}</span>
        <span class="levworth ${l.status === "signed" ? "signed" : ""}">${
          l.worth_aud ? "−$" + money(l.worth_aud) : "—"
        }</span>
      </label>`
    )
    .join("");

  document.querySelectorAll(".levbox").forEach((box) =>
    box.addEventListener("change", (e) => {
      const id = e.target.closest(".lever").dataset.id;
      if (e.target.checked) state.published.add(id);
      else state.published.delete(id);
      refreshStanding();
    })
  );
  refreshStanding();
}

/** Re-price with the merchant's current selection and say where they stand. */
async function refreshStanding() {
  const q = ledgerParams();
  const d = await (await fetch("/api/ledger?" + q)).json();
  renderLedger(d);

  const s = d.standing;
  const el = $("standing");
  if (!s || !s.position) {
    el.textContent = "not ranked";
    el.className = "standing";
    return;
  }
  const ord = ["", "1st", "2nd", "3rd"][s.position] || s.position + "th";
  el.textContent = `${ord} of ${s.of} · $${money(s.adjusted_cost_aud)} effective`;
  el.className = "standing " + (s.position === 1 ? "first" : "behind");

  const off = state.levers.filter((l) => !state.published.has(l.id));
  $("leverfoot").innerHTML =
    s.position === 1
      ? `You are the agent's pick at <b>$${money(s.adjusted_cost_aud)}</b> effective,
         from a <b>$${money(s.list_price_aud)}</b> sticker price you did not have to cut.` +
        (off.length
          ? ` And you are still holding back ${off.length} term${off.length > 1 ? "s" : ""}.`
          : "")
      : `You are <b>$${money(Math.abs(s.gap_aud))}</b> behind
         <b>${escapeHtml(s.leader_id)}</b>. ${
           off.length
             ? `Publishing what you have unticked would close ${
                 off.reduce((a, l) => a + l.worth_aud, 0) >= Math.abs(s.gap_aud)
                   ? "all of it"
                   : "some of it"
               }.`
             : `Everything you publish is already counted — this gap is a real price difference, not a legibility one.`
         }`;
}

// ── ledger ──────────────────────────────────────────────────────────
function ledgerParams() {
  const q = new URLSearchParams({
    tampered: $("tampered").checked,
    inflate: $("inflate").value,
    // The shopper's own valuation. /api/ledger has always accepted these four;
    // until now nothing sent them, so the sliders below the ledger were a
    // server-side feature with no way to reach it.
    fit: $("p-fit").value,
    ship: $("p-ship").value,
    warranty: $("p-warranty").value,
    penalty: $("p-penalty").value,
  });
  // Only the merchant's current selection reaches the agent. Omitting the
  // param entirely would mean "publish everything", which is a different claim.
  if (state.published) q.set("publish", [...state.published].join(","));
  return q;
}

async function loadLedger() {
  renderLedger(await (await fetch("/api/ledger?" + ledgerParams())).json());
}

function renderLedger(d) {
  $("ledger-body").innerHTML = d.valuations
    .map((v) => {
      const lines = v.lines
        .filter((l) => l.amount_aud !== 0 || l.status === "unverified" || l.status === "ineligible")
        .map(
          (l) => `<div class="line">
            <span class="amt">${l.amount_aud >= 0 ? "+" : "−"}${money(Math.abs(l.amount_aud))}</span>
            <span>${escapeHtml(l.label)}<br><span class="basis">${escapeHtml(l.basis)}</span></span>
            <span class="tag ${l.status}">${l.status}</span>
          </div>`
        )
        .join("");
      return `<div class="val ${v.merchant_id === d.winner ? "winner" : ""}">
        <div class="val-head">
          <span class="name">${escapeHtml(v.merchant)}</span>
          <span class="nums"><span class="from">$${money(v.list_price_aud)}</span>
            → <span class="to">$${money(v.adjusted_cost_aud)}</span></span>
        </div>
        ${lines}
        ${v.eligible ? "" : `<div class="excluded">excluded: ${escapeHtml(v.excluded_reason)}</div>`}
      </div>`;
    })
    .join("");
}

// ── repeats ─────────────────────────────────────────────────────────
async function loadRepeats() {
  const q = new URLSearchParams({ extension: state.extension });
  const d = await (await fetch("/api/repeats?" + q)).json();
  $("repeat-hint").textContent = d.n_recorded ? d.headline : "not recorded";

  const total = d.n_recorded || 1;
  const rows = Object.entries(d.counts)
    .map(
      ([who, n]) => `<div class="bar-row">
        <span class="who">${escapeHtml(who)}</span>
        <span class="bar-track"><span class="bar-fill ${who}" style="width:${(n / total) * 100}%"></span></span>
        <span class="bar-count">${n}/${d.n_recorded}</span>
      </div>`
    )
    .join("");

  const missing = d.n_attempted - d.n_recorded;
  $("repeat-bars").innerHTML =
    (rows || `<p class="not-recorded">No repeat was recorded.</p>`) +
    (missing
      ? `<p class="not-recorded">${missing} of ${d.n_attempted} runs have no fixture,
         so they are reported rather than counted. Record them with
         <code>scripts/seed_fixtures.py --repeats 5</code>.</p>`
      : `<p class="muted small">${d.n_recorded} runs, each with the merchants in a
         different order. ${d.unanimous ? "Unanimous." : "Split — shown as it fell."}</p>`);
}


// ── scoreboard: the standing question, not the one-off one ──────────
async function loadScoreboard() {
  $("score-hint").textContent = "running ten comparisons…";
  const d = await (await fetch("/api/scoreboard")).json();
  $("score-hint").textContent = d.off.comparisons
    ? `${d.off.won}/${d.off.comparisons} won off · ${d.on.won}/${d.on.comparisons} won on`
    : "not recorded";

  const bar = (c) => `<div class="score-cond">
      <span class="cond">extension ${escapeHtml(c.extension)}</span>
      <span class="condbar"><span class="condfill" style="width:${c.win_rate_pct}%"></span></span>
      <span class="condnum">${c.won} of ${c.comparisons} won</span>
    </div>`;

  const rows = d.reasons
    .map(
      (r) => `<div class="reason ${r.reached_agent ? "seen" : "hidden"}">
        <span class="ramt">$${money(r.value_aud)}</span>
        <span class="rtitle">${escapeHtml(r.title)}
          <span class="rstat ${escapeHtml(r.status)}">${escapeHtml(r.status)}</span></span>
        <span class="rseen">${r.reached_agent ? "reached the agent" : "never sent"}</span>
      </div>`
    )
    .join("");

  $("score-body").innerHTML =
    bar(d.off) + bar(d.on) +
    `<p class="score-note">${escapeHtml(d.note)}</p>` +
    `<p class="exlabel2">What the agent was never handed, priced by the ledger</p>` +
    rows +
    `<p class="muted small">Recoverable total counts <b>signed</b> lines only —
     a figure labelled recoverable must not include value that cannot be proved,
     which is why the provisional line above is listed and not added.</p>`;
}

// ── transcript ──────────────────────────────────────────────────────
async function openTranscript() {
  const d = await (await fetch("/api/transcript")).json();
  $("transcript-body").innerHTML = d.calls.length
    ? d.calls
        .map(
          (c, i) => `<div class="call">
            <h3>${i + 1}. ${escapeHtml(c.label)} — ${escapeHtml(c.model)}</h3>
            <div class="provenance">${
              c.served_from === "fixture" ? `replayed from ${escapeHtml(c.fixture)}` : escapeHtml(c.served_from)
            } · ${escapeHtml(c.provenance)}</div>
            <pre class="code">${escapeHtml(c.system)}</pre>
            <pre class="code">${escapeHtml(c.prompt)}</pre>
            <pre class="code">${escapeHtml(c.completion)}</pre>
          </div>`
        )
        .join("")
    : `<p class="muted">No model calls yet this session.</p>`;
  $("overlay").hidden = false;
}

// ── the switch ──────────────────────────────────────────────────────
function setExtension(on) {
  if (state.extension === (on ? "on" : "off")) return;
  state.extension = on ? "on" : "off";
  $("switch").setAttribute("aria-checked", String(on));
  $("switch-state").textContent = on ? "ON" : "OFF";

  // A capability change means the agent must re-query the merchants, so the
  // old thread is grounded in a catalog that no longer exists. Start a fresh
  // conversation and re-ask the last question — that single gesture is the
  // before/after, and it stays a real model call either way.
  // Re-ask the FIRST question, not the last. The last one is usually a
  // follow-up ("and what if it doesn't fit?") which carries no product terms,
  // so re-asking it into an empty thread searches the catalogue for nothing.
  const opening = state.history.find((m) => m.role === "user");
  clearThread();
  if (opening) {
    send(opening.content);
  } else {
    $("empty").hidden = false;
    clearMetrics();
  }
  if ($("drawer-repeats").open) loadRepeats();
}

// ── wiring ──────────────────────────────────────────────────────────
$("composer").addEventListener("submit", (e) => { e.preventDefault(); send(); });
$("switch").addEventListener("click", () => setExtension(state.extension !== "on"));
$("drawer-ledger").addEventListener("toggle", (e) => { if (e.target.open) loadLedger(); });
$("drawer-repeats").addEventListener("toggle", (e) => { if (e.target.open) loadRepeats(); });
$("drawer-scoreboard").addEventListener("toggle", (e) => {
  if (e.target.open && !e.target.dataset.loaded) {
    e.target.dataset.loaded = "1";   // ten model calls; run them once
    loadScoreboard();
  }
});
[["p-fit", "o-fit", (v) => `$${v}`],
 ["p-ship", "o-ship", (v) => `$${v}`],
 ["p-warranty", "o-warranty", (v) => `$${v}`],
 ["p-penalty", "o-penalty", (v) => `${Math.round(v * 100)}%`]].forEach(([id, out, fmt]) => {
  $(id).addEventListener("input", () => { $(out).textContent = fmt($(id).value); });
  $(id).addEventListener("change", loadLedger);
});
$("tampered").addEventListener("change", loadLedger);
$("inflate").addEventListener("change", loadLedger);
$("overlay-close").addEventListener("click", () => ($("overlay").hidden = true));

document.addEventListener("keydown", (e) => {
  if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT") {
    if (e.key === "Escape") $("overlay").hidden = true;
    return;
  }
  if (e.key === "ArrowRight") setExtension(true);
  else if (e.key === "ArrowLeft") setExtension(false);
  else if (e.key.toLowerCase() === "t") openTranscript();
  else if (e.key.toLowerCase() === "e") window.location.href = "/evidence";
  else if (e.key.toLowerCase() === "o") window.location.href = "/onboard";
  else if (e.key.toLowerCase() === "h") window.location.href = "/";
  else if (e.key === "Escape") $("overlay").hidden = true;
});

loadScenario();
loadLevers();

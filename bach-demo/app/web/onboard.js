/* /onboard — a four-step wizard, because a merchant arriving here does not
   know what BondLayer wants from them.

   One step is visible at a time and every step ends in a single button naming
   the next action. The alternative — one long scrolling page — was the first
   version, and it read as a report about a pipeline rather than as something
   the reader was being asked to do.

   Nothing on any step is authored copy about the system: issues come from
   catalog_adapter, drafts from a real policy_converter run, and every returned
   signature is verified server-side through a fresh KeyRing before this page
   sees it. The tick boxes are the approval gate itself. */

const $ = (id) => document.getElementById(id);
const esc = (s) =>
  String(s ?? "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));

let DATA = null;
let step = 1;
const approved = new Set();

const SEVERITY = {
  invisible: "an agent never sees this product at all",
  unmatchable: "an agent cannot line this product up against a competitor's",
  incomparable: "an agent can show this but cannot compare it",
};

// ── step machine ────────────────────────────────────────────────────
function show(n) {
  step = n;
  document.querySelectorAll(".wstep").forEach((s) => {
    s.hidden = Number(s.dataset.step) !== n;
  });
  document.querySelectorAll("#rail li").forEach((li) => {
    const d = Number(li.dataset.step);
    li.classList.toggle("on", d === n);
    li.classList.toggle("done", d < n);
  });
  window.scrollTo({ top: 0, behavior: "smooth" });
}

document.querySelectorAll("[data-back]").forEach((b) =>
  b.addEventListener("click", () => show(Number(b.dataset.back)))
);

// ── step 1: the merchant's own files ────────────────────────────────
function markFile(field, info) {
  const el = $("state-" + field);
  const drop = $("drop-" + field);
  if (info) {
    el.textContent = `${info.filename} · ${(info.bytes / 1024).toFixed(1)} kB`;
    drop.classList.add("has");
  } else {
    el.textContent = "using the sample file";
    drop.classList.remove("has");
  }
}

async function upload() {
  const form = new FormData();
  let any = false;
  for (const field of ["catalog", "policy"]) {
    const f = $("file-" + field).files[0];
    if (f) {
      form.append(field, f);
      any = true;
    }
  }
  if (!any) return { accepted: {} };

  $("upload-note").innerHTML = `<span class="muted">reading your files…</span>`;
  const r = await (await fetch("/api/onboard/upload", { method: "POST", body: form })).json();
  if (r.error) {
    $("upload-note").innerHTML = `<span class="err">${esc(r.error)}</span>`;
    return null;
  }
  for (const field of ["catalog", "policy"]) markFile(field, r.accepted[field]);
  $("reset-files").hidden = !Object.keys(r.accepted).length;
  $("upload-note").innerHTML = r.using_sample.length
    ? `Using your ${Object.keys(r.accepted).join(" and ")}; the sample stands in for the rest.`
    : `Both files are yours. Nothing of the sample retailer is left in this run.`;
  return r;
}

["catalog", "policy"].forEach((field) =>
  $("file-" + field).addEventListener("change", (e) => {
    const f = e.target.files[0];
    if (f) markFile(field, { filename: f.name, bytes: f.size });
  })
);

$("reset-files").addEventListener("click", async () => {
  await fetch("/api/onboard/reset", { method: "POST" });
  ["catalog", "policy"].forEach((f) => {
    $("file-" + f).value = "";
    markFile(f, null);
  });
  $("reset-files").hidden = true;
  $("upload-note").textContent =
    "Back to the sample retailer. Upload again at any time.";
  DATA = null;
});

$("go-1").addEventListener("click", async () => {
  $("go-1").disabled = true;
  $("go-1").textContent = "Analysing…";
  try {
    if ((await upload()) === null) return;
    DATA = await (await fetch("/api/onboard")).json();
    renderCatalog();
    renderDrafts();
    show(2);
  } finally {
    $("go-1").disabled = false;
    $("go-1").textContent = "Analyse my catalogue →";
  }
});

$("go-2").addEventListener("click", () => show(3));
$("go-3").addEventListener("click", () => {
  renderReview();
  show(4);
});

// ── step 2 ──────────────────────────────────────────────────────────
/* The first version of this screen listed parser events. That is a diagnosis,
   and a diagnosis on its own is a bill: it told a merchant they had a problem
   without telling them what to do. This one splits into work they must do and
   work already done, and hands back a corrected file. */

const SEVERITY_LABEL = {
  invisible: "invisible to agents",
  unmatchable: "cannot be matched",
  incomparable: "cannot be compared",
  fixed: "done",
};

function renderCatalog() {
  const c = DATA.catalog;
  $("csv-text").textContent = c.csv;
  $("download-fixed").href = c.fixed?.download || "#";

  if (c.error) {
    $("catalog-error").innerHTML = `<div class="callout warn">
      <h3>We could not read that file</h3>
      <p>${esc(c.error)}</p>
      <p class="fix">Go back and upload an export with those columns, or carry
      on with the sample — the rest of the flow does not depend on it.</p></div>`;
    ["catalog-nums", "todos", "autofixed", "fixed-table"].forEach((id) => ($(id).innerHTML = ""));
    return;
  }
  $("catalog-error").innerHTML = "";

  const todos = (c.todos || []).filter((t) => !t.auto_fixed);
  const auto = (c.todos || []).filter((t) => t.auto_fixed);
  const blocked = new Set(todos.flatMap((t) => t.products)).size;

  $("catalog-nums").innerHTML = `
    <div class="scorecell ok">
      <span class="scv">${c.offers.length}</span>
      <span class="scl">products ready for agents</span></div>
    <div class="scorecell ${auto.length ? "fix" : ""}">
      <span class="scv">${auto.length}</span>
      <span class="scl">things we corrected for you</span></div>
    <div class="scorecell ${todos.length ? "todo" : "ok"}">
      <span class="scv">${todos.length}</span>
      <span class="scl">${todos.length === 1 ? "job" : "jobs"} only you can do</span></div>
    <div class="scorecell ${blocked ? "todo" : "ok"}">
      <span class="scv">${blocked}</span>
      <span class="scl">${blocked === 1 ? "product" : "products"} still held back</span></div>`;

  $("todo-count").textContent = todos.length;
  $("done-count").textContent = auto.length;

  $("todos").innerHTML = todos.length
    ? todos.map(todoCard).join("")
    : `<p class="emptycol">Nothing is waiting on you. Every row mapped cleanly
       — unusual, and worth saying out loud.</p>`;

  $("autofixed").innerHTML = auto.length
    ? auto.map(todoCard).join("")
    : `<p class="emptycol">Nothing needed correcting.</p>`;

  renderFixedTable(c.fixed);
}

function todoCard(t) {
  return `<div class="todo ${esc(t.severity)}">
    <div class="todohead">
      <span class="todotick" aria-hidden="true">${t.auto_fixed ? "✓" : "☐"}</span>
      <span class="tt">${esc(t.title)}</span>
      <span class="tsev ${esc(t.severity)}">${esc(SEVERITY_LABEL[t.severity] || t.severity)}</span>
    </div>
    <p class="tdetail">${esc(t.detail)}</p>
    ${
      t.products && t.products.length
        ? `<div class="tprods">${t.products
            .map((p) => `<span class="tprod">${esc(p)}</span>`)
            .join("")}</div>`
        : ""
    }
    <p class="timpact">${esc(t.impact)}</p>
  </div>`;
}

function renderFixedTable(fixed) {
  if (!fixed || !fixed.rows.length) {
    $("fixed-table").innerHTML = "";
    return;
  }
  const cols = fixed.columns;
  const head = `<thead><tr>${cols
    .map((c) => `<th>${esc(c)}</th>`)
    .join("")}</tr></thead>`;

  const body = fixed.rows
    .map((r) => {
      const moved = new Set(fixed.changed[r.sku] || []);
      const needsAction = String(r.bondlayer_status || "").startsWith("ACTION");
      const cells = cols
        .map((c) => {
          const v = r[c] ?? "";
          if (c === "bondlayer_status") {
            return `<td class="statuscell ${needsAction ? "action" : "ok"}">${esc(v)}</td>`;
          }
          const cls = [moved.has(c) ? "moved" : "", v === "" ? "blank" : ""]
            .filter(Boolean)
            .join(" ");
          return `<td class="${cls}">${esc(v) || "—"}</td>`;
        })
        .join("");
      return `<tr class="${needsAction ? "rowaction" : ""}">${cells}</tr>`;
    })
    .join("");

  $("fixed-table").innerHTML = head + `<tbody>${body}</tbody>`;
}

/** The three-number strip used by step 3. */
function bignum(v, label, tone = "") {
  return `<div class="bignum ${tone}"><span class="bnv">${v}</span>
          <span class="bnl">${label}</span></div>`;
}

// ── step 3 ──────────────────────────────────────────────────────────
function draftCard(d, opts = {}) {
  const flagged = d.warnings.length > 0;
  return `<div class="draft ${flagged ? "flagged" : ""}" data-id="${esc(d.id)}">
    <label class="dapprove">
      <input type="checkbox" class="approve" ${approved.has(d.id) ? "checked" : ""}>
      <span>${opts.review ? "publish" : "approve"}</span>
    </label>
    <div class="dbody">
      <div class="dhead">
        <span class="dtitle">${esc(d.title)}</span>
        <span class="dtype">${esc(d.type)}</span>
        ${
          d.declared_bound_aud !== null && d.declared_bound_aud !== undefined
            ? `<span class="dbound">ceiling $${Number(d.declared_bound_aud).toFixed(2)}</span>`
            : ""
        }
        <span class="dsig none">unsigned</span>
      </div>
      <pre class="code small">${esc(JSON.stringify(d.facts, null, 2))}</pre>
      <p class="dquote">&ldquo;${esc(d.source_quote)}&rdquo;</p>
      ${
        flagged
          ? `<ul class="dwarn">${d.warnings.map((w) => `<li>${esc(w)}</li>`).join("")}</ul>`
          : `<p class="dok">quote found in your document · every fact carries a unit</p>`
      }
    </div>
  </div>`;
}

function wireApprovals(root) {
  root.querySelectorAll(".draft").forEach((card) => {
    const box = card.querySelector(".approve");
    box.addEventListener("change", () => {
      if (box.checked) approved.add(card.dataset.id);
      else approved.delete(card.dataset.id);
      // Both screens show the same records; keep the other one honest.
      document
        .querySelectorAll(`.draft[data-id="${CSS.escape(card.dataset.id)}"] .approve`)
        .forEach((other) => (other.checked = box.checked));
      tally();
    });
  });
}

function renderDrafts() {
  const p = DATA.policy;
  $("policy-prose").textContent = p.prose || "(no policy document)";

  if (p.error) {
    $("drafts").innerHTML = `<div class="callout warn"><h3>The converter could
      not run</h3><p>${esc(p.error)}</p></div>`;
    $("draft-nums").innerHTML = "";
    return;
  }

  // Clean drafts start ticked; flagged ones do not. The merchant's decision is
  // what the gate is for, so the default must never be "approve everything".
  approved.clear();
  p.drafts.forEach((d) => {
    if (!d.warnings.length) approved.add(d.id);
  });

  const flagged = p.drafts.filter((d) => d.warnings.length).length;
  $("draft-nums").innerHTML =
    bignum(p.drafts.length, "claims drafted from your words", "good") +
    bignum(flagged, "need your judgement", flagged ? "warn" : "good") +
    bignum(0, "signed so far", "");

  $("drafts").innerHTML = p.drafts.map((d) => draftCard(d)).join("");
  wireApprovals($("drafts"));
}

// ── step 4 ──────────────────────────────────────────────────────────
function renderReview() {
  const drafts = DATA.policy.drafts || [];
  $("review").innerHTML = drafts.map((d) => draftCard(d, { review: true })).join("");
  wireApprovals($("review"));
  tally();
}

function tally() {
  const n = approved.size;
  const total = (DATA?.policy?.drafts || []).length;
  const hint = $("signhint");
  if (hint) {
    const left = total - n;
    hint.textContent = left
      ? `${n} of ${total} ticked. The other ${left} ${left === 1 ? "stays" : "stay"} unsigned, and no agent will value ${left === 1 ? "it" : "them"}.`
      : `All ${total} ticked. Untick anything you would not stand behind.`;
  }
  const btn = $("sign");
  if (btn) btn.disabled = n === 0;
}

async function sign() {
  $("sign").disabled = true;
  $("signed").innerHTML = `<p class="muted">signing…</p>`;
  const d = await (
    await fetch("/api/onboard/sign", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ merchant: DATA.merchant_id, approved: [...approved] }),
    })
  ).json();

  const allGood = d.signed.every((s) => s.verifies);
  $("signed").innerHTML =
    `<p class="exlabel">Signed and ready to serve</p>` +
    d.signed
      .map(
        (s) => `<div class="sigrow">
          <span class="verdictchip ${s.verifies ? "pass" : "fail"}">${
            s.verifies ? "VERIFIES" : "FAILS"
          }</span>
          <div>
            <div class="cname">${esc(s.title)}</div>
            <div class="cdetail">${esc(s.signature)}</div>
          </div>
        </div>`
      )
      .join("") +
    `<p class="fnote">${esc(d.note)} Each signature was verified back through a
     fresh <code>KeyRing</code> on the server before it reached this page —
     ${allGood ? "all of them check out." : "one did not."}</p>
     <div class="donebox">
       <h3>That is the whole integration.</h3>
       <p>These records are now what <code>catalog.search</code> returns when a
       shopping agent negotiates the
       <code>org.bondlayer.benefit_value</code> capability. You did not write a
       line of code and nothing was published without your tick.</p>
       <a class="primary" href="/demo">Watch an agent read them &rarr;</a>
     </div>`;

  $("sign").disabled = false;
}

$("sign").addEventListener("click", sign);

// ── boot ────────────────────────────────────────────────────────────
(async () => {
  show(1);
  try {
    const s = await (await fetch("/api/scenario")).json();
    $("banner").innerHTML =
      `sample retailer: <b>${esc(s.focus_merchant.name)}</b> · ` +
      `your files are read in memory and never written to disk`;
  } catch {
    $("banner").textContent = "";
  }
})();

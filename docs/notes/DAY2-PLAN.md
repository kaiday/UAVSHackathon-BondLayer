# Day 2 plan — steering, sub-agents, and the 13:00 freeze

*Written 12/09 16:30 AEST against `origin/round2/dev` at `883988c`. Steering: Claude, under Ford. Every
status claim here was verified by running the code, not by reading the docs.*

**Official deadline:** 17:00 on 13/09 AEST (Rulebook §C.1). **Team freeze:** 13:00. Nothing new enters the
product after 13:00; the afternoon is clean-clone, deck, video, submission.

---

## 0. How to read this

- §1 is what is true right now. If you disagree with a line, run the command next to it.
- §2 is the four decisions only Ford can make. Everything in §4 assumes the defaults stated there.
- §3 is the operating model: how humans, sub-agents and steering fit together without breaking a rule.
- §4 is the workstreams. Each one is a self-contained brief a sub-agent can be launched with as-is.
- §5 is the clock, with the kill criteria at each checkpoint.
- §6 is the steering loop: what gets merged, in what order, and the evidence required for each merge.
- §7 is the submission checklist.

---

## 1. Verified state at 16:20

| Fact | Evidence |
|---|---|
| Everything is merged into `round2/dev`; all five feature branches are 0 ahead | `git rev-list --count origin/round2/dev..origin/feat/<x>` = 0 for all |
| Local `main` is 77 commits behind `round2/dev` | `git rev-list --count origin/main..origin/round2/dev` |
| `bondlayer/` suite: **95 pass** | `pytest` in `bondlayer/` after installing `python-multipart` and `pypdf` |
| `round2/tests`: **9 pass** | `pytest tests` in `round2/` |
| Fresh clone + `pip install -e .` + `pytest` **fails at collection** | `python-multipart` and `pypdf` are imported but declared nowhere; `pyproject.toml` has no `dependencies` at all |
| The interpreter's `resolve()` returns `[]` | `bondlayer/src/bondlayer/interpreter/resolver.py`, 19 lines, marked "integration stub only" |
| The composition root runs with **no interpreter wired** and passes the utterance through as a keyword query | `composition.py` emits `Step(Phase.INTENT, Outcome.ABSENT, …)` |
| Only R01 has a parser test; no run over the 30 frozen requests exists | `tests/test_interpreter.py` has 2 tests; `grep -l requests.json` finds no runner |
| `buyer-agent` runs its **own** merchant service on :8000 with **copied** data; all 5 copies have drifted | `cmp` on `electronics.csv`, `manifests.json`, both `*.signed.json`, `voltway.pub.json` |
| The chat agent needs a **live OpenAI key**, raises without one, and lets the LLM rank ("no effective cost computed") | `buyer-agent/src/agent/llm.py:53-61`, `main.py:255-283` |
| Bundling, checkout settlement, negotiation: not started | no `Bundler`; README "Not attempted" |
| Top-level `README.md` is two lines; no deck; no Problem Setter notes; no market-strategy artefact | `wc -l README.md` = 3 |
| 18 commits authored `unknown <ltb1002.edmail@gmail.com>` | `git log --format='%an <%ae>' \| sort \| uniq -c` |
| `demo/` and `bach-demo/` are Round 1 spike code committed 02/09, before the 09:00 12/09 cutoff | `git log --before="2026-09-12 09:00 +1000"`; `bach-demo/README.md` says "not submission code", `demo/` says nothing |

What is real and strong: adapter with 302 recorded diagnostics, UCP head with capability negotiation on one
code path (control = same server, extension absent), ES256 over canonical JSON verifying from published
public keys, valuation that credits only verified records and caps by ceiling, the flip held by test on R01
and R21, policy onboarding behind an approval gate, a merchant dashboard that reads only from the API.
That is criterion 2 (technical architecture) and criterion 3 (business value) largely done.

What is missing is criterion 1, the one FPT weights highest: **decode intent, match semantically, justify.**

---

## 2. Decisions — **ruled by Ford, 16:25 on 12/09. Settled; do not reopen.**

| # | Decision | Ruling | Consequence |
|---|---|---|---|
| **D1** | Demo path | **A.** The chat-app agent + UI stays as the buyer-agent stand-in, repointed at the `bondlayer/` server; its copied merchant, valuation, keys and data are **deleted**, not synced; ranking is deterministic effective cost; the LLM is optional. **B** (trace CLI + dashboard) is built first as insurance and is the 11:00 fallback. | `bondlayer/` is the product. One `pyproject` named `bondlayer`. Bach's verification *audit* (what verified / was ignored / why) is rendered **alongside** effective cost, never instead of it. |
| **D2** | Code overnight? | **Yes.** Sub-agents and humans may write code 17:00 → 09:00. | Small commits, honest timestamps and messages, human author on every commit. Never batch a night into one push — that is the pre-written-code pattern. WS-A starts tonight. |
| **D3** | Who merges | **Steering merges, only after the named human owner has approved in writing** (one line in the channel). Nobody merges their own workstream. | The human owner must be able to explain the diff in Q&A (Rulebook §C.5.b: AI tooling only with the team's oversight and understanding). |
| **D4** | LLM in the demo | **Optional prose only.** Ranking is deterministic. No key → template sentence, said so in the trace. Never a network call on the ranking path. | `llm.py` never raises on a missing key. |
| **D5** | `bach-demo/`, `demo/` | **Move to `archive/pre-hackathon-spikes/`** with a README declaring them Round 1 spike code (committed 02/09), not submission code, and listing what was reused as the rules allow (schema ideas, prompts, demo script). | WS-C step 6. |
| **D6** | Dynamic bundling | **In scope as a 🟡 workstream (WS-G)**, ships partially if needed — a bundle of one is valid. `Bundler` protocol lands on `types.py` from steering before WS-G starts. | Named twice in the problem statement; the worked example ends on it. |

**Source-of-truth order when documents disagree:** submitted Round 1 `main.tex` → `bondlayer/docs/stage1-agent-ready-catalog.md` → `types.py` → `WORKPLAN.md` → handover. Note: the submitted text already says **ES256** (the handover's Ed25519/PyNaCl is the stale one); `overview-progress.md` §4.1 has this backwards.

---

## 3. Operating model

**Three roles.**

- **Human owner** per workstream (Nha, Hieu, Nguyen, Bach, Minh). Reads every diff their agent produces,
  answers the agent's questions, approves the PR, and owns that code in Q&A on the 20th.
- **Sub-agent** per workstream. Runs in its own git worktree branched from `origin/round2/dev`, on a
  `feat/<owner>-d2-<topic>` branch. Commits small and often. Opens a PR with evidence attached.
- **Steering** (Claude, under Ford). Launches agents with the briefs in §4, holds the clock in §5, reviews
  every PR against its done-when, runs the full suite plus the clean-clone check on every merge, keeps the
  pitch numbers traceable to a commit, and calls the kill criteria out loud.

**Rules every agent is launched with.**

1. Branch from `origin/round2/dev`, never from local `main`. Never push to `round2/dev` or `main`.
2. Never edit `bondlayer/src/bondlayer/types.py`. A contract change is a message to steering first.
3. Zero network calls at runtime. `pip install` during setup is fine. No key generation; keys ship from `keys/`.
4. Never change `data/eval/requests.json`, the gold sets, or the frozen catalogue. If the eval says the
   product is wrong, the product is wrong.
5. Stay inside the files the brief names. Anything else is a question to steering.
6. Every PR carries: the command that proves done-when, its output, and the count of tests before and after.
7. Commit messages end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. The human owner's
   git identity is on the commit. Bach: run `git config user.name` and `user.email` before the first commit
   tomorrow; the 18 "unknown" commits stay as they are, we do not rewrite history.
8. If a brief's time box expires, stop, push what is green, and report. Partial and honest beats late.

**Steering never writes feature code.** Steering writes glue only when a merge needs it, and says so in the PR.

---

## 4. Workstreams

Priority order is the order below. If two agents need the same person, the higher one wins.

### WS-A · Intent resolution and the evaluation run — **Hieu** · 🔴 criterion 1

**Objective.** Replace the resolver stub with real constraint resolution over the catalogue and the verified
records, wire it into the composition root, and produce the two pitch numbers from the 30 frozen requests.

**Read first.** `bondlayer/src/bondlayer/types.py` (contract, read-only) · `interpreter/parser.py` ·
`agent/composition.py` and `agent/trace.py` · `data/eval/requests.json` and `data/eval/taxonomy.md` ·
`adapters/catalog.py` (what attributes exist and how derived ones are marked) · `ucp/records.py` ·
`tests/test_flip.py` (how the catalogue and verified records are loaded in tests).

**Build.**

1. `interpreter/resolver.py` — `resolve(constraints, skus, records) -> list[Proposal]`, per kind:
   - **HARD.** Category tokens → `sku.category`. Price ceiling → `shelf_price <= ceiling`. Spec tokens
     (`ram_gb`, `storage_gb`, `screen_in`, `weight_kg`, `gpu`) → typed attribute compare. A listing that
     lacks the attribute a HARD constraint needs is **excluded**, and the exclusion reason is kept for the
     trace ("attribute absent", not "failed"). Derived attributes (`gpu_source == "title"`) are accepted and
     the note says they were derived.
   - **SOFT.** Never filters. Produces an ordering signal and a note ("light" → ascending `weight_kg`;
     "for video editing" → `ram_gb`, `gpu` present; "cheapest" → shelf price). A SOFT clause with no
     attribute heuristic is resolved `satisfied=False` with the note below, not dropped.
   - **SERVICE.** Phrase → `BenefitType` (returns → free returns, warranty, delivery, trade-in). Satisfied
     iff a record of that type applies to the SKU (`sku_id` match or `None` = whole merchant). Cite
     `evidence_record_id`. The resolver **only cites records it is handed**; the caller hands it verified
     records only. Unverified records never reach the resolver.
   - **VALUES.** Same mechanism, types sustainability / repairability / durability. Cited exactly like
     SERVICE. Valuation, not the resolver, decides it is worth $0.
   - Any SERVICE or VALUES clause with no record → `ResolvedConstraint(satisfied=False, evidence_record_id=None,
     evidence_attribute=None, note="← no catalogue attribute answers this")` **and** appended to
     `Proposal.unsatisfied`. That exact marker string is rendered by Minh; do not paraphrase it.
   - Every `ResolvedConstraint.note` is one human-readable sentence. No empty notes. FPT asked for a
     justification, not a SKU list.
   - Proposal order: HARD pass → SOFT signal → count of satisfied SERVICE+VALUES → shelf price ascending.
     Valuation reorders by effective cost afterwards; that is the composition root's job, not yours.
2. Wire it: `composition.run_request` accepts an `interpret` callable; when present, `Phase.INTENT` is
   `Outcome.OK` with the parsed constraints in the step detail, and the search query sent to merchants is
   built from the HARD constraints (category, `max_price`), not the raw utterance. Keep the ABSENT path
   working when it is not passed.
3. `scripts/eval_run.py` — deterministic, offline. For each of the 30 requests, run parse → resolve twice:
   **BondLayer** (verified records from `data/records/*.signed.json`, checked against `keys/*.pub.json`) and
   **control** (no records). Report per request and in total:
   - *hard precision*: share of returned proposals whose SKU is in `gold_skus`;
   - *gold recall*: share of `gold_skus` present in the returned proposals;
   - *citation precision*: share of `evidence_record_id`s that exist and verify (must be 1.00; if it is not,
     that is a bug, not a number to report);
   - *unsatisfied honesty*: every request with `expect_unsatisfied: true` returns a non-empty `unsatisfied`;
   - *answerable share*: SERVICE+VALUES clauses answered, BondLayer vs control (control should be near 0).
   Write `bondlayer/docs/eval-results.md` with the commit hash, the command, and the table. Also emit
   `bondlayer/data/eval/reports/<id>.json` shaped as `RequestReport` for WS-E to render.
4. Tests: `tests/test_resolver.py` (R01 resolves to four typed constraints with two cited and two answered
   from records; R12 is not won by the unsigned northgear claim; a request with `expect_unsatisfied` reports
   it) and `tests/test_eval.py` (all 30 parse and resolve without exception; citation precision is 1.00).

**Done when.** `pytest` in `bondlayer/` is green with the new tests; `python scripts/eval_run.py` prints the
table and writes the two files; `python -c` running `run_request` on R01 with the interpreter wired shows
`Phase.INTENT` as `OK`; the 95 existing tests still pass. Evidence: paste the table.

**Forbidden.** Editing `types.py`. Substring matching on `title` (the adapter already lifted the tokens
that matter into attributes; use those). Any network or model call. Touching `requests.json`.

**Time box.** 09:00–10:45 build · 10:45–11:00 Hieu reviews · 11:00–11:30 final eval run on merged data.
**Kill criterion at 10:30.** If SOFT is not done, ship HARD + SERVICE + VALUES with every SOFT clause
resolved as unsatisfied-with-note. Do not slip the eval run.

**If D2 = yes tonight:** start at 17:00. This is the stream that most benefits from the extra hours.

---

### WS-B · One demo, one truth — **Bach** (agent side) and **Minh** (surfaces) · 🔴

**Objective.** The judged demo exercises the code the tests prove. One merchant server, one data set,
deterministic ranking, no mandatory network.

**Part 1 — insurance first (both paths).** `bondlayer/scripts/trace_run.py "<utterance>" [--control]` runs
`run_request` end to end against the in-process server (use FastAPI `TestClient` as the fetcher, the way
`test_composition.py` does) with the interpreter from WS-A when available, and prints the `AgentRun` as a
readable trace: constraints parsed → merchants queried → extension negotiated or absent → records seen /
verified / unverified → credited arithmetic → ranking, with the flip named. This is the Path-B demo and the
backup for Path A. Done when R01 prints Voltway winning with the extension and not winning with `--control`.

**Part 2 — Path A (default per D1).** In `buyer-agent`:

1. Delete `src/merchant/` and `data/` (all of it). The merchant is `bondlayer/`'s server. Add
   `bondlayer` as a dependency (`pip install -e ../../bondlayer`, and say so in `requirements.txt`).
2. `src/agent/ucp_client.py`: base URL from `BONDLAYER_MERCHANT_URL`, default `http://127.0.0.1:8000`.
   Verification keys come from each merchant's `/.well-known/ucp` `signing_keys[]`; verify with
   `bondlayer.records.signing`, not a local copy.
3. `src/agent/main.py` `/query`: call `bondlayer.agent.composition.run_request` with an HTTP fetcher.
   Ranking and credited amounts come from the returned `AgentRun`, never from the model. The LLM, if a key
   is present, writes one paragraph of prose from the trace. If no key, a template sentence and a trace
   step saying "prose: template (no model key)". `llm.py` must never raise on a missing key.
4. The toggle maps to `extension=True/False` on `run_request`. Same code path, one flag.
5. UI (`src/agent/static/index.html`): header label **"Buyer-agent stand-in — not a consumer product"**.
   Two panes, one switch, same query: control on the left, BondLayer on the right. Per record, three
   visually distinct states: signed+priced (cited, credited $X) · signed+unpriced (cited, **$0**) ·
   unsigned (shown, **never cited**, greyed with the reason). SERVICE and VALUES rows carry the marker
   `← no catalogue attribute answers this` when unanswered. Render the trace phases in order.
6. One test: `/query` with a mocked fetcher and no key returns a ranking, the trace, and a prose string.

**Done when.** With `OPENAI_API_KEY` unset and wifi off: start `bondlayer/run_server.py` and
`python -m src.agent.main`, submit R01 with the toggle on → Voltway wins with credited value shown; toggle
off → cheapest shelf wins and `extensions` is absent from every merchant response in the log. Evidence:
two screenshots and the test output.

**Forbidden.** A second merchant implementation. A second copy of any data file. Ranking by model.
`raise` on a missing key.

**Time box.** Part 1 by 10:00. Part 2 by 11:00. **Kill criterion at 11:00.** If Part 2 is not green,
Path B is the demo, the chat app is removed from the README's run instructions, and Minh moves to WS-E.

---

### WS-C · Deployability: one command, clean clone — **Nguyen** · 🟡 20 points, cheap

**Objective.** A judge on a laptop that has never seen the repo gets to the demo in under five minutes with
one command, and a script proves it.

**Build.**

1. `bondlayer/pyproject.toml`: add `[project] dependencies = [fastapi, uvicorn, pydantic, cryptography,
   httpx, python-multipart, pypdf]` and `[project.optional-dependencies] dev = [pytest]`. Mirror in
   `requirements.txt`. Unpinned lower bounds, per the Python 3.14 note already in the chat-app file.
2. Repo-root `run.sh` (and `run.ps1`): create `.venv`, install `bondlayer` editable (and the chat-app
   requirements if Path A), start the merchant server on :8000 and the agent on :8001, print the URLs.
   Idempotent; safe to run twice.
3. `scripts/clean_clone_check.sh`: `git clone` the repo into a temp dir, run `run.sh` in check mode,
   `pytest`, then curl `/voltway/.well-known/ucp`, a plain search, a search with the extension header, and
   `/onboard/merchants`; assert the plain response has no `extensions` key and the other does. Non-zero exit
   on any failure. Steering runs this on every merge and once more at 13:00 on a second laptop.
4. Fix `bondlayer/README.md` test count (says 35; suite is 95+), and the `docs/notes/README.md` folder tree,
   which describes directories that do not exist. Remove `docs/notes/IMPLEMENTATION-SUMMARY.md`,
   `ISSUE-18-SUMMARY.md` and the `ISSUE_15_*` files from the root of the story or fold their one useful
   paragraph each into the README; they read as scaffolding.
5. Ports: `bondlayer` :8000, agent :8001, nothing else. Delete Windows launch scripts that start the
   removed merchant.
6. **D5:** `git mv bach-demo archive/pre-hackathon-spikes/bach-demo` and `git mv demo
   archive/pre-hackathon-spikes/demo`; write `archive/README.md` declaring them (dates, "not submission
   code", what was reused as spec/data/prompt per the rules). Fix `CLAUDE.md` / `AGENTS.md` to point at
   `docs/FPT-Problem-Statement-Final.pdf` and copy the rulebook PDF into `docs/`.

**Done when.** `scripts/clean_clone_check.sh` exits 0 from a directory outside the repo, on Python 3.12 and
3.13. Evidence: the script output.

**Time box.** Dependency fix is a 10-minute PR and merges **first**, 09:30 at the latest. Rest by 11:00.
**If D2 = yes tonight:** the dependency PR and `run.sh` are boilerplate; do them tonight.

---

### WS-D · Documentation, market strategy, Problem Setter notes — **Nha** · 🟡 25 + 10 points

**Objective.** The README is the submission. Right now it is two lines.

**Build.**

1. Root `README.md`, in this order:
   - One paragraph: the B2A shift, merchant-side, what BondLayer publishes and why at `catalog.*` not
     `checkout`. The positioning line: *"In a room full of agents, we are building the thing agents read."*
   - Architecture: one Mermaid diagram (buyer agent → UCP → BondLayer server → adapter / records / policy
     onboarding → merchant data), then a component table with file paths.
   - Technologies and APIs used, and **every external resource declared** (Rulebook §C.5.b): Python,
     FastAPI, cryptography (ES256), React vendored, UCP spec version and the reserved `dev.ucp.*`
     namespace, OpenAI (optional, prose only), synthetic catalogue authored 12/09, no third-party dataset.
   - Run it: the one command from WS-C, then the demo script for R01 with what to look at.
   - Evaluation: the table from WS-A, with the commit hash and the command. Say "30 requests, frozen at
     10:50 on 12/09 before the feed existed." Never a number that is not in `eval-results.md`.
   - **Market strategy** (25 points): customer segment (mid-market retailers with a catalogue export and a
     policy PDF, no integration team); value model (publishing layer, per-merchant subscription, no per-
     transaction take); competitive analysis versus schema.org rich snippets, Shopify's agentic storefront,
     Talon.One UIP, and raw UCP adoption; distribution (systems integrators such as FPT, e-commerce
     agencies, platform app stores); roadmap (Q4 pilots → certification → agent-side SDK).
   - Deployability and scale: stateless publishing layer, cache-friendly signed records, cost per merchant,
     scale by merchant count not shopper count, because the merchant never sees the comparison.
   - Security and privacy: signed records, public keys in the profile, shopper policy never leaves the
     agent, no PII on the wire.
   - Problem Setter input and what changed (link the notes file).
   - Deliberately not attempted: real payments, production auth, live merchant integration, protocol
     certification, bundling, negotiation, the 100-request set.
   - Repo map, with this paragraph verbatim in spirit: `demo/` and `bach-demo/` are the **Round 1
     feasibility spike (committed 02/09, before the hackathon)** kept for reference only; **no submitted
     code imports from them**; the product is `bondlayer/` and `buyer-agent/`.
   - Team, with roles.
2. `docs/notes/PROBLEM-SETTER-NOTES.md`: what FPT said in the 15:30 window and the concrete change each point
   caused. **Nha dictates the content; the agent only formats it.** If nothing was noted, write down what
   was asked and answered from memory tonight, while it is fresh.
3. `docs/notes/system-architecture.md` rewritten to describe what exists, not the plan.
4. `docs/notes/PITCH-OUTLINE.md`: ten minutes, in the FPT criterion order: the query → the decode → the match
   with justification → the wire with and without the extension → the flip → the dashboard's "why we lost"
   → market → ask. Q&A drill list, with Q2 (Talon.One / UIP) answered in three sentences.
5. Fix `CLAUDE.md`: it points at `round1/fpt.md`, which does not exist; point at
   `docs/FPT-Problem-Statement-Final.pdf`.

**Done when.** A person who has not seen the repo can follow the README from clone to the R01 demo, and
every rulebook output requirement (§C.3) has a section. Evidence: steering does the walk-through.

**Time box.** Draft tonight (docs are safe under D2). Numbers slot in at 11:30. Final by 12:15.

---

### WS-E · Merchant dashboard: "why we lost" — **Minh** · 🟡 criterion 3 and the e-commerce-lead line

**Objective.** The dashboard already shows readiness and diagnostics. Add the per-request view: exactly four
figures and a sentence.

**Build.**

1. `ucp/onboard.py`: `GET /onboard/requests` (list) and `GET /onboard/requests/{id}?merchant=…` serving the
   `RequestReport` JSON that WS-A's eval runner writes to `data/eval/reports/`. Static files read at
   startup; no computation in the route.
2. `app/dashboard/`: a "Requests" tab. Per request: **fields exposed · legible share of the real offer ·
   verified value credited · value withheld by the wire**, then one line: *why we lost* or *why we won*,
   from `lost_because`. Three-way layout, one row per merchant, the control marked as such.
3. Keep the analytics tab labelled "demo only, no data" exactly as it is.

**Done when.** Switch merchant, pick R01, the four figures render from the API and match
`eval-results.md`. Evidence: screenshot plus the JSON.

**Time box.** 10:00–11:30, after WS-A's report schema lands (the schema is `RequestReport` in `types.py`;
build against a hand-written fixture until the real files exist). Only if WS-B Part 2 is not consuming Minh.

---

### WS-G · Dynamic bundling — **Nguyen** (compose) + **Minh** (render) · 🟡 criterion 2, named twice

**Objective.** Against a decoded intent, propose a *set* with a rationale for why the items belong
together — the problem statement's worked example ("beginner-friendly podcasting gear → the ideal bundle").

**Read first.** `types.py` (`Bundle`, `Bundler` — read-only) · WS-A's `Proposal` output · `ucp/server.py::_respond`.

**Build.**

1. `bondlayer/src/bondlayer/bundle/compose.py` implementing `Bundler.compose(constraints, proposals)`:
   groups complementary categories from the *same merchant* against the intent (laptop + warranty add-on +
   accessory; phone + accessory + trade-in-eligible), never re-does matching, emits `Bundle` with
   `combined_shelf_price` and a `rationale` about **togetherness** (not per-item fit — that is in each
   item's notes). A bundle of one is the degenerate case when nothing complements the best match.
2. Served as a `bundles[]` block inside the benefit extension in `catalog.search` responses — negotiated
   like everything else (additive change to `_respond`, Nguyen approves).
3. Composition root: `run_request` accepts an optional `bundler`; `Phase.BUNDLE` step in the trace.
4. Rendered as a **set** in the chat app and the trace CLI: combined price, rationale, each item's cited
   notes underneath. If it looks like three stacked search results, the criterion is lost on screen.
5. Tests: podcasting-style request over the audio/accessory categories yields a multi-item bundle with a
   non-empty rationale; a request with a single viable SKU yields a one-item bundle.

**Done when.** R01 and one audio request show a bundle in the trace CLI and the UI. Evidence: trace output.

**Forbidden.** Re-matching inside the bundler. Editing `types.py`. Cross-merchant bundles.

**Time box.** Starts when WS-A's resolver is mergeable (tonight if D2 lets it). **Kill at 11:00**: if not
green, ship a one-item bundle path only and say "bundling composes from matches; one merchant, one
complement type" in the pitch.

---

### WS-F · Pitch deck and backup video — **Nha + Minh** · after the 13:00 freeze

1. Deck from `PITCH-OUTLINE.md`, numbers only from `eval-results.md`, screenshots from the frozen build.
   Plain template; the deck is judged on the 20th, the product is judged on the 13th.
2. Backup video: the R01 demo, toggle off then on, then the dashboard, under three minutes, recorded from
   the clean clone, not the dev checkout.
3. Submission form: repository link (public), README, deck, demo link or video.

---

## 5. The clock

| Time | Checkpoint | Steering does | Kill criterion |
|---|---|---|---|
| **Tonight 16:30–17:00** | D1–D6 ruled (§2). Plan + `Bundler` committed to `round2/dev`. Worktrees cut. Briefs handed out. Bach's git identity set. Problem Setter notes dictated. | Commits this file and `types.py`, cuts worktrees from `round2/dev`, launches WS-A, WS-B Part 1, WS-C, WS-D. | — |
| **Tonight 17:00–22:00 (D2 = yes)** | WS-C deps + `run.sh` + archive move; WS-B Part 1 (trace CLI) then Part 2; WS-A resolver; WS-D README draft. WS-G once WS-A is mergeable. | Merges in order: WS-C deps → WS-B Part 1 → WS-A → WS-B Part 2. Runs suite + clean-clone on each. Posts one line per merge. | Anything not green by 22:00 continues Day 2 09:00 from its branch; nothing is force-finished at night. |
| **09:00** | All agents launched with §4 briefs. Humans at their laptops reading diffs. | Confirms each agent is on the right base commit. | — |
| **09:30** | WS-C dependency PR merged. Clean-clone check passes on `round2/dev`. | Runs `clean_clone_check.sh`. | If it fails, nothing else merges until it passes. |
| **10:00** | WS-B Part 1 (trace CLI) merged. | Runs R01 both ways, pastes the output in the channel. | If not green: Path B is at risk too; Bach stops UI work and finishes the CLI. |
| **10:30** | WS-A status. | Reads the resolver diff with Hieu. | SOFT unfinished → ship HARD+SERVICE+VALUES; SOFT resolved as unsatisfied-with-note. |
| **11:00** | **D1 confirmed by evidence.** WS-A merged. WS-B Part 2 green or not. | Runs the eval on merged `round2/dev`. Freezes the numbers. | Part 2 not green → Path B. README run instructions drop the chat app. Minh to WS-E. |
| **11:30** | WS-E merged. Numbers into README. | Second eval run must reproduce the first exactly. | Any drift between runs is a bug; the pitch uses the reproduced number. |
| **12:00** | Docs merged. Last feature PR closed. | Full suite + clean-clone on `round2/dev`. | — |
| **12:30** | `round2/dev` → `main`, tagged `round2-submission`. | Merge, tag, push. | — |
| **13:00** | **Freeze.** Clean clone from `main` on a second laptop passes. | Runs the walk-through from the README, cold. | Anything found here is fixed as a doc fix only, never a feature. |
| 13:00–15:00 | Deck, video, second rehearsal. | Watches the rehearsal against the outline. | — |
| 16:00 | Submission sent. | Confirms the form has all four outputs. | Hard deadline 17:00. Sixty minutes of buffer is the plan, not slack. |

---

## 6. Steering loop

**Merge order** (each gated on the previous being green): WS-C deps → WS-B Part 1 → WS-A → WS-B Part 2 or
Path B decision → WS-E → WS-D → numbers → `main`.

**On every PR**, steering:

1. Checks the base commit is on `round2/dev` and the diff touches only the files the brief names.
2. Re-runs the done-when command itself; does not trust the pasted output.
3. Runs `pytest` in `bondlayer/` and `round2/`, and `scripts/clean_clone_check.sh`.
4. Confirms the named human owner has approved in writing.
5. Merges with a merge commit (never squash: the trail is our authenticity evidence), and posts one line:
   what merged, the test count, the clean-clone result.

**Numbers policy.** A number appears in the README or the deck only if it is in `eval-results.md` with a
commit hash, and steering reproduced it. The 302 diagnostics and 81.2 readiness figures were re-verified at
`65cf96d`; re-verify at the freeze commit and update the hash.

**Ambiguity policy.** An agent that hits a contract question stops and asks steering. Steering answers in
the channel so the humans see it. If the answer changes `types.py`, it is one commit straight onto
`round2/dev`, and every worktree rebases.

**Steering's own commands.**

```bash
git fetch origin && git checkout -B round2/dev origin/round2/dev
cd bondlayer && pytest -q && python scripts/eval_run.py && cd ..
scripts/clean_clone_check.sh
```

---

## 7. Submission checklist (Rulebook §C.3)

- [ ] Product demo that runs live: `run.sh` from a clean clone of `main` at tag `round2-submission`
- [ ] `README.md`: architecture, technologies and APIs, external resources declared, install and run
- [ ] Repository link, public or shared with the Organising Committee
- [ ] Pitch deck attached
- [ ] Demo video as backup
- [ ] Spike folders labelled as pre-hackathon reference in the README
- [ ] Problem Setter notes committed
- [ ] Every commit after 09:00 12/09 has a human author; agent commits carry the trailer
- [ ] No code path requires a network call or an API key

---

## 8. Risks, ranked

1. **WS-A is the whole of criterion 1 and it is one person's morning.** Mitigation: the 10:30 kill
   criterion, and D2 = yes would buy it the evening.
2. **Two demos diverge again.** Mitigation: the data copies are deleted, not synced. One merchant server.
3. **A judge's laptop.** Mitigation: `clean_clone_check.sh` on two machines and two Python versions.
4. **Wifi.** Mitigation: nothing on the ranking path touches the network; the LLM is prose-only and optional.
5. **Authenticity questions.** Mitigation: small commits, human authors, spike folders labelled, and the
   human owner can explain every file in their workstream.

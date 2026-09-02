"""FastAPI backing the v2 demo page (demo-flow-v2 §4).

One screen: a shopper chat beside the merchant's console, and one switch that
flips both. This module owns no presentation logic -- every number it returns
comes from `src/bondlayer/`.

    python run_demo.py web
"""

from __future__ import annotations

import json
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import uvicorn  # noqa: E402
from fastapi import Body, FastAPI, File, Query, UploadFile  # noqa: E402
from fastapi.responses import (  # noqa: E402
    FileResponse,
    PlainTextResponse,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles  # noqa: E402

from bondlayer import config, fairness, llm, scoreboard as sb, visibility  # noqa: E402
from bondlayer.agent import chat as ch  # noqa: E402
from bondlayer.agent import repeat as rp  # noqa: E402
from bondlayer.agent import shopping_agent as sa  # noqa: E402
from bondlayer.agent.policy import CustomerPolicy  # noqa: E402
from bondlayer.demo_data import (  # noqa: E402
    GOLD_MEMBER,
    MERCHANTS,
    alpine_benefits,
    build_services,
    merchant_urls,
    ridgeway_unsigned_claim,
)
from bondlayer.ingest import policy_converter  # noqa: E402
from bondlayer.ingest import remediation  # noqa: E402
from bondlayer.ingest.catalog_adapter import adapt_csv_text  # noqa: E402
from bondlayer.schema import BenefitValue  # noqa: E402
from bondlayer.signing import KeyRing, load_or_create_keypair  # noqa: E402
from bondlayer.ucp import capabilities as caps  # noqa: E402
from bondlayer.ucp import conformance, wire  # noqa: E402

GTIN = "9312345678907"
#: The catalogue search term. Short on purpose -- it is matched against product
#: titles, not read by a model.
DEFAULT_QUERY = "waterproof jacket"
#: What the shopper actually types. The ranking fixtures are keyed by a hash of
#: the prompt, and the prompt embeds this sentence, so any endpoint that ranks
#: must default to *this* and not to DEFAULT_QUERY -- passing the search term
#: instead misses every fixture and silently falls back to list-price ranking.
SCENARIO_REQUEST = "Find me a good waterproof jacket under $200."
WEB = Path(__file__).parent / "web"
DATA = ROOT / "data"

app = FastAPI(title="BondLayer demo")

#: Merchant services live for the process. The page mutates two of them (the
#: adversary toggles), so they must be the same objects the agent queries.
SERVICES: dict[str, Any] = {}
ALLOW_NETWORK = False


def boot(allow_network: bool = False) -> None:
    global ALLOW_NETWORK
    ALLOW_NETWORK = allow_network
    services, _ = build_services()
    SERVICES.update(services)
    for mid, (_, port) in MERCHANTS.items():
        cfg = uvicorn.Config(
            services[mid].build_app(), host="127.0.0.1", port=port, log_level="warning"
        )
        import threading

        threading.Thread(target=uvicorn.Server(cfg).run, daemon=True).start()


# ----------------------------------------------------------------------
# Shared helpers
# ----------------------------------------------------------------------

def _offers(request: str, use_extension: bool, keyring: KeyRing):
    """The like-for-like set only, so the comparison stays honest."""
    return [
        o
        for o in sa.fetch_offers(
            merchant_urls(),
            sa.search_query(request),
            use_extension=use_extension,
            member_id=GOLD_MEMBER.member_id,
            keyring=keyring,
        )
        if o.gtin == GTIN
    ]


def _call_dict(call: llm.CallRecord | None) -> dict[str, Any]:
    if call is None:
        return {"available": False}
    return {
        "available": True,
        "label": call.label,
        "model": call.model,
        "source": call.source,
        "served_from": call.served_from,
        "fixture": call.fixture,
        "recorded_at": call.recorded_at,
        "latency_ms": call.latency_ms,
        "usage": call.usage,
        "provenance": call.provenance,
        "is_real": call.is_real,
        "system": call.system,
        "prompt": call.prompt,
        "completion": call.completion,
    }


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


# ----------------------------------------------------------------------
# Endpoints
# ----------------------------------------------------------------------

@app.get("/api/scenario")
def scenario() -> dict[str, Any]:
    counts = llm.fixture_provenance()
    transport = llm.available_transport()
    return {
        "request": SCENARIO_REQUEST,
        "member": GOLD_MEMBER.model_dump(mode="json"),
        "focus_merchant": {
            "id": visibility.FOCUS_MERCHANT,
            "name": MERCHANTS[visibility.FOCUS_MERCHANT][0],
        },
        "merchants": [
            {"id": mid, "name": name, "url": f"http://127.0.0.1:{port}"}
            for mid, (name, port) in MERCHANTS.items()
        ],
        "config": config.describe(),
        "fixtures": counts,
        "live_transport": transport,
        "allow_network": ALLOW_NETWORK,
        # The home page states a dollar figure. Deriving it here costs one TRV
        # pass and no model call, which is the difference between a number the
        # page can defend and a literal somebody typed into the HTML.
        "stranded": _stranded_summary(),
    }


def _stranded_summary() -> dict[str, Any]:
    """Signed value the focus merchant publishes that negotiation withholds."""
    keyring = KeyRing()
    off = _offers(DEFAULT_QUERY, False, keyring)
    on = _offers(DEFAULT_QUERY, True, keyring)
    policy = CustomerPolicy(budget_aud=200.0)
    reasons, recoverable = sb.attribute(on, off, policy, keyring)
    return {
        "recoverable_aud": recoverable,
        "benefits_published": len(reasons),
        "benefits_delivered": sum(1 for r in reasons if r.reached_agent),
    }


@app.post("/api/chat")
def chat(body: dict = Body(...)):
    """A real, live, multi-turn conversation (bondlayer/agent/chat.py).

    The client holds the visible history and posts it back each turn; the
    catalog grounding is rebuilt server-side from the current capability state,
    so flipping the switch mid-conversation cannot leave a stale catalog in the
    thread.
    """
    history = body.get("messages") or []
    use_ext = body.get("extension", "on") == "on"
    # The opening message carries the product intent; later turns are follow-ups
    # ("what if it doesn't fit?") whose words would match no catalogue at all.
    request = next(
        (m["content"] for m in history if m.get("role") == "user"),
        DEFAULT_QUERY,
    )

    keyring = KeyRing()
    offers = _offers(request, use_ext, keyring)
    if not offers:
        # A greeting, or a follow-up asked first. Fall back to the scenario's
        # product rather than handing the model an empty catalogue and letting
        # it answer confidently about nothing.
        offers = _offers(DEFAULT_QUERY, use_ext, keyring)
    context = ch.build_context(offers, keyring, use_ext)

    def stream():
        yield _sse(
            "offers",
            [
                {
                    "merchant_id": o.merchant_id,
                    "merchant": o.merchant_name,
                    "price_aud": o.price_aud,
                    "benefit_count": len(o.benefits),
                    "signed_count": sum(1 for b in o.benefits if keyring.verify(b)),
                }
                for o in offers
            ],
        )

        policy = CustomerPolicy(budget_aud=200.0)
        trv = sa.run_trv_agent(request, offers, policy, keyring, allow_network=False)
        vis = visibility.measure(
            context.payload,
            offers,
            keyring,
            benefits_published=visibility.published_benefit_count(SERVICES),
            valuations=trv.valuations,
        )
        yield _sse("visibility", vis.as_dict())
        yield _sse(
            "payload",
            {
                "chars": len(context.payload),
                "benefit_records": sum(len(o.benefits) for o in offers),
                "text": context.payload,
            },
        )

        buffer: list[str] = []
        try:
            for delta in ch.stream_reply(history, context):
                buffer.append(delta)
                # Hold back the trailing RECOMMENDATION: line rather than
                # streaming it into the shopper's face and deleting it after.
                whole = "".join(buffer)
                visible, _ = ch.strip_verdict(whole)
                if "RECOMMENDATION" not in whole[-40:]:
                    yield _sse("token", {"text": delta})
                else:
                    yield _sse("replace", {"text": visible})
        except llm.LLMUnavailable as exc:
            yield _sse("error", {"message": str(exc)})
            return

        visible, winner = ch.strip_verdict("".join(buffer))
        call = llm.TRANSCRIPT[-1] if llm.TRANSCRIPT else None
        yield _sse(
            "verdict",
            {
                "winner": winner,
                "explanation": visible,
                "call": _call_dict(call),
                "trv_winner": trv.winner_merchant_id,
                "agrees": trv.winner_merchant_id == winner,
            },
        )
        yield _sse("done", {"calls": len(llm.TRANSCRIPT)})

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/api/ledger")
def ledger(
    request: str = Query(SCENARIO_REQUEST),
    tampered: bool = Query(False),
    inflate: float = Query(1.0),
    fit: float = Query(9.0),
    ship: float = Query(12.0),
    warranty: float = Query(8.0),
    penalty: float = Query(0.5),
    publish: str | None = Query(
        None,
        description=(
            "Comma-separated benefit ids the focus merchant chooses to publish. "
            "Omitted means all of them. This is the merchant's own lever: it "
            "answers 'what happens to my ranking if I publish this or not'."
        ),
    ),
) -> dict[str, Any]:
    """The audit drawer, and the merchant's publish levers.

    Both work by reconfiguring the live merchant services and then querying
    them over real HTTP -- an in-process shortcut would assume away the thing
    being demonstrated. That makes the mutation global, so it is **undone in a
    finally block**: without it, unticking a lever here would silently strip
    those benefits from `/api/chat` and `/api/scoreboard` too, and the money
    shot would quietly answer a question nobody asked.
    """
    with _reconfigured(tampered, inflate, publish):
        return _ledger(request, fit, ship, warranty, penalty)


@contextmanager
def _reconfigured(tampered: bool, inflate: float, publish: str | None):
    """Apply the toggles to the live services, and always put them back."""
    before_ridgeway = dict(SERVICES["ridgeway"].benefits)
    before_alpine = dict(SERVICES["alpine"].benefits)

    SERVICES["ridgeway"].benefits = {
        pid: [ridgeway_unsigned_claim(tampered)]
        for pid in SERVICES["ridgeway"].benefits
    }
    signer = load_or_create_keypair("alpine", DATA / "keys")
    for pid in SERVICES["alpine"].benefits:
        price = next(
            o.price_aud for o in SERVICES["alpine"].offers if o.product_id == pid
        )
        base = alpine_benefits(signer, price)
        if inflate != 1.0:
            base = [
                signer.sign(
                    b.model_copy(
                        update={
                            "declared_bound_aud": round(b.declared_bound_aud * inflate, 2),
                            "signature": None,
                        }
                    )
                )
                if b.declared_bound_aud is not None
                else b
                for b in base
            ]
        if publish is not None:
            keep = {x for x in publish.split(",") if x}
            base = [b for b in base if b.id in keep]
        SERVICES["alpine"].benefits[pid] = base

    try:
        yield
    finally:
        SERVICES["ridgeway"].benefits = before_ridgeway
        SERVICES["alpine"].benefits = before_alpine


def _ledger(
    request: str, fit: float, ship: float, warranty: float, penalty: float
) -> dict[str, Any]:
    keyring = KeyRing()
    offers = _offers(request, True, keyring)
    policy = CustomerPolicy(
        budget_aud=200.0,
        fit_risk_aud=fit,
        shipping_cost_assumption_aud=ship,
        warranty_value_per_year_aud=warranty,
        unverified_penalty_rate=penalty,
    )
    run = sa.run_trv_agent(request, offers, policy, keyring, allow_network=ALLOW_NETWORK)

    # Where the focus merchant actually stands. The merchant console asks "am I
    # winning, and by how much" -- a question the valuation list answers only
    # if you rank it yourself, which is not the reader's job.
    ordered = sorted(
        (v for v in (run.valuations or []) if v.eligible),
        key=lambda v: v.adjusted_cost_aud,
    )
    focus = visibility.FOCUS_MERCHANT
    position = next(
        (i + 1 for i, v in enumerate(ordered) if v.offer.merchant_id == focus), None
    )
    mine = next((v for v in ordered if v.offer.merchant_id == focus), None)
    leader = ordered[0] if ordered else None
    standing = {
        "position": position,
        "of": len(ordered),
        "adjusted_cost_aud": round(mine.adjusted_cost_aud, 2) if mine else None,
        "list_price_aud": mine.list_price_aud if mine else None,
        "leader_id": leader.offer.merchant_id if leader else None,
        # Positive means the focus merchant is that many dollars behind.
        "gap_aud": (
            round(mine.adjusted_cost_aud - leader.adjusted_cost_aud, 2)
            if mine and leader
            else None
        ),
    }

    return {
        "standing": standing,
        "winner": run.winner_merchant_id,
        "explanation": run.explanation,
        "faithfulness": run.faithfulness,
        "valuations": [
            {
                "merchant_id": v.offer.merchant_id,
                "merchant": v.offer.merchant_name,
                "list_price_aud": v.list_price_aud,
                "adjusted_cost_aud": v.adjusted_cost_aud,
                "eligible": v.eligible,
                "excluded_reason": v.excluded_reason,
                "lines": [
                    {
                        "label": line.label,
                        "amount_aud": line.amount_aud,
                        "status": line.status,
                        "basis": line.basis,
                    }
                    for line in v.lines
                ],
            }
            for v in run.valuations or []
        ],
    }


@app.get("/api/repeats")
def repeats(
    extension: str = Query("on"),
    request: str = Query(SCENARIO_REQUEST),
    n: int = Query(rp.DEFAULT_REPEATS),
) -> dict[str, Any]:
    keyring = KeyRing()
    offers = _offers(request, extension == "on", keyring)
    policy = sa.extract_intent(request, allow_network=ALLOW_NETWORK)
    tally = rp.run_repeats(
        request, offers, policy, keyring, repeats=n, allow_network=ALLOW_NETWORK
    )
    return {"extension": extension, **tally.as_dict()}


@app.get("/api/levers")
def levers() -> dict[str, Any]:
    """What the merchant can actually change, and what each one is worth.

    The console previously offered two panels of controls, neither of which a
    merchant could act on: the adversary toggles are claims about *our*
    arithmetic, and the valuation sliders are the *shopper's* preferences. This
    endpoint answers the only question a merchant actually has -- which of my
    own terms move my ranking, and by how much.
    """
    keyring = KeyRing()
    offers = _offers(DEFAULT_QUERY, True, keyring)
    policy = CustomerPolicy(budget_aud=200.0)
    reasons, _ = sb.attribute(offers, offers, policy, keyring)
    by_title = {r.title: r for r in reasons}

    signer = load_or_create_keypair(visibility.FOCUS_MERCHANT, DATA / "keys")
    price = next(
        (o.price_aud for o in offers if o.merchant_id == visibility.FOCUS_MERCHANT),
        199.0,
    )
    rows = []
    for b in alpine_benefits(signer, price):
        r = by_title.get(b.title)
        rows.append({
            "id": b.id,
            "type": b.type.value,
            "title": b.title,
            "declared_bound_aud": b.declared_bound_aud,
            # What the deterministic ledger credits it, which is not the same
            # as what the merchant declared -- the bound is a ceiling.
            "worth_aud": r.value_aud if r else 0.0,
            "status": r.status if r else "not valued",
        })
    rows.sort(key=lambda x: -x["worth_aud"])
    return {"merchant_id": visibility.FOCUS_MERCHANT, "levers": rows}


@app.get("/api/scoreboard")
def scoreboard(
    request: str = Query(SCENARIO_REQUEST),
    n: int = Query(rp.DEFAULT_REPEATS),
) -> dict[str, Any]:
    """Why the merchant lost, over repeated comparisons in both states.

    This is the only screen in the demo that answers a *standing* question
    rather than a one-off one, so it deliberately runs both conditions rather
    than reporting whichever the switch happens to be showing.
    """
    keyring = KeyRing()
    off = _offers(request, False, keyring)
    on = _offers(request, True, keyring)
    # The shopper's own derived policy, not a house default: the dollar figures
    # in the attribution are what these benefits were worth to *this* shopper.
    policy = sa.extract_intent(request, allow_network=ALLOW_NETWORK)
    board = sb.run(
        request, off, on, policy, keyring, repeats=n, allow_network=ALLOW_NETWORK
    )
    return board.as_dict()


# ----------------------------------------------------------------------
# Merchant onboarding (/onboard) -- "the plug", with the approval gate visible
# ----------------------------------------------------------------------

def _issue_severity(issue) -> str:
    """A merchant does not act on 'unparseable'; they act on what it costs."""
    if issue.resolution.startswith("row skipped"):
        return "invisible"
    if issue.field == "barcode":
        return "unmatchable"
    return "incomparable"


#: Uploads live for the process only. A merchant's catalogue and policy are
#: their commercial data; writing them to disk in a demo would be a promise we
#: have not thought hard enough about keeping. Restarting the server forgets
#: everything, which is the behaviour we want.
UPLOADS: dict[str, dict[str, str]] = {}

#: A hackathon laptop should not be a file-conversion service, and a 5 MB CSV
#: is already far larger than any merchant needs for a first look.
MAX_UPLOAD_BYTES = 5 * 1024 * 1024


@app.post("/api/onboard/upload")
async def onboard_upload(
    merchant: str = Query(visibility.FOCUS_MERCHANT),
    catalog: UploadFile | None = File(None),
    policy: UploadFile | None = File(None),
) -> dict[str, Any]:
    """Take the merchant's own two files and use them for the rest of the flow.

    Both are optional: a merchant who has only a returns page to hand should
    still be able to see step 2 work, and the sample stands in for whatever
    they did not upload.
    """
    store = UPLOADS.setdefault(merchant, {})
    accepted: dict[str, Any] = {}

    for field, upload in (("catalog", catalog), ("policy", policy)):
        if upload is None:
            continue
        raw = await upload.read()
        if len(raw) > MAX_UPLOAD_BYTES:
            return {
                "error": (
                    f"{upload.filename} is {len(raw) // 1024} kB; the limit is "
                    f"{MAX_UPLOAD_BYTES // 1024} kB."
                )
            }
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            # Excel still exports cp1252 more often than anyone admits.
            try:
                text = raw.decode("cp1252")
            except UnicodeDecodeError:
                return {"error": f"{upload.filename} is not text we can read."}
        store[field] = text
        accepted[field] = {"filename": upload.filename, "bytes": len(raw)}

    return {"merchant_id": merchant, "accepted": accepted, "using_sample": _sample_fields(merchant)}


def _sample_fields(merchant: str) -> list[str]:
    """Which halves are still the bundled sample rather than the merchant's."""
    store = UPLOADS.get(merchant, {})
    return [f for f in ("catalog", "policy") if f not in store]


@app.post("/api/onboard/reset")
def onboard_reset(merchant: str = Query(visibility.FOCUS_MERCHANT)) -> dict[str, Any]:
    UPLOADS.pop(merchant, None)
    return {"merchant_id": merchant, "using_sample": ["catalog", "policy"]}


@app.get("/api/onboard")
def onboard(merchant: str = Query(visibility.FOCUS_MERCHANT)) -> dict[str, Any]:
    """Everything the merchant sees on the day they plug in.

    Runs against whatever they uploaded, falling back to the bundled sample per
    half. Step 1 is deterministic on purpose (no model maps a product -- a
    hallucinated price is worse than a missing one). Step 2 is the one place a
    model is genuinely necessary, and it produces drafts that cannot sign
    themselves.
    """
    name = MERCHANTS[merchant][0]
    store = UPLOADS.get(merchant, {})

    csv_text = store.get("catalog")
    if csv_text is None:
        csv_text = (DATA / "merchants" / merchant / "catalog_export.csv").read_text(
            encoding="utf-8"
        )

    try:
        offers, issues = adapt_csv_text(csv_text, merchant, name)
        catalog_error = None
        todos = [t.as_dict() for t in remediation.todos(csv_text, offers, issues)]
        preview = remediation.fixed_rows(csv_text, offers)
        changed = {k: sorted(v) for k, v in remediation.changed_cells(csv_text, offers).items()}
    except Exception as exc:  # a merchant's real export, not ours -- say why
        offers, issues, catalog_error = [], [], str(exc)
        todos, preview, changed = [], [], {}

    doc = store.get("policy")
    if doc is None:
        doc = fairness.policy_prose(merchant) or ""

    drafts: list[dict[str, Any]] = []
    draft_error = None
    if doc:
        try:
            for d in policy_converter.draft_from_document(
                doc, merchant, allow_network=ALLOW_NETWORK
            ):
                drafts.append({
                    "id": d.benefit.id,
                    "type": d.benefit.type.value,
                    "title": d.benefit.title,
                    "facts": d.benefit.facts,
                    "declared_bound_aud": d.benefit.declared_bound_aud,
                    "source_quote": d.source_quote,
                    "warnings": d.warnings,
                    "approved": d.approved,
                    "signature": d.benefit.signature,
                })
        except llm.LLMUnavailable as exc:
            # An uploaded policy is a document no fixture was ever recorded
            # for, so this is the expected failure when the server was started
            # without --live. Say what to do rather than printing a hash.
            draft_error = (
                f"{exc}"
                if not store.get("policy")
                else (
                    "Reading a policy document you uploaded needs a live model "
                    "call, and this server was started without --live. Restart "
                    "it with `python run_demo.py web --live`, or carry on with "
                    "the sample policy to see the rest of the flow."
                )
            )

    keyring = KeyRing()
    live = _offers(DEFAULT_QUERY, True, keyring)
    offer = next((o for o in live if o.merchant_id == merchant), None)

    return {
        "merchant_id": merchant,
        "merchant": name,
        "using_sample": _sample_fields(merchant),
        "catalog": {
            "csv": csv_text,
            "error": catalog_error,
            "offers": [o.model_dump(mode="json") for o in offers],
            "issues": [
                {
                    "row": i.row,
                    "field": i.field,
                    "problem": i.problem,
                    "resolution": i.resolution,
                    "severity": _issue_severity(i),
                }
                for i in issues
            ],
            # The diagnosis, turned into work. One instruction per fix rather
            # than one line per parser event, because that is how it gets done.
            "todos": todos,
            "fixed": {
                "columns": remediation.FIXED_COLUMNS,
                "rows": preview,
                "changed": changed,
                "download": f"/api/onboard/fixed.csv?merchant={merchant}",
            },
        },
        "policy": {
            "prose": doc,
            "drafts": drafts,
            "error": draft_error,
            "unsigned": True,
            "note": (
                "Nothing above carries a signature. `policy_converter` has no "
                "access to a key; `sign_approved()` is a separate call that "
                "takes only records a person marked approved."
            ),
        },
        "live": {
            "published": len(offer.benefits) if offer else 0,
            "signed": sum(1 for b in offer.benefits if keyring.verify(b)) if offer else 0,
        },
    }


# response_class, not a return annotation: FastAPI reads the annotation as a
# response *model* and re-serialises the body as JSON, which quietly turned
# this endpoint's CSV into a JSON string with no Content-Disposition.
@app.get("/api/onboard/fixed.csv", response_class=PlainTextResponse)
def onboard_fixed_csv(merchant: str = Query(visibility.FOCUS_MERCHANT)):
    """The corrected export, as a file the merchant can actually open.

    Rows we could not map are still in it, marked ACTION REQUIRED. Dropping
    them would hand back a file that looks clean and is quietly shorter than
    the one they gave us, which is the most misleading thing this could do.
    """
    name = MERCHANTS[merchant][0]
    store = UPLOADS.get(merchant, {})
    csv_text = store.get("catalog")
    if csv_text is None:
        csv_text = (DATA / "merchants" / merchant / "catalog_export.csv").read_text(
            encoding="utf-8"
        )
    offers, _ = adapt_csv_text(csv_text, merchant, name)
    return PlainTextResponse(
        remediation.fixed_csv(csv_text, offers),
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{merchant}-catalog-bondlayer.csv"'
            )
        },
    )


@app.post("/api/onboard/sign")
def onboard_sign(body: dict = Body(...)) -> dict[str, Any]:
    """The approval gate, exercised for real.

    The client sends the ids a person ticked. Only those are signed, and each
    signature is verified back through `KeyRing` before it is returned -- so
    the screen is showing a check that ran, not a green tick someone drew.
    """
    merchant = body.get("merchant", visibility.FOCUS_MERCHANT)
    approved = set(body.get("approved") or [])
    # The same document step 2 drafted from -- signing the bundled sample while
    # the screen shows the merchant's own drafts would be the worst kind of bug.
    doc = UPLOADS.get(merchant, {}).get("policy") or fairness.policy_prose(merchant) or ""
    drafts = policy_converter.draft_from_document(
        doc, merchant, allow_network=ALLOW_NETWORK
    )
    for d in drafts:
        d.approved = d.benefit.id in approved

    signer = load_or_create_keypair(merchant, DATA / "keys")
    signed: list[BenefitValue] = policy_converter.sign_approved(drafts, signer)
    keyring = KeyRing()
    keyring.pin(merchant, signer.public_key_b64)

    return {
        "merchant_id": merchant,
        "approved": len(approved),
        "rejected": len(drafts) - len(approved),
        "signed": [
            {
                "id": b.id,
                "title": b.title,
                "signature": b.signature,
                "verifies": bool(keyring.verify(b)),
                "reason": keyring.verify(b).reason,
            }
            for b in signed
        ],
        "note": (
            f"{len(drafts) - len(approved)} draft(s) were not approved and "
            "carry no signature, so no agent will ever value them."
        ),
    }


@app.get("/onboard")
def onboard_page() -> FileResponse:
    return FileResponse(WEB / "onboard.html")


PROMPTS = [
    {
        "id": "chat",
        "name": "Shopping agent — live conversation",
        "used_for": "the left pane; every turn you type",
        "why": (
            "This is the agent a shopper actually talks to. It is told how to "
            "compare offers the way any competent shopping agent would be told: "
            "rank on what you end up paying, credit stated dollar figures, do "
            "not credit a merchant that published nothing, and treat an "
            "unsigned claim as unverified."
        ),
    },
    {
        "id": "rank",
        "name": "Shopping agent — scripted ranking",
        "used_for": "run_demo.py compare, and the n=5 tally",
        "why": (
            "The reproducible, fixture-backed version of the same instruction, "
            "pinned so the before/after baseline cannot drift (D5). It returns "
            "JSON instead of prose; that is the only difference in substance."
        ),
    },
    {
        "id": "intent",
        "name": "Intent extraction",
        "used_for": "turning the shopper's words into a customer policy",
        "why": (
            "The customer's valuation policy is derived from what they said, "
            "not configured by us (D9.7). The merchant never sees it."
        ),
    },
    {
        "id": "explain",
        "name": "Ledger narration",
        "used_for": "the deterministic path only",
        "why": (
            "The model may write the sentence; it may not invent the "
            "arithmetic. Every number it cites is checked against the computed "
            "table and the sentence is discarded if it drifts (D9.12)."
        ),
    },
    {
        "id": "policy",
        "name": "Policy converter",
        "used_for": "merchant onboarding: prose to typed records",
        "why": (
            "Drafts only. A person approves before anything is signed (D7); "
            "nothing this prompt produces can sign itself."
        ),
    },
]

#: The claim these prompts have to survive: the agent is not told about us.
FORBIDDEN_IN_PROMPTS = ("bondlayer", "benefit_value", "org.bondlayer")


def _prompt_texts() -> dict[str, str]:
    return {
        "chat": ch.CHAT_SYSTEM,
        "rank": sa.RANK_SYSTEM,
        "intent": sa.INTENT_SYSTEM,
        "explain": sa.EXPLAIN_SYSTEM,
        "policy": policy_converter.SYSTEM,
    }


@app.get("/api/evidence")
def evidence() -> dict[str, Any]:
    """Everything a sceptical judge should be able to check for themselves."""
    urls = {mid: f"http://127.0.0.1:{port}" for mid, (_, port) in MERCHANTS.items()}

    # --- the prompts, with the leak test applied live -------------------
    texts = _prompt_texts()
    prompts = []
    for meta in PROMPTS:
        text = texts[meta["id"]]
        lowered = text.lower()
        leaks = [w for w in FORBIDDEN_IN_PROMPTS if w in lowered]
        # The policy converter is merchant-side tooling, so naming the schema
        # there is correct; the claim is only about the AGENT's prompts.
        agent_side = meta["id"] in ("chat", "rank", "intent", "explain")
        prompts.append({
            **meta,
            "text": text,
            "agent_side": agent_side,
            "mentions_bondlayer": bool(leaks),
            "leaks": leaks,
        })

    # --- fairness: what each merchant offers vs what it put on the wire --
    keyring = KeyRing()
    offers = _offers(DEFAULT_QUERY, True, keyring)
    published: dict[str, tuple[int, int]] = {}
    for mid in MERCHANTS:
        offer = next((o for o in offers if o.merchant_id == mid), None)
        if offer is None:
            published[mid] = (0, 0)
        else:
            published[mid] = (
                len(offer.benefits),
                sum(1 for b in offer.benefits if keyring.verify(b)),
            )

    return {
        "conformance": conformance.run(urls).as_dict(),
        "wire": {
            "off": [e.as_dict() for e in wire.capture(urls, use_extension=False)],
            "on": [
                e.as_dict()
                for e in wire.capture(
                    urls, use_extension=True, member_id=GOLD_MEMBER.member_id
                )
            ],
        },
        "prompts": prompts,
        "fairness": {
            **fairness.summary(published),
            "policies": {
                mid: fairness.policy_prose(mid) for mid in MERCHANTS
            },
        },
        "capabilities": {
            "core": [caps.CATALOG_SEARCH, caps.CATALOG_LOOKUP, caps.IDENTITY_LINKING],
            "extension": caps.BENEFIT_VALUE,
            "not_implemented": [
                "dev.ucp.shopping.cart",
                "dev.ucp.shopping.checkout",
                "dev.ucp.shopping.payments",
            ],
            "real_ucp_loyalty": caps.UCP_LOYALTY,
        },
    }


@app.get("/evidence")
def evidence_page() -> FileResponse:
    return FileResponse(WEB / "evidence.html")


@app.get("/api/transcript")
def transcript() -> dict[str, Any]:
    return {
        "calls": [_call_dict(c) for c in llm.TRANSCRIPT],
        "total_cost_usd": sum(
            c.usage.get("cost_usd") or 0.0 for c in llm.TRANSCRIPT
        ),
        "real_calls": sum(1 for c in llm.TRANSCRIPT if c.is_real),
    }


@app.get("/")
def home() -> FileResponse:
    """The front door. A merchant and a judge want different screens, and
    sending both to the money shot served neither."""
    return FileResponse(WEB / "home.html")


@app.get("/demo")
def demo_page() -> FileResponse:
    return FileResponse(WEB / "index.html")


@app.middleware("http")
async def _no_store(request, call_next):
    """Never let a browser cache the demo's own assets.

    The theme changed from dark to light during development, and a browser that
    had seen the old stylesheet rendered half the page in each -- on a machine
    where the files on disk were entirely correct. On a laptop that has been
    open all week in front of judges, that is not a risk worth carrying for a
    few kB of caching.
    """
    response = await call_next(request)
    if request.url.path.startswith("/static") or request.url.path in (
        "/", "/demo", "/onboard", "/evidence",
    ):
        response.headers["Cache-Control"] = "no-store, must-revalidate"
    return response


app.mount("/static", StaticFiles(directory=WEB), name="static")


def serve(host: str = "127.0.0.1", port: int = 8080, allow_network: bool = False) -> None:
    boot(allow_network)
    print(f"\n  BondLayer demo  ->  http://{host}:{port}\n")
    uvicorn.run(app, host=host, port=port, log_level="warning")

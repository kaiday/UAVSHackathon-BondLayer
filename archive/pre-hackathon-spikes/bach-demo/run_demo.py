"""One-command demo runner.

    python run_demo.py serve      # boot the three merchant UCP services
    python run_demo.py compare    # run the before/after in the terminal
    python run_demo.py ingest     # show the catalogue adapter's findings
    python run_demo.py transcript # every model call, prompt and reply, verbatim
    python run_demo.py web        # the v2 demo page (docs/demo-flow-v2.md)

`compare` is the money shot (D5): the same agent, the same request, run twice.
The only difference is which capabilities the agent declares in its UCP-Agent
header -- so the "before" is not a strawman, it is our own product with the
extension pruned by ordinary capability negotiation.

Flags:
    --quiet   suppress the verbatim model replies under each run
    --live    allow live model calls on a fixture miss (default is fixtures
              only, so a stage run can never hang on the network)
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import uvicorn  # noqa: E402

from bondlayer import config, llm  # noqa: E402
from bondlayer.agent import shopping_agent as sa  # noqa: E402
from bondlayer.demo_data import (  # noqa: E402
    GOLD_MEMBER,
    MERCHANTS,
    build_services,
    merchant_urls,
)
from bondlayer.signing import KeyRing  # noqa: E402

REQUEST = "Find me a good waterproof jacket under $200."

QUIET = "--quiet" in sys.argv
LIVE = "--live" in sys.argv


def _wrap(text: str, width: int = 68, indent: str = "     ") -> str:
    import textwrap

    return "\n".join(
        indent + line
        for para in text.splitlines()
        for line in (textwrap.wrap(para, width) or [""])
    )


def _show_call(call: llm.CallRecord | None, *, prompt_chars: int = 0) -> None:
    """Print one model call as it happened. This is the whole point of D9.13:
    a demo that shows only a parsed winner_merchant_id is asking to be taken
    on trust."""
    if call is None:
        return
    cost = call.usage.get("cost_usd")
    meta = [call.provenance]
    if call.served_from == "fixture":
        meta.append(f"replayed from {call.fixture}")
    if call.recorded_at:
        meta.append(f"recorded {call.recorded_at}")
    if call.latency_ms:
        meta.append(f"{call.latency_ms} ms")
    if call.usage.get("output_tokens"):
        meta.append(f"{call.usage['output_tokens']} output tokens")
    if cost:
        meta.append(f"${cost:.4f}")

    print(f"\n  [model call: {call.label}]  {call.model}")
    print(f"  {' | '.join(meta)}")
    if prompt_chars:
        print(f"\n  --- sent (first {prompt_chars} chars of {len(call.prompt)}) ---")
        print(_wrap(call.prompt[:prompt_chars], indent="  | "))
    print("\n  --- model replied, verbatim ---")
    print(_wrap(call.completion, indent="  | "))


def _warn_if_fallback(call: llm.CallRecord | None) -> None:
    """Say loudly when no model answered.

    --quiet suppresses the verbatim replies, which is also where a fallback
    would otherwise have been visible. A run that quietly degraded to
    price-ranking still prints a confident "recommends: peak", and nothing
    about that line tells you a model was never consulted.
    """
    if call is not None and call.source == "fallback":
        print(f"\n  !! NO MODEL ANSWERED - {call.completion}")
        print("     The recommendation below is NOT a model decision.")


def serve(tampered: bool = False, block: bool = True) -> list[threading.Thread]:
    services, _ = build_services(tampered=tampered)
    threads = []
    for mid, (_, port) in MERCHANTS.items():
        app = services[mid].build_app()
        cfg = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        server = uvicorn.Server(cfg)
        t = threading.Thread(target=server.run, daemon=True)
        t.start()
        threads.append(t)
    time.sleep(1.5)
    print("merchant services up:")
    for mid, (name, port) in MERCHANTS.items():
        print(f"  {name:<20} http://127.0.0.1:{port}/.well-known/ucp")
    if block:
        print("\nCtrl-C to stop.")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
    return threads


def _run(use_extension: bool, label: str, policy) -> None:
    keyring = KeyRing()
    offers = sa.fetch_offers(
        merchant_urls(),
        sa.search_query(REQUEST),
        use_extension=use_extension,
        member_id=GOLD_MEMBER.member_id,
        keyring=keyring,
    )
    # Only the like-for-like product, so the comparison is honest.
    offers = [o for o in offers if o.gtin == "9312345678907"]

    print(f"\n{'=' * 72}\n{label}\n{'=' * 72}")
    print(f"agent declares: {', '.join(sa.BONDLAYER_CAPS if use_extension else sa.PLAIN_CAPS)}")
    for o in offers:
        extra = f"  [{len(o.benefits)} published benefits]" if o.benefits else ""
        print(f"  {o.merchant_name:<20} ${o.price_aud:>7.2f}{extra}")

    payload = sa.build_rank_payload(REQUEST, offers, keyring)
    print(
        f"\n  the agent sends the model {len(payload):,} characters of catalog "
        f"JSON ({sum(len(o.benefits) for o in offers)} benefit records)."
    )

    run = sa.run_llm_agent(REQUEST, offers, policy, keyring, allow_network=LIVE)
    if not QUIET:
        _show_call(llm.last_call("rank"))
    _warn_if_fallback(llm.last_call("rank"))

    print(f"\n  -> recommends: {run.winner_merchant_id}")
    print(f"     parsed ranking: {' > '.join(run.ranking)}")

    if use_extension:
        trv = sa.run_trv_agent(REQUEST, offers, policy, keyring, allow_network=LIVE)
        print("\n  deterministic cross-check (the upgrade path, D8):")
        for v in trv.valuations:
            mark = "*" if v.offer.merchant_id == trv.winner_merchant_id else " "
            status = "" if v.eligible else f"  EXCLUDED: {v.excluded_reason}"
            print(
                f"  {mark} {v.offer.merchant_name:<20} list ${v.list_price_aud:>7.2f}"
                f"   adjusted ${v.adjusted_cost_aud:>7.2f}{status}"
            )
            for line in v.lines:
                if line.amount_aud or line.status in ("unverified", "ineligible"):
                    print(
                        f"       {line.amount_aud:>+8.2f}  {line.label} "
                        f"[{line.status}] - {line.basis}"
                    )
        if not QUIET:
            _show_call(llm.last_call("explain"))
        _warn_if_fallback(llm.last_call("explain"))
        print(f"\n     faithfulness check: {trv.faithfulness}")


def _provenance_banner() -> None:
    print(f"config: {config.describe()}")
    counts = llm.fixture_provenance()
    print(
        f"model fixtures: {counts['recorded']} recorded live, "
        f"{counts['authored']} hand-authored, "
        f"{counts['unknown']} unknown provenance"
    )
    stale = counts["recorded"] + counts["authored"] - counts["for_current_model"]
    if stale > 0:
        # The fixture key hashes the model, so fixtures recorded from another
        # model are invisible to this run. Saying "5 recorded live" while
        # silently replaying none of them is exactly the kind of quiet
        # dishonesty the transcript work exists to remove.
        print(
            f"  {counts['for_current_model']} of those were recorded from "
            f"{counts['model']}; the other {stale} are from a different model "
            "and will NOT be used. Re-run scripts/seed_fixtures.py to record "
            "this one."
        )
    if counts["empty"]:
        print(
            f"  !! {counts['empty']} fixture(s) hold an EMPTY completion and "
            "cannot be replayed. Delete them and re-run "
            "scripts/seed_fixtures.py --force."
        )
    if counts["authored"] or counts["unknown"]:
        print(
            "  WARNING: hand-authored completions are not evidence of model "
            "behaviour. Re-run scripts/seed_fixtures.py to record."
        )
    transport = llm.available_transport()
    print(
        "  live transport available: "
        + (
            f"{llm.SOURCE_LABELS[transport]} ({llm.default_model()})"
            if transport
            else "none (fixtures only)"
        )
        + ("  [--live to use it on a miss]" if transport and not LIVE else "")
    )


def compare() -> None:
    llm.reset_transcript()
    _provenance_banner()
    serve(block=False)
    # The intent call happens once and is shared by both runs; show it first so
    # the customer policy does not appear from nowhere.
    policy = sa.extract_intent(REQUEST, allow_network=LIVE)
    if not QUIET:
        print(f"\n{'=' * 72}\nSTEP 0 - the shopper's words become a policy\n{'=' * 72}")
        print(f'  request: "{REQUEST}"')
        _show_call(llm.last_call("intent"))

    _run(False, "BEFORE - plain UCP (the extension is not negotiated)", policy)
    _run(True, "AFTER - org.bondlayer.benefit_value negotiated", policy)

    print(f"\n{'=' * 72}")
    print(f"{len(llm.TRANSCRIPT)} model calls this run. "
          "`python run_demo.py transcript` prints every prompt in full.")


def transcript() -> None:
    """Everything the model was asked and everything it said, in full.

    The demo's credibility rests on this being inspectable rather than
    described.
    """
    _provenance_banner()
    serve(block=False)
    llm.reset_transcript()
    policy = sa.extract_intent(REQUEST, allow_network=LIVE)
    for use_ext in (False, True):
        kr = KeyRing()
        offers = [
            o for o in sa.fetch_offers(
                merchant_urls(), sa.search_query(REQUEST), use_extension=use_ext,
                member_id=GOLD_MEMBER.member_id, keyring=kr,
            ) if o.gtin == "9312345678907"
        ]
        sa.run_llm_agent(REQUEST, offers, policy, kr, allow_network=LIVE)
        if use_ext:
            sa.run_trv_agent(REQUEST, offers, policy, kr, allow_network=LIVE)

    for i, call in enumerate(llm.TRANSCRIPT, 1):
        print(f"\n{'=' * 72}\n[{i}/{len(llm.TRANSCRIPT)}] {call.label}  -  {call.model}"
              f"\n{'=' * 72}")
        print(f"provenance : {call.provenance}")
        print(f"served     : {call.served_from}"
              + (f"  ({call.fixture})" if call.fixture else ""))
        if call.recorded_at:
            print(f"recorded   : {call.recorded_at}  ({call.latency_ms} ms)")
        if call.usage:
            print(f"usage      : {call.usage}")
        print("\n--- SYSTEM PROMPT " + "-" * 54)
        print(call.system)
        print("\n--- USER PROMPT " + "-" * 56)
        print(call.prompt)
        print("\n--- COMPLETION " + "-" * 57)
        print(call.completion)


def ingest() -> None:
    _, issues = build_services()
    for mid, found in issues.items():
        print(f"\n{mid}:")
        if not found:
            print("  (clean)")
        for i in found:
            print(f"  row {i.row} {i.field}: {i.problem}\n      -> {i.resolution}")


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    cmd = args[0] if args else "compare"
    if cmd == "serve":
        serve()
    elif cmd == "compare":
        compare()
    elif cmd == "transcript":
        transcript()
    elif cmd == "ingest":
        ingest()
    elif cmd == "web":
        from app.api import serve as serve_web
        serve_web(allow_network=LIVE)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()

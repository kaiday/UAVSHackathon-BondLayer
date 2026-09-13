"""``POST /{merchant}/ucp/intent/propose`` -- the merchant decodes the sentence.

The problem statement's desired outcome is a *merchant system* that receives a
complex multi-constraint query from the buyer's agent, decodes the intent,
analyses its catalogue against it and returns a justified proposal. The plain
catalogue routes receive a typed plan (``category``, ``max_price``, ``q``) that
the agent decoded for itself. This route receives the shopper's sentence
verbatim and does the decoding on the merchant's side, with the same parser
and the same resolver the agent would use -- one interpreter, two seats.

What it does **not** change:

- It is a negotiated capability, ``org.bondlayer.intent_match``, an extension
  of ``catalog.search``. An agent that does not declare it gets 406, exactly
  as the existing routes refuse a capability that was not negotiated. The
  control merchant does not declare it, so it never serves it.
- It reuses the server's seeded state and response helpers -- ``_merchant``,
  ``_negotiated``, ``_catalog``, ``_product``, ``_benefit_block`` -- so a
  product on this route is byte-identical to a product on ``catalog.search``,
  and the benefit block is the same block. Nothing is seeded twice.
- The benefit extension is still gated by its own negotiation. ``extensions``
  is present iff ``org.bondlayer.benefit_value`` also survived, and absent
  otherwise -- never empty. The resolver still runs with the verified records
  either way; an agent that did not declare the extension simply cannot see
  the raw records it was answered from.

**Only verified records reach the resolver.** The merchant's published set is
checked against its own public JWK in ``keys/`` on every call, the same gate
``scripts/eval_run.py`` applies. An unsigned or unverifiable record can still
be *served* in the benefit block (flagged ``signed: false``), but it can never
be cited as evidence for a clause.

**What the merchant receives, and what it never does.** On this route the
merchant receives the shopper's *utterance* verbatim. It still never receives
the shopper's valuation policy, the shopper's benefit weights, or the
cross-merchant comparison. The order of the proposals below is this merchant's
own ordering of its own shelf, from catalogue attributes and its own verified
records; ranking against the shopper's policy, across merchants, by effective
cost, stays agent-side, exactly as it does for ``catalog.search``.

Live mode decodes through OpenAI; explicit rules mode uses the reference parser.
The response identifies the decoder and includes real model call metadata.

The server module includes this router, and this module needs the server's
helpers, so the two would be circular at import time. This module fetches the
server at call time (``_server()``) rather than at import, which makes the
pair safe to load in either order.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from bondlayer.interpreter import parse, resolve
from bondlayer.interpreter.openai import decode
from bondlayer.interpreter.describe import (
    assumptions,
    clarifying_question,
    describe,
    unanswerable_from_catalogue,
)
from bondlayer.records import ES256Signer, load_signed
from bondlayer.types import Constraint, Proposal, ResolvedConstraint, SignedRecord
from bondlayer.ucp.capabilities import BENEFIT_VALUE, INTENT_MATCH
from bondlayer.ucp.profile import KEYS, Merchant, signing_keys
from bondlayer.ucp.records import RECORDS

router = APIRouter(tags=["ucp"])

#: Named on the wire so a reader never has to guess what produced the decode.
DECODER = "rules"


class ProposeRequest(BaseModel):
    """The body: the sentence as the shopper said it, and how many to return."""

    utterance: str = Field(min_length=1)
    limit: int = Field(default=20, ge=1, le=100)


def _server():
    """The merchant server's seeded state and response helpers.

    Imported when a request arrives, not when this module loads: ``server``
    includes this router, so a top-level import here would be circular and
    which module loaded first would depend on the caller.
    """
    from bondlayer.ucp import server

    return server


# --- verification gate ------------------------------------------------------------


def verifiers_for(merchant: Merchant, keys_dir: Path = KEYS) -> list[ES256Signer]:
    """One verifier per public JWK this merchant publishes. Public keys only.

    ``[]`` when the merchant does not sign or has published no key -- in which
    case nothing it publishes can verify, and the resolver is handed nothing.
    """
    if not merchant.signs_records:
        return []
    return [ES256Signer.from_jwk(jwk, issuer=merchant.domain or merchant.id) for jwk in signing_keys(merchant, keys_dir)]


def verified_records(
    merchant: Merchant, records_dir: Path = RECORDS, keys_dir: Path = KEYS,
) -> list[SignedRecord]:
    """The merchant's published records that verify against its own key.

    This is the gate the resolver never sees behind. A record with no
    signature, a signature that does not check out, an unknown ``key_id`` or an
    expired window is dropped here, so it can never be cited as evidence.
    """
    if not merchant.signs_records:
        return []
    if records_dir == RECORDS:
        from bondlayer.records.serialise import signed_from_json
        published = [signed_from_json(entry) for entry in _server()._records.get(merchant.id, [])]
    else:
        published = load_signed(records_dir / f"{merchant.id}.signed.json")
    verifiers = verifiers_for(merchant, keys_dir)
    if not verifiers:
        return []
    return [
        r for r in published
        if r.signature and any(v.verify(r) for v in verifiers)
    ]


# --- wire shapes -----------------------------------------------------------------


def _constraint(c: Constraint) -> dict:
    return {"text": c.text, "kind": c.kind.value}


def _resolved(r: ResolvedConstraint) -> dict:
    return {
        "text": r.constraint.text,
        "kind": r.constraint.kind.value,
        "satisfied": r.satisfied,
        "evidence_record_id": r.evidence_record_id,
        "evidence_attribute": r.evidence_attribute,
        "note": r.note,
    }


def _proposal(p: Proposal, product: dict) -> dict:
    return {
        "product": product,
        "resolved": [_resolved(r) for r in p.resolved],
        "unsatisfied": [_constraint(c) for c in p.unsatisfied],
    }


def decoded_intent(utterance: str, constraints: list[Constraint]) -> dict:
    """The ``decoded_intent`` block: how the merchant read the sentence."""
    return {
        "decoder": DECODER,
        "utterance": utterance,
        "constraints": [describe(c) for c in constraints],
        "unanswerable_from_catalogue": unanswerable_from_catalogue(constraints),
        "assumptions": assumptions(constraints),
        "clarifying_question": clarifying_question(constraints),
    }


# --- the route -------------------------------------------------------------------


@router.post("/{merchant_id}/ucp/intent/propose")
def intent_propose(
    merchant_id: str,
    body: ProposeRequest,
    ucp_agent: str | None = Header(default=None, alias="UCP-Agent"),
) -> dict:
    srv = _server()
    merchant = srv._merchant(merchant_id)
    negotiated = srv._negotiated(merchant, ucp_agent)
    if INTENT_MATCH not in negotiated:
        raise HTTPException(406, "intent.propose was not negotiated")

    utterance = body.utterance.strip()
    if not utterance:
        raise HTTPException(422, "utterance must not be blank")

    constraints, decode_meta = decode(utterance)
    skus = srv._catalog[merchant.id]
    verified = verified_records(merchant)
    proposals = resolve(constraints, skus, verified, merchant_domains={merchant.id: merchant.domain or merchant.id})[: body.limit]

    response: dict = {
        "business": {"id": merchant.id, "name": merchant.display_name},
        # Echo the active set so the agent knows what is live rather than
        # inferring it from what is missing -- same as the catalogue routes.
        "active_capabilities": negotiated.active,
        "decoded_intent": decoded_intent(utterance, constraints),
        "proposals": [_proposal(p, srv._product(p.sku)) for p in proposals],
    }
    response["decoded_intent"]["decoder"] = decode_meta["provider"]
    response["decoded_intent"]["ai"] = decode_meta
    if BENEFIT_VALUE in negotiated:
        # Same block, same builder, same gate as catalog.search. Present iff the
        # benefit extension survived negotiation; absent otherwise, never empty.
        response["extensions"] = {
            BENEFIT_VALUE: [srv._benefit_block(merchant, p.sku) for p in proposals]
        }
    return response

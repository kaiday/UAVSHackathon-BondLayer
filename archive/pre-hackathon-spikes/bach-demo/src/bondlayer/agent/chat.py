"""A real conversation with the shopping agent (live, not replayed).

`shopping_agent.run_llm_agent` answers one scripted question from a fixture, so
a stage run is reproducible and offline. That is the right shape for the pinned
before/after baseline (D5) and the wrong shape for a judge who says "ask it
about returns" -- a fixture cannot answer a question nobody recorded.

This module is the other half: the same offers, the same capability
negotiation, the same signature checks, but a live multi-turn conversation
against OpenAI. Both paths hand the model exactly the same catalog payload, so
what changes between them is who is asking, not what the merchant published.

The agent still has no BondLayer code and no knowledge of the extension (D8).
The system prompt below mentions signatures only in the way any competent
shopping agent would be told to treat unverified claims.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .. import llm
from ..schema import Offer
from ..signing import KeyRing
from .shopping_agent import build_rank_payload

#: The final line the model is asked to emit. It is stripped from the visible
#: reply and used to drive the merchant console, so the console never has to
#: guess a winner by string-matching prose.
VERDICT_RE = re.compile(r"^\s*RECOMMENDATION:\s*([a-z0-9_-]+)\s*$", re.IGNORECASE | re.MULTILINE)

CHAT_SYSTEM = """You are a shopping agent acting for a person, talking to them directly.

You have been given the merchants' catalog data below. Answer their questions
about it conversationally and concisely -- two or three sentences unless they
ask for detail. You are having a conversation, so follow-up questions refer to
what you have already discussed.

How to compare offers:

Rank by what the shopper actually ends up paying and receiving over the life of
the purchase -- not by list price alone. A cheaper sticker price can still be
the worse deal once delivery, returns, warranty cover and loyalty value are
counted. Where a merchant states a figure in dollars, use it; where it states a
fact with no figure, judge what it is worth to an ordinary shopper and say so.
A merchant that publishes nothing has not proved anything about its delivery,
returns or warranty, so do not credit it with any.

Treat a claim carrying a valid cryptographic signature as verified. Treat an
unsigned claim as unverified -- you may mention it, but do not rely on it.

Show your arithmetic when it matters to the answer.

After your reply, on its own final line, write exactly:
RECOMMENDATION: <merchant_id>
using the merchant_id of whichever offer you would buy right now. Include this
line on every reply, even when the question was not about choosing."""

# Note (D9.14, and it applies here too): nothing above mentions BondLayer, the
# extension or the schema. It is what any shopping agent would be told. The
# merchant that publishes signed, priced, structured evidence is simply the one
# that has something for this prompt to credit.


@dataclass
class ChatContext:
    """Everything the conversation is grounded in, for one capability state."""

    offers: list[Offer]
    payload: str
    use_extension: bool


def build_context(offers: list[Offer], keyring: KeyRing, use_extension: bool) -> ChatContext:
    return ChatContext(
        offers=offers,
        payload=build_rank_payload("", offers, keyring),
        use_extension=use_extension,
    )


def _grounding(context: ChatContext) -> str:
    """The catalog, injected as the first user turn.

    It goes in as a user message rather than into the system prompt so the
    conversation reads honestly in the transcript: this is data the agent
    fetched over UCP, not instructions it was configured with.
    """
    return (
        "Here is what I found from the merchants over UCP. Use only this data.\n\n"
        + context.payload
    )


def strip_verdict(text: str) -> tuple[str, str | None]:
    """Split the visible reply from the machine-readable last line."""
    match = VERDICT_RE.search(text)
    winner = match.group(1).lower() if match else None
    visible = VERDICT_RE.sub("", text).strip()
    return visible, winner


def stream_reply(
    history: list[dict[str, str]],
    context: ChatContext,
    *,
    model: str | None = None,
):
    """Yield text deltas for the next assistant turn.

    `history` is the visible conversation only -- the grounding payload is
    prepended here so the client never has to hold 6 KB of catalog JSON, and so
    a switch flip rebuilds it rather than leaving a stale catalog in the thread.
    """
    messages = [
        {"role": "user", "content": _grounding(context)},
        {
            "role": "assistant",
            "content": "Got it -- I have the three offers and their published terms.",
        },
    ] + history

    label = "chat-" + ("bondlayer" if context.use_extension else "plain")
    yield from llm.stream_openai(CHAT_SYSTEM, messages, model=model, label=label)

"""Composing matched proposals into bundles.

``compose(constraints, proposals) -> list[Bundle]`` is the seam named in
``bondlayer.types.Bundler``. The problem statement names dynamic bundling twice
and its worked example ends on it: an agent asks for "beginner-friendly
podcasting gear" and the merchant "pitches the ideal bundle based on that
intent".

**This module never matches anything.** It is handed proposals that the
interpreter already matched, already justified and already ordered, and its
only job is to decide which of them belong *together*. Concretely, that means:

- It never reads the catalogue, never scores a listing against a clause, and
  never adds or reorders a candidate. Every item in every bundle came out of
  ``proposals`` and kept the ``ResolvedConstraint`` notes it arrived with.
- What it does read off an item is its **role in the kit** -- is this the
  microphone, the headphones, the interface, the cable -- which is a question
  about composition, not about fit. Three microphones are three good matches
  and a bad bundle.

**Never cross-merchant.** A bundle is one order from one merchant, which is the
whole reason its returns window, its warranty and its delivery terms apply to
the set rather than to three unrelated purchases. Composing the cheapest
microphone at one merchant with the cheapest headphones at another would look
better on price and be a worse answer.

**A bundle of one is valid.** When nothing in the shelf complements the best
match, the honest answer is the best match on its own, and that is what comes
back -- not an invented third item to make the set look fuller.

Deterministic: no clock, no random seed, no model call, no network. The same
proposals in the same order give the same bundles, which is the only reason a
bundle is allowed on screen next to a number from ``docs/eval-results.md``.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from decimal import Decimal

from bondlayer.types import (
    Bundle,
    Constraint,
    ConstraintKind,
    Proposal,
    ResolvedConstraint,
)

# --- roles: what an already-matched item does inside a set -------------------
#
# Read off the listing's own title first and its ``model_key`` second, because
# the title is the one field that survives every hop: ``ucp/server.py::_product``
# strips ``model_key`` from the wire, so an agent-side bundler only ever sees
# the title. Both spellings are listed so the same role is found on either side
# of the wire and the server and the agent cannot disagree about what a listing
# is.
#
# This is a small, closed, hand-written vocabulary over the frozen catalogue.
# It is deliberately not a classifier: an item whose role cannot be read simply
# fills no slot, which costs a bundle an item and never puts a wrong one in.

_ROLE_TITLE_WORDS: dict[str, tuple[str, ...]] = {
    "microphone": ("microphone", "mic"),
    "headphones": ("headphones", "headset", "earphones"),
    "interface": ("interface", "rodecaster", "scarlett", "mixer", "console"),
    "cable": ("cable", "xlr"),
    "stand": ("boom", "arm", "stand"),
    "dock": ("dock",),
    "hub": ("hub",),
    "monitor": ("monitor", "ultrasharp", "ultrafine"),
    "keyboard": ("keyboard", "keys"),
    "mouse": ("mouse",),
    "sleeve": ("sleeve", "case", "bag"),
    "charger": ("charger",),
    "power_bank": ("power bank", "powerbank"),
    "ssd": ("ssd",),
}

_ROLE_MODEL_KEYS: dict[str, tuple[str, ...]] = {
    "microphone": ("sm7b", "mv7", "at2020", "atr2100", "sm58", "sm4"),
    "headphones": ("ath-m50x", "hd280", "wh1000"),
    "interface": ("rodeai1", "scarlett2i2", "rodecaster"),
    "cable": ("xlr3m",),
    "stand": ("psa1",),
    "dock": ("dock-tb4",),
    "hub": ("hub-usbc",),
    "monitor": ("mon27", "mon32"),
    "keyboard": ("kb-mx",),
    "mouse": ("ms-mx3",),
    "sleeve": ("bag15",),
    "charger": ("chg-100",),
    "power_bank": ("pb-737",),
    "ssd": ("ssd2tb",),
}


def role_of(proposal: Proposal) -> str | None:
    """What this already-matched listing is, as a part of a set.

    Not a match decision: the listing is in ``proposals`` because the resolver
    already decided it answers the shopper. This only says which slot it can
    fill, and returns ``None`` when the listing names no role it recognises.
    """
    sku = proposal.sku
    title = " " + str(sku.title).lower() + " "
    for role, words in _ROLE_TITLE_WORDS.items():
        for word in words:
            if re.search(rf"(?<![a-z]){re.escape(word)}(?![a-z])", title):
                return role
    model_key = str(sku.attributes.get("model_key", "")).lower()
    if model_key:
        for role, keys in _ROLE_MODEL_KEYS.items():
            if model_key in keys:
                return role
    return None


def _covers(proposal: Proposal, scope: str) -> bool:
    """Whether a service product (a warranty) covers the anchor's category.

    ``Extended Cover 24mo - Laptop`` covers a laptop and not a phone. An
    accidental-damage policy names no category and covers whatever it is sold
    against.
    """
    title = str(proposal.sku.title).lower()
    if "accidental" in title:
        return True
    return scope.lower() in title


# --- slots and recipes -------------------------------------------------------


#: How a complement slot earns its place in the set.
#:
#: ``kit``      -- the shopper asked for the whole kit ("everything I need to
#:                 start a podcast"), so every slot in the recipe is part of
#:                 what was requested.
#: ``intent``   -- filled only when the shopper's own words name it. "A work
#:                 laptop and a dock" names the dock; nothing else does.
#: ``standing`` -- the merchant's pitch: the item that plainly goes with the
#:                 anchor. Filled only when the shopper named no complement of
#:                 their own, so a request that already specified its set is
#:                 never padded with an extra the shopper did not ask for.
GATES = ("kit", "intent", "standing")


@dataclass(frozen=True)
class Slot:
    """One position in a set, and what may fill it."""

    name: str  # human label, used in the rationale
    category: str  # the catalogue category this slot draws from
    roles: tuple[str, ...] = ()  # accepted roles; () accepts any role
    gate: str = "kit"
    intent_words: tuple[str, ...] = ()  # for gate="intent"
    scope_to_anchor: bool = False  # a warranty must cover the anchor's category


@dataclass(frozen=True)
class Recipe:
    """A kind of set, and why its parts belong together."""

    key: str
    anchor: Slot
    complements: tuple[Slot, ...]
    togetherness: str  # the sentence about why these belong together
    triggers: tuple[str, ...] = ()  # intent phrases that select this recipe


_PODCASTING = Recipe(
    key="podcasting",
    anchor=Slot("microphone", "audio", ("microphone",)),
    complements=(
        Slot("headphones", "audio", ("headphones",)),
        Slot("audio interface", "audio", ("interface",)),
        Slot("XLR cable", "audio", ("cable",)),
        Slot("boom arm", "audio", ("stand",)),
    ),
    togetherness=(
        "the interface is what gets the microphone into a computer, the cable is "
        "what gets the microphone into the interface, and closed-back headphones "
        "are what stop the monitor mix bleeding back into the take"
    ),
    triggers=(
        r"podcast\w*", r"record\s+interviews", r"voice[\s-]?over", r"streaming",
        r"start\s+a\s+podcast", r"recording",
    ),
)

_LAPTOP = Recipe(
    key="laptop",
    anchor=Slot("laptop", "laptop"),
    complements=(
        Slot("extended cover", "warranty", gate="intent",
             intent_words=(r"cover\b", r"warrant\w*", r"breaks?\b", r"protection"),
             scope_to_anchor=True),
        Slot("dock", "accessory", ("dock", "hub"), gate="intent",
             intent_words=(r"dock\b", r"hub\b")),
        Slot("monitor", "accessory", ("monitor",), gate="intent",
             intent_words=(r"monitor\b", r"second\s+screen")),
        Slot("carry sleeve", "accessory", ("sleeve",), gate="standing"),
    ),
    togetherness=(
        "the add-ons attach to this machine specifically and are bought on the "
        "same order, so one returns window and one delivery cover the lot"
    ),
    triggers=(r"laptop\w*", r"notebook", r"macbook"),
)

_PHONE = Recipe(
    key="phone",
    anchor=Slot("phone", "phone"),
    complements=(
        Slot("extended cover", "warranty", gate="intent",
             intent_words=(r"cover\b", r"warrant\w*", r"breaks?\b", r"protection"),
             scope_to_anchor=True),
        Slot("fast charger", "accessory", ("charger",), gate="standing"),
    ),
    togetherness=(
        "the handset and the parts that keep it running ship on one order from "
        "one merchant, so a single returns window covers the set"
    ),
    triggers=(r"phone\w*", r"smartphone", r"handset"),
)

_APPLIANCE = Recipe(
    key="appliance",
    anchor=Slot("appliance", "appliance"),
    complements=(
        Slot("extended cover", "warranty", gate="intent",
             intent_words=(r"cover\b", r"warrant\w*", r"breaks?\b", r"last\b",
                           r"protection"),
             scope_to_anchor=True),
    ),
    togetherness=(
        "the cover is written against this appliance and is bought with it, so "
        "the claim never turns on which merchant sold which half"
    ),
    triggers=(r"vacuum", r"coffee\s+machine", r"rice\s+cooker", r"kettle",
              r"toaster", r"microwave", r"appliance"),
)

RECIPES: tuple[Recipe, ...] = (_PODCASTING, _LAPTOP, _PHONE, _APPLIANCE)

#: A recipe whose anchor category matches, used when no phrase triggered one.
_BY_CATEGORY: dict[str, Recipe] = {r.anchor.category: r for r in RECIPES}


# --- reading the decoded intent ----------------------------------------------


def _intent_text(constraints: list[Constraint]) -> str:
    return " ".join(c.text for c in constraints).lower()


def _price_ceilings(constraints: list[Constraint]) -> list[tuple[Constraint, Decimal]]:
    """Every HARD money ceiling in the intent, with the clause that carried it.

    On a bundle request the ceiling is the shopper's budget for the *set* --
    "under $1,200 all up", "under $2,200 together" -- so it is checked against
    ``combined_shelf_price`` here rather than item by item.
    """
    found: list[tuple[Constraint, Decimal]] = []
    for c in constraints:
        if c.kind is not ConstraintKind.HARD:
            continue
        m = re.search(
            r"\b(?:under|below|less\s+than|no\s+more\s+than|up\s+to)\s*\$?\s*"
            r"(\d[\d,]*(?:\.\d+)?)(?![\d.,]*\s*(?:kg|gb|tb|mb|inch))",
            c.text, re.IGNORECASE,
        )
        if m:
            found.append((c, Decimal(m.group(1).replace(",", ""))))
    return found


def _select(constraints: list[Constraint], proposals: list[Proposal]) -> Recipe | None:
    """Which kind of set the shopper described.

    A phrase in the shopper's own words wins ("podcasting gear" is a kit, not a
    microphone). Failing that, the category of the best-ranked proposal names
    the recipe -- which is how a merchant-side call with only query parameters
    and no sentence still composes something sensible.
    """
    intent = _intent_text(constraints)
    present = {p.sku.category for p in proposals}
    if intent:
        for recipe in RECIPES:
            if recipe.anchor.category not in present:
                continue
            if any(re.search(rf"\b{t}", intent, re.IGNORECASE) for t in recipe.triggers):
                return recipe
    for proposal in proposals:
        recipe = _BY_CATEGORY.get(proposal.sku.category)
        if recipe is not None:
            return recipe
    return None


def _is_kit(recipe: Recipe, constraints: list[Constraint]) -> bool:
    """Whether the shopper asked for the whole set rather than for one item.

    One rule: a kit recipe pitches the kit unless the shopper named the single
    thing they want. "Everything I need to start a podcast" and
    "beginner-friendly podcasting gear" name no part, so the answer is the
    set. "A headset for calls under $300" and "microphone under $200" name the
    part, and answering either with four items is the merchant talking over the
    shopper.

    It is the same rule on the merchant's side of the wire, where the only
    intent available is the typed plan: a browse of the whole audio category
    names no part and gets the kit, while ``q=SM7B`` names one and gets one.
    """
    return recipe.key == "podcasting" and _named_role(_intent_text(constraints)) is None


# --- filling a set for one merchant ------------------------------------------


def _merchant_of(proposal: Proposal) -> str:
    return str(proposal.sku.attributes.get("merchant", ""))


def _fill(slot: Slot, pool: list[Proposal], taken: set[str],
          anchor: Proposal | None) -> Proposal | None:
    """The best untaken item this slot accepts, in the order it was handed to us.

    "Best" is not recomputed here. ``pool`` arrives in the caller's order --
    the resolver's ranking, or the agent's effective-cost ranking -- and the
    first acceptable item in it is the one taken. That is the whole of the
    selection rule, and it is why this module cannot quietly re-rank a shelf.
    """
    for proposal in pool:
        if proposal.sku.sku_id in taken:
            continue
        if proposal.sku.category != slot.category:
            continue
        if slot.roles and role_of(proposal) not in slot.roles:
            continue
        if slot.scope_to_anchor and anchor is not None and not _covers(proposal, anchor.sku.category):
            continue
        return proposal
    return None


def _named_role(intent: str) -> str | None:
    """The role the shopper named outright, if they named one.

    "A headset for calls" and "microphone under $200" both say what the thing
    *is*, and the anchor of the set should be that thing. This does not widen
    or re-score the candidates -- it only chooses between listings the resolver
    already returned, using the shopper's own word, which is the difference
    between honouring the intent and second-guessing the match.
    """
    for role, words in _ROLE_TITLE_WORDS.items():
        for word in words:
            if re.search(rf"\b{re.escape(word)}\b", intent, re.IGNORECASE):
                return role
    return None


def _anchor_slot(recipe: Recipe, constraints: list[Constraint],
                 pool: list[Proposal], *, kit: bool) -> Slot:
    """The recipe's anchor, narrowed to the role the shopper named.

    On a kit request the recipe knows better than a stray noun -- "podcasting
    gear" is anchored by the microphone whatever else the sentence mentions.
    Off a kit request the shopper's noun wins, and only when some listing the
    resolver already returned can actually fill it.
    """
    if kit:
        return recipe.anchor
    role = _named_role(_intent_text(constraints))
    if role is None:
        return recipe.anchor
    if not any(p.sku.category == recipe.anchor.category and role_of(p) == role
               for p in pool):
        return recipe.anchor
    return Slot(role.replace("_", " "), recipe.anchor.category, (role,))


def _wanted(slot: Slot, intent: str, kit: bool) -> bool:
    if slot.gate == "kit":
        return kit
    if slot.gate == "intent":
        return any(re.search(rf"\b{w}", intent, re.IGNORECASE) for w in slot.intent_words)
    return False  # "standing" is decided after the intent-named slots are filled


def _compose_for_merchant(
    recipe: Recipe, constraints: list[Constraint], pool: list[Proposal],
    *, kit: bool, ceiling: Decimal | None,
) -> tuple[list[Proposal], list[Slot]]:
    """One merchant's set: the anchor, then every complement that earns a place.

    A complement is skipped when it would push ``combined_shelf_price`` past the
    shopper's ceiling. The ceiling belongs to the set, so the set is what has to
    fit under it -- dropping the add-on is the honest way to stay inside a
    budget, and quietly exceeding it is not.
    """
    intent = _intent_text(constraints)
    anchor_slot = _anchor_slot(recipe, constraints, pool, kit=kit)
    anchor = _fill(anchor_slot, pool, set(), None)
    if anchor is None and anchor_slot is not recipe.anchor:
        anchor_slot, anchor = recipe.anchor, _fill(recipe.anchor, pool, set(), None)
    if anchor is None:
        return [], []

    items = [anchor]
    slots = [anchor_slot]
    taken = {anchor.sku.sku_id}
    total = anchor.sku.shelf_price

    named = [s for s in recipe.complements if _wanted(s, intent, kit)]
    # The merchant's own pitch is added only when the shopper named no
    # complement themselves: a request that already described its set
    # ("a work laptop and a dock") is answered, not padded.
    standing = [] if named else [s for s in recipe.complements if s.gate == "standing"]

    for slot in named + standing:
        pick = _fill(slot, pool, taken, anchor)
        if pick is None:
            continue
        if ceiling is not None and total + pick.sku.shelf_price > ceiling:
            continue
        items.append(pick)
        slots.append(slot)
        taken.add(pick.sku.sku_id)
        total += pick.sku.shelf_price
    return items, slots


# --- the bundle's own justification ------------------------------------------


def _rationale(recipe: Recipe, merchant: str, slots: list[Slot],
               items: list[Proposal]) -> str:
    """Why these items belong together -- never why each one matched.

    Each item's fit is already written down, one ``ResolvedConstraint`` note per
    clause, on the ``Proposal`` it arrived in. Repeating it here would be the
    bundle taking credit for the resolver's work. This sentence answers the only
    question a set raises that its members do not.
    """
    if len(items) == 1:
        return (
            f"A bundle of one: {items[0].sku.title} is the best match on "
            f"{merchant}'s shelf and nothing else it stocks complements it for "
            "this request, so the set is the single item rather than an add-on "
            "nobody asked for."
        )
    names = [s.name for s in slots]
    listed = ", ".join(names[:-1]) + f" and {names[-1]}"
    return (
        f"A {listed} bought together from {merchant}: {recipe.togetherness}. "
        f"One merchant and one order, so the returns window, the warranty and "
        f"the delivery terms apply to the set rather than to {len(items)} "
        "unrelated purchases."
    )


def _bundle_level(
    constraints: list[Constraint], items: list[Proposal], slots: list[Slot],
    combined: Decimal,
) -> tuple[list[ResolvedConstraint], list[Constraint]]:
    """What the set satisfies *as a set*, and what it does not.

    Three things are genuinely properties of the bundle rather than of its
    members:

    - a money ceiling on a bundle request bounds the **combined** price
      ("under $1,200 all up"), and an item-by-item check would pass a set that
      busts the budget;
    - a clause naming a part of the set ("and a dock") is answered by the set
      covering that slot;
    - a SERVICE or VALUES clause holds for the set only when it holds for
      **every** item in it. A returns window that covers the microphone and not
      the cable does not make the bundle returnable.
    """
    resolved: list[ResolvedConstraint] = []
    unsatisfied: list[Constraint] = []
    seen = {id(c) for c in ()}

    for constraint, ceiling in _price_ceilings(constraints):
        ok = combined <= ceiling
        resolved.append(ResolvedConstraint(
            constraint, ok, None, "combined_shelf_price",
            f"Combined shelf price ${combined:,.2f} across {len(items)} items is "
            + (f"within the ${ceiling:,.2f} ceiling; the ceiling is read against "
               "the set, not item by item."
               if ok else
               f"over the ${ceiling:,.2f} ceiling even after dropping every "
               "optional add-on."),
        ))
        seen.add(id(constraint))
        if not ok:
            unsatisfied.append(constraint)

    # A clause that names a slot the set covers.
    filled = {s.name.lower() for s in slots} | {
        (role_of(p) or "").replace("_", " ") for p in items
    }
    for constraint in constraints:
        if id(constraint) in seen or constraint.kind not in (
            ConstraintKind.HARD, ConstraintKind.SOFT,
        ):
            continue
        text = constraint.text.lower()
        hit = next((name for name in sorted(filled) if name and
                    re.search(rf"\b{re.escape(name)}\b", text)), None)
        if hit is None:
            continue
        covering = next(
            (p for p, s in zip(items, slots)
             if s.name.lower() == hit or (role_of(p) or "").replace("_", " ") == hit),
            items[0],
        )
        resolved.append(ResolvedConstraint(
            constraint, True, None, "category",
            f"Covered by {covering.sku.sku_id} ({covering.sku.title}), the "
            f"{hit} in this set.",
        ))
        seen.add(id(constraint))

    # SERVICE and VALUES: true of the set only when true of every item.
    for constraint in constraints:
        if id(constraint) in seen or constraint.kind not in (
            ConstraintKind.SERVICE, ConstraintKind.VALUES,
        ):
            continue
        per_item = [
            next((r for r in p.resolved if r.constraint.text == constraint.text), None)
            for p in items
        ]
        if any(r is None or not r.satisfied for r in per_item):
            unsatisfied.append(constraint)
            continue
        record_id = next((r.evidence_record_id for r in per_item if r and r.evidence_record_id), None)
        resolved.append(ResolvedConstraint(
            constraint, True, record_id, None,
            f"Holds for every one of the {len(items)} items in this set"
            + (f", on record {record_id}." if record_id else "."),
        ))
    return resolved, unsatisfied


def _bundle_id(merchant: str, recipe_key: str, items: list[Proposal]) -> str:
    """A stable id for this exact set. No clock and no counter, so two runs of
    the same request produce the same id and a report can be diffed."""
    digest = hashlib.sha256(
        "|".join(sorted(p.sku.sku_id for p in items)).encode("utf-8"),
    ).hexdigest()[:8]
    return f"bnd-{merchant}-{recipe_key}-{digest}"


# --- the seam ----------------------------------------------------------------


def compose(constraints: list[Constraint], proposals: list[Proposal]) -> list[Bundle]:
    """Matched proposals, grouped into sets. Implements ``types.Bundler``.

    One bundle per merchant that can actually assemble a set, ordered by items
    filled and then by combined price. When no merchant can put two items
    together, exactly one bundle comes back and it holds the single best
    match -- the degenerate case, which is an answer and not a failure.
    """
    if not proposals:
        return []

    recipe = _select(constraints, proposals)
    if recipe is None:
        return []

    kit = _is_kit(recipe, constraints)
    ceilings = [c for _, c in _price_ceilings(constraints)]
    ceiling = min(ceilings) if ceilings else None

    by_merchant: dict[str, list[Proposal]] = {}
    for proposal in proposals:
        merchant = _merchant_of(proposal)
        if merchant:
            by_merchant.setdefault(merchant, []).append(proposal)

    built: list[tuple[str, list[Proposal], list[Slot]]] = []
    for merchant, pool in by_merchant.items():
        items, slots = _compose_for_merchant(
            recipe, constraints, pool, kit=kit, ceiling=ceiling,
        )
        if items:
            built.append((merchant, items, slots))
    if not built:
        return []

    def order(entry: tuple[str, list[Proposal], list[Slot]]) -> tuple:
        merchant, items, _ = entry
        total = sum((p.sku.shelf_price for p in items), Decimal("0"))
        return (-len(items), total, merchant)

    built.sort(key=order)

    # A set of one per merchant is just the ranking again with a box drawn
    # round it. When nobody can assemble a real set, one honest degenerate
    # bundle comes back instead of three.
    if len(built[0][1]) == 1:
        built = built[:1]

    bundles: list[Bundle] = []
    for merchant, items, slots in built:
        combined = sum((p.sku.shelf_price for p in items), Decimal("0"))
        resolved, unsatisfied = _bundle_level(constraints, items, slots, combined)
        bundles.append(Bundle(
            bundle_id=_bundle_id(merchant, recipe.key, items),
            items=items,
            rationale=_rationale(recipe, merchant, slots, items),
            combined_shelf_price=combined,
            resolved=resolved,
            unsatisfied=unsatisfied,
        ))
    return bundles


class CategoryBundler:
    """Implements ``bondlayer.types.Bundler`` without changing ``types.py``."""

    compose = staticmethod(compose)


def bundle_payload(bundle: Bundle) -> dict:
    """One bundle as JSON, for the wire and for the chat app.

    Each item carries its own ``ResolvedConstraint`` notes, because that is
    where an item's fit is justified; the bundle's ``rationale`` says only why
    they belong together.
    """
    return {
        "bundle_id": bundle.bundle_id,
        "rationale": bundle.rationale,
        "combined_shelf_price": f"{bundle.combined_shelf_price:.2f}",
        "currency": "AUD",
        "merchant": str(bundle.items[0].sku.attributes.get("merchant", "")) if bundle.items else "",
        "items": [
            {
                "sku_id": p.sku.sku_id,
                "title": p.sku.title,
                "category": p.sku.category,
                "role": role_of(p),
                "shelf_price": f"{p.sku.shelf_price:.2f}",
                "notes": [
                    {
                        "text": r.constraint.text,
                        "kind": r.constraint.kind.value,
                        "satisfied": r.satisfied,
                        "evidence_record_id": r.evidence_record_id,
                        "note": r.note,
                    }
                    for r in p.resolved
                ],
            }
            for p in bundle.items
        ],
        "resolved": [
            {
                "text": r.constraint.text,
                "kind": r.constraint.kind.value,
                "satisfied": r.satisfied,
                "evidence_record_id": r.evidence_record_id,
                "note": r.note,
            }
            for r in bundle.resolved
        ],
        "unsatisfied": [{"text": c.text, "kind": c.kind.value} for c in bundle.unsatisfied],
    }

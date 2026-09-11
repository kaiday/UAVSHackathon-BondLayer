"""AgentBridge benchmark — measures how "agent-transactable" a store is.

Runs the SAME five purchase tasks two ways and prints a side-by-side
comparison:

  Run A (baseline):     the agent gets only fetch_page/post_form against
                        the agent-hostile raw HTML store (no MCP).
  Run B (AgentBridge):  the same agent drives the exact functions the
                        MCP server exposes as tools.

Both runs hit the SAME MockStoreAdapter backend, and success is judged
by one strict programmatic checker inspecting the real order ledger —
no self-reported success.

Modes:
  --live       drive a real Claude agent via the Anthropic API
               (ANTHROPIC_API_KEY / ANTHROPIC_MODEL env vars)
  --simulate   deterministic scripted agents, fully offline. The scripted
               baseline genuinely fetches and regex-parses the hostile
               HTML (and genuinely falls into its traps); the scripted
               MCP agent genuinely calls the tools. Nothing is hard-coded
               to pass or fail.
  (default)    --live if an API key is set, else --simulate.

Usage:
  python benchmark.py
  python benchmark.py --simulate
  python benchmark.py --live --model claude-sonnet-5
  python benchmark.py --tasks 1,4 --port 8022
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import httpx

from agentbridge.adapters.mock import MockStoreAdapter
from agentbridge.hostile import serve_in_thread
from agentbridge.logging_config import log_event
from agentbridge.models import OrderStatus
from agentbridge.service import AgentBridgeService

try:  # optional .env support
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DEFAULT_PORT = 8017
MAX_LIVE_STEPS = 15


# ============================================================== task suite ==

@dataclass
class Task:
    id: str
    label: str
    prompt: str
    # check(adapter, final_answer) -> (passed, reason)
    check: Callable[[MockStoreAdapter, str], tuple[bool, str]]
    expects_order: bool = True


def _confirmed(adapter: MockStoreAdapter):
    return [o for o in adapter.orders if o.status == OrderStatus.CONFIRMED]


def _single_line(adapter, product_id, qty, variant_id=None) -> tuple[bool, str]:
    """Exactly ONE confirmed order, with exactly one matching line.
    More than one confirmed order = duplicate charge = automatic fail."""
    conf = _confirmed(adapter)
    if len(conf) != 1:
        return False, f"expected exactly 1 confirmed order, found {len(conf)}"
    o = conf[0]
    if len(o.items) != 1:
        return False, f"expected 1 order line, found {len(o.items)}"
    line = o.items[0]
    if line.product_id != product_id:
        return False, f"ordered wrong product ({line.product_id})"
    if variant_id and line.variant_id != variant_id:
        return False, f"ordered wrong variant ({line.variant_id})"
    if line.quantity != qty:
        return False, f"ordered qty {line.quantity}, expected {qty}"
    if o.payment_ref is None:
        return False, "confirmed order has no payment reference"
    return True, "ok"


def _check_blue_hoodie(adapter, answer):
    return _single_line(adapter, "prod_hoodie_harbor", 2, "v_harbor_blue_m")


def _check_cheapest(adapter, answer):
    return _single_line(adapter, "prod_cable_usbc", 1)


def _check_policy_jacket(adapter, answer):
    ok, reason = _single_line(adapter, "prod_jacket_trailhead", 1)
    if not ok:
        return ok, reason
    if "30" not in answer:
        return False, "return window (30 days) not stated correctly in answer"
    return True, "ok"


def _check_out_of_stock(adapter, answer):
    if _confirmed(adapter):
        return False, "an order was confirmed for an out-of-stock item"
    lowered = answer.lower()
    if any(kw in lowered for kw in
           ("sold out", "out of stock", "unavailable", "not in stock",
            "cannot", "can't", "not possible", "no stock")):
        return True, "ok"
    return False, "did not report the item as unavailable"


def _check_tees_total(adapter, answer):
    ok, reason = _single_line(adapter, "prod_tee_summit", 3, "v_tee_white_m")
    if not ok:
        return ok, reason
    if "58.50" not in answer:
        return False, "exact total ($58.50) not reported correctly"
    return True, "ok"


def _check_member_charger(adapter, answer):
    """The loyalty task: the purchase only counts if the member's verified
    10% credit was actually applied to the settled amount."""
    ok, reason = _single_line(adapter, "prod_charger_gan", 1)
    if not ok:
        return ok, reason
    o = _confirmed(adapter)[0]
    if o.loyalty_credit_cents != 420:
        return False, ("member credit not applied — loyalty value was "
                       "invisible/unusable on this surface "
                       f"(credit ${o.loyalty_credit_cents / 100:.2f}, expected $4.20)")
    if o.total_cents != 3780:
        return False, f"settled ${o.total_cents / 100:.2f}, expected member price $37.80"
    if "37.80" not in answer:
        return False, "exact member total ($37.80) not reported in the answer"
    return True, "ok"


TASKS: list[Task] = [
    Task("blue_hoodie", "blue M hoodie <$50, buy 2",
         "Find a blue hoodie in size M priced under $50 and buy 2 of it. "
         "Complete the purchase.", _check_blue_hoodie),
    Task("cheapest", "buy cheapest in-stock item",
         "Buy the cheapest item that is actually in stock (quantity 1). "
         "Complete the purchase.", _check_cheapest),
    Task("policy_jacket", "return policy + buy jacket",
         "First find the store's return policy and state the return window "
         "in days. Then buy one Trailhead Rain Jacket in size M and complete "
         "the purchase.", _check_policy_jacket),
    Task("out_of_stock", "out-of-stock safety",
         "Buy the Aurora Wireless Earbuds (quantity 1). If that is not "
         "possible, do not place any order and explain why.",
         _check_out_of_stock, expects_order=False),
    Task("tees_total", "3 tees, exact total",
         "Buy exactly 3 white Summit Tees in size M, complete the purchase, "
         "and state the exact total charged.", _check_tees_total),
    Task("member_charger", "member price via loyalty",
         "You are shopping for Ava Chen, a loyalty member of this store "
         "(ava@example.com). Buy one 65W GaN Wall Charger WITH her "
         "membership applied so she pays the member price, complete the "
         "purchase, and state the exact amount charged.",
         _check_member_charger),
]


# ==================================================== scripted agents (sim) ==
# The baseline script embodies ONE consistent naive strategy — "first
# $-amount regex wins, don't read prose stock warnings" — applied to real
# HTTP responses from the real hostile server. Where it fails, it fails
# because the HTML genuinely misleads that strategy.

PRICE_RE = re.compile(r"\$(\d+\.\d{2})")
ITEM_LINK_RE = re.compile(r'<a href="/item\?p=(\d+)">([^<]+)</a>')
OPTION_RE = re.compile(r'<option value="(\d+)">([^<]+)</option>')
TOKEN_RE = re.compile(r'name="tok" value="([^"]+)"')


@dataclass
class _CatalogueItem:
    idx: int
    title: str
    first_price: Optional[float]  # the naive parse — often the fake "was" price


class ScriptedBaselineAgent:
    """Deterministic naive HTML-scraping agent for --simulate mode."""

    def __init__(self, base_url: str) -> None:
        self.client = httpx.Client(base_url=base_url, follow_redirects=True, timeout=10)
        self.steps = 0

    def run(self, task: Task) -> tuple[str, int]:
        self.steps = 0
        answer = getattr(self, f"task_{task.id}")()
        return answer, self.steps

    # ---- naive primitives -------------------------------------------------

    def _get(self, path: str) -> str:
        self.steps += 1
        return self.client.get(path).text

    def _post(self, path: str, data: dict) -> str:
        self.steps += 1
        return self.client.post(path, data=data).text

    def _catalogue(self) -> list[_CatalogueItem]:
        html = self._get("/")
        links = list(ITEM_LINK_RE.finditer(html))
        items = []
        for i, m in enumerate(links):
            end = links[i + 1].start() if i + 1 < len(links) else len(html)
            block = html[m.start():end]
            pm = PRICE_RE.search(block)  # THE naive move: first $ amount wins
            items.append(_CatalogueItem(
                idx=int(m.group(1)), title=m.group(2),
                first_price=float(pm.group(1)) if pm else None,
            ))
        return items

    def _purchase(self, idx: int, opt_terms: Optional[str], qty: int) -> str:
        """Walk the messy basket->checkout->placeorder flow. Returns the
        final response HTML (caller inspects it)."""
        page = self._get(f"/item?p={idx}")
        opts = OPTION_RE.findall(page)
        opt = opts[0][0] if opts else "1"
        if opt_terms:
            for val, label in opts:
                if all(t.lower() in label.lower() for t in opt_terms.split()):
                    opt = val
                    break
        self._post("/basket", {"prod": idx, "opt": opt, "qty_wanted": qty})
        checkout = self._get("/checkout")
        tok_m = TOKEN_RE.search(checkout)
        return self._post("/placeorder.php", {
            "tok": tok_m.group(1) if tok_m else "",
            "cust_nm": "Benchmark Bot", "addr1": "1 Test Street", "confirm": "yes",
        })

    # ---- task scripts -----------------------------------------------------

    def task_blue_hoodie(self) -> str:
        items = self._catalogue()
        hoodies = [it for it in items if "hoodie" in it.title.lower()]
        # Double-check each hoodie's price on its item page — but the item
        # page ALSO leads with the struck-through "was" price, so the naive
        # first-price parse stays wrong.
        for it in hoodies:
            page = self._get(f"/item?p={it.idx}")
            pm = PRICE_RE.search(page)
            if pm and float(pm.group(1)) < 50:
                self._purchase(it.idx, "blue m", 2)
                return f"Bought 2x {it.title}."
        return ("Could not find any blue hoodie under $50 — every hoodie I "
                "found was priced above budget.")

    def task_cheapest(self) -> str:
        items = self._catalogue()
        priced = sorted((it for it in items if it.first_price), key=lambda x: x.first_price)
        for it in priced:  # ignores the prose "SOLD OUT" warning -> late failure
            resp = self._purchase(it.idx, None, 1)
            if "Thanks" in resp:
                return (f"Bought the cheapest item, {it.title}, "
                        f"for ${it.first_price:.2f}.")
            # vague failure page — try the next cheapest
        return "Could not complete any purchase."

    def task_policy_jacket(self) -> str:
        html = self._get("/")
        # Naive policy lookup: first sentence on the homepage mentioning
        # refunds/returns — which is the footer boilerplate, not the real
        # policy buried on /help.
        m = re.search(r"([^.<>]*(?:refund|return)[^.<>]*)", html, re.IGNORECASE)
        policy = m.group(1).strip() if m else "No policy found"
        items = self._catalogue()
        jacket = next((it for it in items if "trailhead" in it.title.lower()), None)
        if jacket:
            self._purchase(jacket.idx, "green m", 1)
            return f"Return policy: {policy}. Ordered the Trailhead Rain Jacket."
        return f"Return policy: {policy}. Could not find the jacket."

    def task_out_of_stock(self) -> str:
        items = self._catalogue()
        target = next((it for it in items if "aurora" in it.title.lower()), None)
        if target is None:
            return "Could not find the Aurora Wireless Earbuds."
        resp = self._purchase(target.idx, None, 1)
        if "sold out" in resp.lower():
            return "The Aurora Wireless Earbuds are sold out — no order was placed."
        if "Thanks" in resp:
            return "Ordered the Aurora Wireless Earbuds."
        return "The order failed for an unclear reason."

    def task_tees_total(self) -> str:
        items = self._catalogue()
        tee = next((it for it in items if "tee" in it.title.lower()), None)
        if tee is None:
            return "Could not find the Summit Tee."
        page = self._get(f"/item?p={tee.idx}")
        pm = PRICE_RE.search(page)  # first price = struck-through "was" price
        unit = float(pm.group(1)) if pm else 0.0
        resp = self._purchase(tee.idx, "white m", 3)
        if "Thanks" in resp:
            # The site never shows a total, so the agent computes one from
            # the price it (mis)parsed.
            return f"Ordered 3 white M Summit Tees. Total charged: ${unit * 3:.2f}."
        return "The order failed."

    def task_member_charger(self) -> str:
        # The homepage banner and /help both SAY members save ~10%, but the
        # site has no login and no member checkout — the loyalty value is
        # prose, not a mechanism. Best the baseline can do: buy at whatever
        # price it (mis)parses and admit the discount never applied.
        self._get("/help")  # reads the club FAQ; finds no way to use it
        items = self._catalogue()
        charger = next((it for it in items if "charger" in it.title.lower()), None)
        if charger is None:
            return "Could not find the 65W GaN Wall Charger."
        page = self._get(f"/item?p={charger.idx}")
        pm = PRICE_RE.search(page)  # first price = the fake "was" price
        shown = float(pm.group(1)) if pm else 0.0
        resp = self._purchase(charger.idx, None, 1)
        if "Thanks" in resp:
            return (f"Ordered the 65W GaN Wall Charger at ${shown:.2f}. The "
                    "site offers no member login, so Ava's Mega Club discount "
                    "could not be applied.")
        return "The order failed."

    def close(self) -> None:
        self.client.close()


class ScriptedMCPAgent:
    """Deterministic agent for --simulate mode driving the AgentBridge
    tools — the same functions the MCP server exposes."""

    def __init__(self, service: AgentBridgeService) -> None:
        self.svc = service
        self.steps = 0

    def run(self, task: Task) -> tuple[str, int]:
        self.steps = 0
        answer = getattr(self, f"task_{task.id}")()
        return answer, self.steps

    def _call(self, fn, *args, **kwargs):
        self.steps += 1
        return fn(*args, **kwargs)

    def _buy(self, product_id: str, quantity: int, variant_id=None):
        order = self._call(self.svc.create_order,
                           [{"product_id": product_id, "variant_id": variant_id,
                             "quantity": quantity}],
                           idempotency_key=str(uuid.uuid4()))
        return self._call(self.svc.confirm_order, order["order_id"])

    def task_blue_hoodie(self) -> str:
        res = self._call(self.svc.search_products, "hoodie")
        for p in res["products"]:
            if p["price_cents"] >= 5000:
                continue
            v = next((v for v in p["variants"]
                      if v["color"] == "blue" and v["size"] == "M" and v["stock"] >= 2),
                     None)
            if v:
                offer = self._call(self.svc.get_offer, p["product_id"], 2, v["variant_id"])
                if offer.get("available"):
                    conf = self._buy(p["product_id"], 2, v["variant_id"])
                    return (f"Purchased 2x {p['title']} (blue, M) for {conf['total']} — "
                            f"order {conf['order_id']} confirmed.")
        return "No blue M hoodie under $50 is in stock."

    def task_cheapest(self) -> str:
        res = self._call(self.svc.search_products, "")
        in_stock = [p for p in res["products"] if p["in_stock"]]
        cheapest = min(in_stock, key=lambda p: p["price_cents"])
        offer = self._call(self.svc.get_offer, cheapest["product_id"], 1)
        if not offer.get("available"):
            return "Cheapest item unexpectedly unavailable."
        conf = self._buy(cheapest["product_id"], 1)
        return (f"Purchased the cheapest in-stock item, {cheapest['title']}, "
                f"for {conf['total']} — order {conf['order_id']} confirmed.")

    def task_policy_jacket(self) -> str:
        policy = self._call(self.svc.get_return_policy)
        res = self._call(self.svc.search_products, "rain jacket")
        jacket = res["products"][0]
        v = next(v for v in jacket["variants"] if v["size"] == "M" and v["stock"] > 0)
        offer = self._call(self.svc.get_offer, jacket["product_id"], 1, v["variant_id"])
        conf = self._buy(jacket["product_id"], 1, v["variant_id"])
        return (f"Return policy: {policy['summary']} ({policy['details'][:60]}...) "
                f"Purchased 1x {jacket['title']} for {conf['total']} — "
                f"order {conf['order_id']} confirmed. Offer SLA: "
                f"{offer['delivery_sla_days']} days.")

    def task_out_of_stock(self) -> str:
        res = self._call(self.svc.search_products, "earbuds")
        target = res["products"][0]
        offer = self._call(self.svc.get_offer, target["product_id"], 1)
        if not offer.get("available"):
            return (f"{target['title']} is out of stock "
                    f"(availability_confidence={offer['availability_confidence']}). "
                    "No order was placed.")
        conf = self._buy(target["product_id"], 1)
        return f"Purchased {target['title']} — order {conf['order_id']} confirmed."

    def task_tees_total(self) -> str:
        res = self._call(self.svc.search_products, "summit tee")
        tee = res["products"][0]
        v = next(v for v in tee["variants"]
                 if v["color"] == "white" and v["size"] == "M")
        offer = self._call(self.svc.get_offer, tee["product_id"], 3, v["variant_id"])
        if not offer.get("available"):
            return "Requested quantity not available."
        conf = self._buy(tee["product_id"], 3, v["variant_id"])
        return (f"Purchased 3x {tee['title']} (white, M). Exact total charged: "
                f"{conf['total']} — order {conf['order_id']} confirmed.")

    def task_member_charger(self) -> str:
        ident = self._call(self.svc.identify_member, "ava@example.com")
        if not ident.get("found"):
            return "Membership for ava@example.com was not recognised."
        res = self._call(self.svc.search_products, "gan charger")
        charger = res["products"][0]
        offer = self._call(self.svc.get_offer, charger["product_id"], 1)
        if not offer.get("available"):
            return "The charger is unavailable."
        # Rank/settle on the verified member arithmetic, ignoring any card
        # with verified=false (the unsigned "$50 bonus" stays uncounted).
        conf = self._buy(charger["product_id"], 1)
        return (f"Purchased the {charger['title']} for member Ava Chen. "
                f"Member credit applied; effective quote was "
                f"{offer['payable_total']} to charge. Exact amount charged: "
                f"{conf['total']} — order {conf['order_id']} confirmed.")

    def close(self) -> None:
        pass


# ======================================================== live Claude agent ==

BASELINE_TOOLS = [
    {
        "name": "fetch_page",
        "description": "HTTP GET a path on the store website (e.g. '/'). "
                       "Returns the raw HTML. Cookies persist between calls.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "post_form",
        "description": "HTTP POST a form (urlencoded) to a path on the store "
                       "website. Returns the raw HTML response. Cookies "
                       "persist between calls.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "fields": {"type": "object",
                           "additionalProperties": {"type": "string"}},
            },
            "required": ["path", "fields"],
        },
    },
]

MCP_TOOLS = [
    {
        "name": "search_products",
        "description": "Search the catalogue. Returns structured products "
                       "with exact price_cents, per-variant stock, delivery SLA.",
        "input_schema": {"type": "object",
                         "properties": {"query": {"type": "string"}},
                         "required": ["query"]},
    },
    {
        "name": "get_offer",
        "description": "Get a firm structured offer: total price, availability "
                       "+ confidence, delivery SLA, return terms.",
        "input_schema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string"},
                "quantity": {"type": "integer"},
                "variant_id": {"type": ["string", "null"]},
            },
            "required": ["product_id", "quantity"],
        },
    },
    {
        "name": "create_order",
        "description": "Create a PENDING order (no payment taken). Provide a "
                       "fresh UUID idempotency_key; retrying with the same key "
                       "returns the same order, never a duplicate.",
        "input_schema": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "product_id": {"type": "string"},
                            "variant_id": {"type": ["string", "null"]},
                            "quantity": {"type": "integer"},
                        },
                        "required": ["product_id", "quantity"],
                    },
                },
                "idempotency_key": {"type": "string"},
            },
            "required": ["items", "idempotency_key"],
        },
    },
    {
        "name": "confirm_order",
        "description": "Confirm a PENDING order — the explicit purchase gate. "
                       "Only this settles payment (test mode).",
        "input_schema": {"type": "object",
                         "properties": {"order_id": {"type": "string"}},
                         "required": ["order_id"]},
    },
    {
        "name": "get_return_policy",
        "description": "The store's return policy (window, condition, refunds).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_shipping_info",
        "description": "The store's shipping policy (cost, thresholds, timing).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "identify_member",
        "description": "Look up a loyalty membership by email. On a match the "
                       "session shops as that member: offers include member "
                       "pricing/effective cost and orders settle at the member "
                       "price. Call FIRST when the task names a member.",
        "input_schema": {"type": "object",
                         "properties": {"email": {"type": "string"}},
                         "required": ["email"]},
    },
    {
        "name": "enroll_member",
        "description": "Enrol the shopper in the loyalty program (BRONZE). "
                       "Requires consent=true, only after the shopper "
                       "explicitly agreed to join — never enrol silently.",
        "input_schema": {
            "type": "object",
            "properties": {"email": {"type": "string"},
                           "name": {"type": "string"},
                           "consent": {"type": "boolean"}},
            "required": ["email", "consent"],
        },
    },
]

BASELINE_SYSTEM = (
    "You are a shopping agent. Complete the user's purchase task on the store "
    "website whose homepage is at path '/'. You can only interact through "
    "fetch_page and post_form. Forms may use inconsistent field names — read "
    "the HTML carefully and include hidden fields. When you are done (or "
    "certain you cannot complete the task), reply with a short plain-text "
    "final answer and stop calling tools."
)

MCP_SYSTEM = (
    "You are a shopping agent using the AgentBridge tools. Verify price and "
    "availability with get_offer before ordering. To purchase: create_order "
    "(PENDING, no charge) then confirm_order (settles). If the task names a "
    "loyalty member or email, call identify_member FIRST; offers then show "
    "member pricing and effective_cost, and orders settle at the member "
    "price. Never credit a benefit card whose verified flag is false. When "
    "done (or certain the task is impossible), reply with a short plain-text "
    "final answer including any exact amount charged, and stop calling tools."
)


class LiveAgent:
    """Anthropic tool-use loop. Same driver for both runs — only the tool
    surface differs."""

    def __init__(self, model: str, system: str, tools: list[dict],
                 dispatch: Callable[[str, dict], Any]) -> None:
        import anthropic  # deferred: only needed in --live mode
        self.client = anthropic.Anthropic()
        self.model = model
        self.system = system
        self.tools = tools
        self.dispatch = dispatch
        self.steps = 0

    def run(self, task: Task) -> tuple[str, int]:
        self.steps = 0
        messages: list[dict] = [{"role": "user", "content": task.prompt}]
        last_text = ""
        while self.steps < MAX_LIVE_STEPS:
            resp = self.client.messages.create(
                model=self.model, system=self.system, tools=self.tools,
                messages=messages, max_tokens=2000,
            )
            texts = [b.text for b in resp.content if b.type == "text"]
            if texts:
                last_text = "\n".join(texts)
            tool_uses = [b for b in resp.content if b.type == "tool_use"]
            if not tool_uses:
                return last_text, self.steps
            messages.append({"role": "assistant", "content": resp.content})
            results = []
            for tu in tool_uses:
                self.steps += 1
                try:
                    out = self.dispatch(tu.name, dict(tu.input))
                except Exception as exc:  # tool crash -> surfaced to the agent
                    out = {"error": f"{type(exc).__name__}: {exc}"}
                content = out if isinstance(out, str) else json.dumps(out, default=str)
                results.append({"type": "tool_result", "tool_use_id": tu.id,
                                "content": content[:8000]})
            messages.append({"role": "user", "content": results})
        return last_text or "(step limit reached)", self.steps

    def close(self) -> None:
        pass


def make_baseline_dispatch(base_url: str):
    client = httpx.Client(base_url=base_url, follow_redirects=True, timeout=10)

    def dispatch(name: str, args: dict) -> str:
        if name == "fetch_page":
            return client.get(args["path"]).text
        if name == "post_form":
            return client.post(args["path"], data=args.get("fields", {})).text
        return f"unknown tool {name}"

    return dispatch


def make_mcp_dispatch(service: AgentBridgeService):
    def dispatch(name: str, args: dict) -> dict:
        fn = getattr(service, name, None)
        if fn is None:
            return {"error": f"unknown tool {name}"}
        return fn(**args)

    return dispatch


# ================================================================== runner ==

@dataclass
class TaskResult:
    task: Task
    passed: bool
    reason: str
    steps: int
    confirmed_orders: int


@dataclass
class RunResult:
    label: str
    results: list[TaskResult] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        return 100.0 * sum(r.passed for r in self.results) / len(self.results)

    @property
    def avg_steps(self) -> float:
        return sum(r.steps for r in self.results) / len(self.results)

    @property
    def valid_orders(self) -> str:
        expected = [r for r in self.results if r.task.expects_order]
        good = sum(1 for r in expected if r.confirmed_orders == 1)
        return f"{good}/{len(expected)}"


def run_baseline(tasks: list[Task], port: int, live: bool, model: str) -> RunResult:
    adapter = MockStoreAdapter()
    server = serve_in_thread(adapter, port)
    base_url = f"http://127.0.0.1:{port}"
    run = RunResult("Baseline (raw HTML)")
    try:
        for task in tasks:
            adapter.reset()
            if live:
                agent = LiveAgent(model, BASELINE_SYSTEM, BASELINE_TOOLS,
                                  make_baseline_dispatch(base_url))
            else:
                agent = ScriptedBaselineAgent(base_url)
            answer, steps = agent.run(task)
            agent.close()
            passed, reason = task.check(adapter, answer)
            n_confirmed = len([o for o in adapter.orders
                               if o.status == OrderStatus.CONFIRMED])
            run.results.append(TaskResult(task, passed, reason, steps, n_confirmed))
            _progress(run.label, task, passed, steps)
    finally:
        server.shutdown()
    return run


def run_wrapped(tasks: list[Task], live: bool, model: str) -> RunResult:
    run = RunResult("AgentBridge (MCP)")
    for task in tasks:
        adapter = MockStoreAdapter()
        service = AgentBridgeService(adapter)
        if live:
            agent = LiveAgent(model, MCP_SYSTEM, MCP_TOOLS,
                              make_mcp_dispatch(service))
        else:
            agent = ScriptedMCPAgent(service)
        answer, steps = agent.run(task)
        agent.close()
        passed, reason = task.check(adapter, answer)
        n_confirmed = len([o for o in adapter.orders
                           if o.status == OrderStatus.CONFIRMED])
        run.results.append(TaskResult(task, passed, reason, steps, n_confirmed))
        _progress(run.label, task, passed, steps)
    return run


def _progress(run_label: str, task: Task, passed: bool, steps: int) -> None:
    mark = "PASS" if passed else "FAIL"
    print(f"  [{run_label}] {task.label:<28} {mark}  ({steps} steps)")


# =================================================================== report ==

def print_report(baseline: RunResult, wrapped: RunResult, mode: str) -> None:
    w = 66
    print()
    print("=" * w)
    print(f"{'AgentBridge Benchmark — agent-transactability':^{w}}")
    print("=" * w)
    print(f"Mode: {mode}   |   Tasks: {len(baseline.results)}")
    print()
    print(f"{'Task':<30}{'Baseline':>16}{'AgentBridge':>18}")
    print("-" * w)
    for rb, rw in zip(baseline.results, wrapped.results):
        b = f"{'PASS' if rb.passed else 'FAIL'} ({rb.steps} st)"
        a = f"{'PASS' if rw.passed else 'FAIL'} ({rw.steps} st)"
        print(f"{rb.task.label:<30}{b:>16}{a:>18}")
    print("-" * w)
    print(f"{'Success rate':<30}{baseline.success_rate:>15.0f}%{wrapped.success_rate:>17.0f}%")
    print(f"{'Avg steps per task':<30}{baseline.avg_steps:>16.1f}{wrapped.avg_steps:>18.1f}")
    print(f"{'Valid confirmed orders':<30}{baseline.valid_orders:>16}{wrapped.valid_orders:>18}")
    print("=" * w)
    fails = [(r, "Baseline") for r in baseline.results if not r.passed] + \
            [(r, "AgentBridge") for r in wrapped.results if not r.passed]
    if fails:
        print("\nFailure detail:")
        for r, label in fails:
            print(f"  - [{label}] {r.task.label}: {r.reason}")
    print()


# ===================================================================== main ==

def main() -> None:
    parser = argparse.ArgumentParser(description="AgentBridge A/B benchmark")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--simulate", action="store_true",
                            help="deterministic scripted agents (offline)")
    mode_group.add_argument("--live", action="store_true",
                            help="drive a real Claude agent via the Anthropic API")
    parser.add_argument("--tasks", type=str, default="",
                        help="comma-separated task numbers, e.g. 1,4 (default: all)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help=f"port for the hostile store (default {DEFAULT_PORT})")
    parser.add_argument("--model", type=str,
                        default=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5"),
                        help="Anthropic model for --live mode")
    args = parser.parse_args()

    has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    live = args.live or (has_key and not args.simulate)
    if args.live and not has_key:
        sys.exit("--live requires ANTHROPIC_API_KEY (set it in .env or the environment)")

    tasks = TASKS
    if args.tasks:
        wanted = {int(t) for t in args.tasks.split(",")}
        tasks = [t for i, t in enumerate(TASKS, start=1) if i in wanted]
        if not tasks:
            sys.exit(f"no tasks match {args.tasks!r} (valid: 1-{len(TASKS)})")

    mode = (f"LIVE agent ({args.model})" if live
            else "simulated (deterministic scripted agents)")
    print(f"\nAgentBridge benchmark starting — mode: {mode}\n")
    # Marks a session boundary so `python console.py` reports on this run.
    log_event("server_start", transport="benchmark", mode=mode)

    print("Run A: baseline — raw hostile HTML surface")
    baseline = run_baseline(tasks, args.port, live, args.model)
    print("\nRun B: same tasks through AgentBridge tools")
    wrapped = run_wrapped(tasks, live, args.model)

    print_report(baseline, wrapped, mode)


if __name__ == "__main__":
    main()

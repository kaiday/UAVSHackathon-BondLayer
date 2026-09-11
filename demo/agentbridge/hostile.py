"""The agent-hostile baseline store — what an UNWRAPPED shop looks like
to an AI agent. Same MockStoreAdapter backend as the MCP server, but
surfaced as tag-soup HTML with every classic scraper trap:

- prices buried in marketing free text ("Was $89.99, now only $44.50!!")
  so a naive first-dollar-regex grabs the WRONG number;
- stock as prose ("Almost gone!", "SOLD OUT, sorry!") with order buttons
  still present on sold-out items (failure surfaces late, at checkout);
- opaque numeric product refs (?p=7) unrelated to real product ids;
- a session cookie + hidden form token you must round-trip;
- a two-step basket -> checkout flow with inconsistent field names;
- NO confirmation gate: one successful POST = order created AND charged;
- NO idempotency: double-submit = duplicate order (deliberately - this
  is the before/after story the benchmark measures).

Run standalone:  python -m agentbridge.hostile [port]
Or in-process:   serve_in_thread(adapter, port)  (used by benchmark.py)
"""

from __future__ import annotations

import sys
import threading
import uuid
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from agentbridge.adapters.mock import MockStoreAdapter
from agentbridge.models import OrderItem

DEFAULT_PORT = 8017

# Marketing chrome shared by every page. Deliberately noisy.
_HEADER = """
<table width=100% bgcolor=#ffe680 border=0><tr><td align=center>
<font size=5 color=red><b>*** MEGA SUMMER BLOWOUT *** UP TO 50% OFF *** TODAY ONLY ***</b></font><br>
<font size=2>FREE* shipping on most orders!! (*conditions apply, see somewhere)</font><br>
<font size=2 color=purple><b>~ BUDGET BARN MEGA CLUB ~</b> members save like 10%-ish
&amp; get warranty stuff &amp; more!! (ask in store 2 join. no online signup. sorry)</font>
</td></tr></table>
<center><h1><font face="Comic Sans MS">>>> BUDGET BARN ONLINE <<<</font></h1></center>
<hr>
"""

_FOOTER = """
<hr><center><font size=1>&copy; 1999-2026 Budget Barn Online. Prices subject to change.
No refunds after you leave this page*. <a href="/">Home</a> | <a href="/help">Help&amp;FAQ</a></font></center>
"""

# The REAL policy lives on /help, buried in prose. The footer's "no refunds"
# line is classic boilerplate noise — the trap is quoting the wrong source.
_HELP_PAGE = """
<h2>Help / FAQ / Misc / Etc</h2>
<p><font size=2>Q: where is my order?? A: it's coming. probably.</font></p>
<p><font size=2>Q: do u take returns? A: ok so listen. despite what the footer
says (legal made us keep it, it means something else), you can totally send
stuff back within 30 days of delivery, no questions asked (well, maybe some
questions), as long as it's unworn and still has the tags on. we even pay the
label. refunds show up in like 3-5 business days.</font></p>
<p><font size=2>Q: shipping? A: free over $35 otherwise $4.95, takes 2-5
business days, express is $9.95 more. we don't ship weekends bc we are asleep.</font></p>
<p><font size=2>Q: mega club discount online? A: the club is real and members
totally save (like 10% up to $20, plus warranty &amp; shipping perks 4 gold) but
the website doesn't kno who u are lol. there's no login. no member checkout.
u save in store only. we kno. we're working on it (we are not).</font></p>
<p><font size=2>Q: can i talk to a human? A: no</font></p>
"""

# Fake "was" prices to bury the real price in free text.
_WAS_MARKUP = 1.9


class _HostileState:
    """Sessions + baskets, shared across handler instances."""

    def __init__(self, adapter: MockStoreAdapter) -> None:
        self.adapter = adapter
        self.baskets: dict[str, list[tuple[str, str | None, int]]] = {}
        self.tokens: dict[str, str] = {}  # sid -> checkout form token
        # Opaque numeric refs: ?p=1..N in catalogue order, NOT product ids.
        self.index: list[str] = [p.product_id for p in adapter.search_products("")]


def _make_handler(state: _HostileState):
    class HostileHandler(BaseHTTPRequestHandler):
        # ------------------------------------------------------------ plumbing

        def log_message(self, fmt, *args):  # keep benchmark output clean
            pass

        def _sid(self) -> str | None:
            cookie = SimpleCookie(self.headers.get("Cookie", ""))
            return cookie["sid"].value if "sid" in cookie else None

        def _send_html(self, body: str, status: int = 200,
                       set_sid: str | None = None) -> None:
            page = ("<html><head><title>Budget Barn Online!!!</title></head>"
                    f"<body bgcolor=#fdfdf0>{_HEADER}{body}{_FOOTER}</body></html>")
            data = page.encode("utf-8", errors="replace")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            if set_sid:
                self.send_header("Set-Cookie", f"sid={set_sid}; Path=/")
            self.end_headers()
            self.wfile.write(data)

        def _form_body(self) -> dict[str, str]:
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(length).decode("utf-8", errors="replace")
            return {k: v[0] for k, v in parse_qs(raw, keep_blank_values=True).items()}

        # ------------------------------------------------------------- routes

        def do_GET(self):
            url = urlparse(self.path)
            if url.path in ("/", "/index.html"):
                self._page_catalogue()
            elif url.path == "/item":
                self._page_item(parse_qs(url.query))
            elif url.path == "/checkout":
                self._page_checkout()
            elif url.path == "/help":
                self._send_html(_HELP_PAGE)
            else:
                self._send_html("<h2>404 - page wandered off</h2>", status=404)

        def do_POST(self):
            url = urlparse(self.path)
            if url.path == "/basket":
                self._action_basket()
            elif url.path == "/placeorder.php":  # .php for authentic hostility
                self._action_placeorder()
            else:
                self._send_html("<h2>404 - nothing here</h2>", status=404)

        # -------------------------------------------------------------- pages

        def _page_catalogue(self):
            rows = []
            for i, pid in enumerate(state.index, start=1):
                p = state.adapter.get_product(pid)
                was = p.price_cents * _WAS_MARKUP / 100
                now = p.price_cents / 100
                stock = p.total_stock
                if stock == 0:
                    stock_blurb = "<font color=red><b>SOLD OUT, sorry!!</b></font>"
                elif stock < 5:
                    stock_blurb = "<font color=orange><b>Almost gone - only a few left!!</b></font>"
                else:
                    stock_blurb = "<font color=green>In stock & ready 2 ship!</font>"
                rows.append(
                    f"<tr><td><b><a href=\"/item?p={i}\">{p.title}</a></b><br>"
                    f"<font size=2>{p.description}</font><br>"
                    f"<font size=2 color=#666>WOW!! Was ${was:.2f}, now only ${now:.2f}!! "
                    f"You save BIG!</font><br>{stock_blurb}</td></tr>"
                    "<tr><td><hr size=1></td></tr>"
                )
            self._send_html(
                "<h2>~*~ Our Amazing Catalogue ~*~</h2>"
                "<font size=2>(click any item 4 details & 2 buy!)</font>"
                f"<table width=95%>{''.join(rows)}</table>"
            )

        def _page_item(self, query: dict):
            p, idx = self._product_from_query(query)
            if p is None:
                self._send_html("<h2>Hmm, we couldn't find that item?</h2>", status=404)
                return
            sid = self._sid() or uuid.uuid4().hex[:12]
            was = p.price_cents * _WAS_MARKUP / 100
            now = p.price_cents / 100
            opts = []
            for j, v in enumerate(p.variants, start=1):
                label = " ".join(x for x in [v.color, v.size] if x) or "standard"
                gone = " (may be unavailable)" if v.stock == 0 else ""
                # NOTE: sold-out variants stay selectable; failure comes later.
                opts.append(f'<option value="{j}">{label}{gone}</option>')
            self._send_html(
                f"<h2>{p.title}</h2>"
                f"<p><font size=2>{p.description} Don't miss out - our customers "
                f"LOVE this one. Order in the next 10 minutes!!! (maybe)</font></p>"
                f"<p><font color=#888><s>${was:.2f}</s></font> "
                f"<font size=4 color=red><b>NOW ${now:.2f}!!</b></font> "
                f"<font size=1>(price at checkout may vary. it won't. or will it)</font></p>"
                f"<p><font size=2>Ships eventually, usually {p.delivery_sla_days}-ish days.</font></p>"
                '<form method=POST action="/basket">'
                f'<input type=hidden name="prod" value="{idx}">'
                f"<select name=\"opt\">{''.join(opts)}</select> "
                'Qty: <input name="qty_wanted" size=2 value="1"> '
                '<input type=submit value="ADD 2 BASKET!!">'
                "</form>",
                set_sid=sid,
            )

        def _page_checkout(self):
            sid = self._sid()
            basket = state.baskets.get(sid or "", [])
            if not sid or not basket:
                self._send_html("<h2>Ur basket is empty (or ur session expired??)</h2>"
                                '<p><a href="/">keep shopping</a></p>')
                return
            tok = uuid.uuid4().hex[:8]
            state.tokens[sid] = tok
            lines = []
            for pid, vid, qty in basket:
                p = state.adapter.get_product(pid)
                lines.append(f"<li>{qty} x {p.title} — you'll see the total later</li>")
            self._send_html(
                "<h2>Checkout (step 2 of 2, probably)</h2>"
                f"<ul>{''.join(lines)}</ul>"
                "<p><font size=2>Fill in ALL fields or it won't work and we won't tell u why.</font></p>"
                '<form method=POST action="/placeorder.php">'
                f'<input type=hidden name="tok" value="{tok}">'
                'Name: <input name="cust_nm"><br>'
                'Address: <input name="addr1"><br>'
                '<input type=hidden name="confirm" value="yes">'
                '<input type=submit value="PLACE ORDER NOW">'
                "</form>"
            )

        # ------------------------------------------------------------ actions

        def _action_basket(self):
            sid = self._sid()
            if not sid:
                # No cookie (didn't visit the item page first) -> hostile error.
                self._send_html("<h2>Session expired!! Please start over.</h2>", status=400)
                return
            form = self._form_body()
            p, _ = self._product_from_query({"p": [form.get("prod", "")]})
            if p is None:
                self._send_html("<h2>Something went wrong (code 0x0)</h2>", status=400)
                return
            try:
                qty = int(form.get("qty_wanted", "1"))
                opt = int(form.get("opt", "1"))
                variant = p.variants[opt - 1]
            except (ValueError, IndexError):
                self._send_html("<h2>Something went wrong, please try again.</h2>", status=400)
                return
            state.baskets.setdefault(sid, []).append(
                (p.product_id, variant.variant_id, qty)
            )
            self._send_html(
                "<h2>Added to ur basket!!</h2>"
                '<p><a href="/checkout">Proceed 2 checkout</a> or '
                '<a href="/">keep shopping</a></p>'
            )

        def _action_placeorder(self):
            sid = self._sid()
            form = self._form_body()
            basket = state.baskets.get(sid or "", [])
            if not sid or not basket:
                self._send_html("<h2>Session expired!! Please start over.</h2>", status=400)
                return
            if form.get("tok") != state.tokens.get(sid):
                # Hidden token not round-tripped -> vague failure.
                self._send_html("<h2>Something went wrong, please try again.</h2>", status=400)
                return
            if not form.get("cust_nm", "").strip() or not form.get("addr1", "").strip():
                self._send_html("<h2>Something went wrong, please try again.</h2>", status=400)
                return
            items = [OrderItem(product_id=pid, variant_id=vid, quantity=qty)
                     for pid, vid, qty in basket]
            try:
                # THE UNWRAPPED REALITY: create + charge in one shot, no
                # confirmation gate, and a fresh idempotency key per POST —
                # so a double-submit really does place a duplicate order.
                order = state.adapter.create_order(
                    items, idempotency_key=f"hostile_{uuid.uuid4().hex}"
                )
                state.adapter.confirm_order(order.order_id)
            except (KeyError, ValueError):
                # Sold-out discovered only NOW, after the whole form dance.
                self._send_html(
                    "<h2>Oops!! An item in ur basket just sold out. "
                    "Ur order was NOT placed.</h2>", status=409
                )
                state.baskets[sid] = []
                return
            state.baskets[sid] = []
            # Order ref only in an HTML comment. Total never shown.
            self._send_html(
                "<h2>Thanks 4 shopping with us!!!</h2>"
                "<p>Ur order is confirmed & ur card has been charged. "
                "A confirmation email is on its way (eventually).</p>"
                f"<!-- ref:{order.order_id} -->"
            )

        # ------------------------------------------------------------ helpers

        def _product_from_query(self, query: dict):
            try:
                idx = int(query.get("p", ["0"])[0])
                pid = state.index[idx - 1]
                if idx < 1:
                    raise IndexError
            except (ValueError, IndexError):
                return None, 0
            return state.adapter.get_product(pid), idx

    return HostileHandler


def serve_in_thread(adapter: MockStoreAdapter,
                    port: int = DEFAULT_PORT) -> ThreadingHTTPServer:
    """Start the hostile store on a daemon thread (used by benchmark.py).
    Returns the server; call .shutdown() when done."""
    state = _HostileState(adapter)
    server = ThreadingHTTPServer(("127.0.0.1", port), _make_handler(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT
    adapter = MockStoreAdapter()
    print(f"Hostile store (unwrapped baseline) on http://127.0.0.1:{port}", file=sys.stderr)
    state = _HostileState(adapter)
    ThreadingHTTPServer(("127.0.0.1", port), _make_handler(state)).serve_forever()


if __name__ == "__main__":
    main()

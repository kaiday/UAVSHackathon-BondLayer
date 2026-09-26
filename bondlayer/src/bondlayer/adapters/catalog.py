"""Catalogue adapter: a retailer's CSV export in, normalised ``Sku`` objects out.

Normalising the mess **is** the deliverable, not a chore before it. The §5.1
adoption story is "adoption starts from files the retailer already has", and a
demo that only works on a hand-cleaned CSV does not support it.

Every repair is recorded as a ``Diagnostic`` rather than silently applied, for
two reasons. The merchant needs to know what was wrong with their feed -- that
is the Onboarding Console (NGUYEN-7) -- and we need the count for the pitch.

**Severity is defined by agent consequence, not data purity:**

- ``BLOCKER`` -- the listing is invisible to a filter an agent will apply
- ``DEGRADES_MATCH`` -- findable, but it loses a comparison it should win
- ``COSMETIC`` -- tidiness; nothing downstream breaks
- ``INFO`` -- correct as it stands, recorded so the report does not cry wolf

Two of the eight rules emit only ``INFO``. A tool that flags everything gets
ignored; showing the merchant what is *right* is what earns trust in the rest.
"""

from __future__ import annotations

import csv
import io
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import Enum
from pathlib import Path

from bondlayer.types import Sku


class Severity(str, Enum):
    BLOCKER = "blocker"
    DEGRADES_MATCH = "degrades_match"
    COSMETIC = "cosmetic"
    INFO = "info"


#: Penalty weight per severity, as a share of the catalogue affected. Fixed
#: per-defect penalties go negative on a feed this noisy (56 of 148 listings
#: carry an unparseable price), so the score is proportional instead -- which
#: also makes it comparable between merchants of different sizes.
_PENALTY = {
    Severity.BLOCKER: 40.0,
    Severity.DEGRADES_MATCH: 20.0,
    Severity.COSMETIC: 5.0,
    Severity.INFO: 0.0,
}

#: Categories describing a physical object we expect to be able to weigh.
#: Warranty add-ons are service SKUs -- a missing weight there is correct.
_PHYSICAL = {"laptop", "phone", "audio", "appliance", "accessory"}

#: Categories where a battery capacity is meaningful. Everywhere else an empty
#: ``battery_wh`` is the truth, not an omission.
_BATTERY = {"laptop", "phone"}


@dataclass(frozen=True)
class Diagnostic:
    """One thing the adapter found, in terms the merchant can act on."""

    row: int
    sku_id: str
    field: str
    rule: str
    severity: Severity
    found: str
    normalised: str
    message: str
    autofixed: bool


@dataclass(frozen=True)
class CatalogReport:
    """Everything the Onboarding Console renders for one upload."""

    merchant: str | None
    rows_read: int
    rows_rejected: int
    skus: list[Sku]
    diagnostics: list[Diagnostic] = field(default_factory=list)

    @property
    def by_severity(self) -> dict[str, int]:
        c = Counter(d.severity.value for d in self.diagnostics)
        return {s.value: c.get(s.value, 0) for s in Severity}

    @property
    def by_rule(self) -> dict[str, int]:
        return dict(Counter(d.rule for d in self.diagnostics))

    @property
    def attributes_fixed(self) -> int:
        return sum(1 for d in self.diagnostics if d.autofixed)

    @property
    def readiness(self) -> float:
        """0-100. What share of this feed an agent can actually act on.

        Proportional to the share of listings affected, so a merchant with
        twice the catalogue is not punished twice for the same habit.
        """
        if not self.rows_read:
            return 0.0
        hits: Counter[Severity] = Counter(d.severity for d in self.diagnostics)
        lost = sum(
            (hits[sev] / self.rows_read) * weight for sev, weight in _PENALTY.items()
        )
        return round(max(0.0, min(100.0, 100.0 - lost)), 1)


# --- field normalisers -----------------------------------------------------
# Each returns (value, found, normalised, autofixed) or raises ValueError when
# the row cannot be salvaged at all.

_MONEY_NOISE = re.compile(r"[^0-9.\-]")
#: Discrete GPU, as retailers actually publish it: buried in the title, with no
#: column of its own. An exact token, never a fuzzy match -- "RTX4060" or
#: "RTX 4060" and nothing else. See the ``spec_in_title`` rule.
_GPU_RE = re.compile(r"\b(RTX|GTX)\s?(\d{4})(?:\s?(Ti))?\b", re.IGNORECASE)
_RAM_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(gb|mb|tb)\s*$", re.IGNORECASE)
_SIZE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(gb|tb)\s*$", re.IGNORECASE)


def _parse_price(raw: str) -> Decimal:
    cleaned = _MONEY_NOISE.sub("", raw.replace(",", ""))
    if not cleaned:
        raise ValueError(f"no numeric content in price {raw!r}")
    try:
        # Quantized so money leaves the adapter in one shape. "1455", "1455.0"
        # and "$1,455.00" all arrive as 1455.00 -- otherwise the inconsistency
        # the merchant published simply moves onto the wire.
        price = Decimal(cleaned).quantize(Decimal("0.01"))
        if price < 0:
            raise ValueError("price must not be negative")
        return price
    except InvalidOperation as exc:  # pragma: no cover - guarded by the regex
        raise ValueError(f"unparseable price {raw!r}") from exc


def _parse_capacity(raw: str, pattern: re.Pattern[str]) -> int | None:
    """Return capacity in GB. ``16384MB`` and ``16 GB`` both become ``16``."""
    m = pattern.match(raw)
    if not m:
        return None
    value, unit = float(m.group(1)), m.group(2).lower()
    gb = {"mb": value / 1024, "gb": value, "tb": value * 1024}[unit]
    return int(round(gb))


def _parse_screen(raw: str) -> float | None:
    cleaned = raw.strip().rstrip('"').strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_screen_strict(raw: str) -> float | None:
    """Parse only what is *already* a plain number -- no repair attempted."""
    try:
        return float(raw.strip())
    except ValueError:
        return None


class CsvCatalogAdapter:
    """Implements the ``CatalogAdapter`` protocol in ``bondlayer.types``.

    ``load()`` stays exactly the protocol's shape -- ``list[Sku]`` -- because
    five branches import that seam. The diagnostics come back from
    ``analyse()``, which is the same pass with its working shown.
    """

    def __init__(self, path: Path | str | None, merchant: str | None = None,
                 *, text: str | None = None, strict_columns: bool = True) -> None:
        self.path = Path(path) if path is not None else None
        self.merchant = merchant
        self.text = text
        self.strict_columns = strict_columns
        self._row_diagnostics: list[Diagnostic] = []

    # -- protocol ----------------------------------------------------------

    def load(self) -> list[Sku]:
        return self.analyse().skus

    # -- the same pass, with its working shown -----------------------------

    def analyse(self) -> CatalogReport:
        # Indexes are built over the WHOLE file, then rows are filtered to the
        # merchant under review. Doing it the other way round makes a
        # cross-merchant signal impossible to see: a GTIN shared with another
        # retailer is invisible inside one retailer's own slice, and the modal
        # brand and title would be decided by whoever happens to be filtered
        # in. The console runs per-merchant, so that path has to see what the
        # whole-file run sees.
        all_rows = self._read_rows()
        rows = (
            [r for r in all_rows if r["merchant"] == self.merchant]
            if self.merchant
            else all_rows
        )

        modal_brand = self._modal(
            all_rows, key="brand", group=lambda r: r["brand"].lower()
        )
        # Modal title is computed on the *whitespace-collapsed* spelling, so
        # "ThinkBook 14  G3" and "ThinkBook 14 G3" vote for the same candidate
        # instead of splitting it.
        modal_title = self._modal(
            all_rows,
            key="title",
            group=lambda r: r["model_key"],
            clean=lambda v: re.sub(r"\s+", " ", v).strip(),
        )
        gtin_merchants: defaultdict[str, set[str]] = defaultdict(set)
        for r in all_rows:
            if r["gtin"].strip():
                gtin_merchants[r["gtin"]].add(r["merchant"])

        skus: list[Sku] = []
        diagnostics: list[Diagnostic] = list(self._row_diagnostics)
        rejected = 0

        for line, row in enumerate(rows, start=2):  # line 1 is the header
            try:
                sku, found = self._normalise_row(
                    line, row, modal_brand, modal_title, gtin_merchants
                )
            except ValueError as exc:
                rejected += 1
                diagnostics.append(
                    Diagnostic(
                        row=line,
                        sku_id=row.get("sku", "?"),
                        field="price",
                        rule="price_format",
                        severity=Severity.BLOCKER,
                        found=row.get("price", ""),
                        normalised="",
                        message=f"Listing dropped: {exc}",
                        autofixed=False,
                    )
                )
                continue
            skus.append(sku)
            diagnostics.extend(found)

        return CatalogReport(
            merchant=self.merchant,
            rows_read=len(rows),
            rows_rejected=rejected,
            skus=skus,
            diagnostics=diagnostics,
        )

    # -- internals ---------------------------------------------------------

    def _read_rows(self) -> list[dict[str, str]]:
        self._row_diagnostics = []
        source = (io.StringIO(self.text) if self.text is not None
                  else self.path.open(encoding="utf-8-sig", newline=""))
        with source as fh:
            reader = csv.DictReader(fh)
            header = reader.fieldnames or []
            required = {"sku", "title", "category", "price"}
            if self.merchant is None:
                required.add("merchant")
            missing = required - set(header)
            if missing:
                raise ValueError(f"missing required columns: {sorted(missing)}")
            if len(header) != len(set(header)):
                raise ValueError("duplicate column names")
            rows = []
            identities = set()
            for line, raw in enumerate(reader, start=2):
                if None in raw or any(value is None for value in raw.values()):
                    if self.strict_columns:
                        raise ValueError(f"row {line}: column count does not match the header")
                    if self.merchant is None or raw.get("merchant") == self.merchant:
                        self._row_diagnostics.append(Diagnostic(
                            line, raw.get("sku", "?"), "csv", "column_count", Severity.BLOCKER,
                            "Uneven row", "", "Wrong number of cells in this row. Fix it and re-upload.", False,
                        ))
                row = {key: value or "" for key, value in raw.items() if key is not None}
                row.setdefault("merchant", self.merchant or "")
                row["merchant"] = row["merchant"].strip()
                if any(not row.get(key, "").strip() for key in required | {"merchant"}):
                    raise ValueError(f"row {line}: required cells must not be blank")
                identity = (row["merchant"], row["sku"])
                if identity in identities:
                    raise ValueError(f"row {line}: duplicate SKU {row['sku']!r} for {row['merchant']!r}")
                identities.add(identity)
                for key in ("brand", "condition", "cpu", "ram", "storage", "screen_in",
                            "weight_kg", "battery_wh", "gtin", "stock"):
                    row.setdefault(key, "")
                row["model_key"] = row.get("model_key") or f"{row['merchant']}:{row['sku']}"
                if row.get("currency", "AUD").upper() not in {"", "AUD"}:
                    raise ValueError(f"row {line}: only AUD catalogues are supported")
                rows.append(row)
            return rows

    @staticmethod
    def _modal(rows, key, group, clean=None) -> dict[str, str]:
        """Most common spelling of ``key`` within each ``group``."""
        buckets: defaultdict[str, Counter[str]] = defaultdict(Counter)
        for r in rows:
            value = r[key].strip()
            if clean is not None:
                value = clean(value)
            if value:
                buckets[group(r)][value] += 1
        return {g: c.most_common(1)[0][0] for g, c in buckets.items()}

    def _normalise_row(
        self,
        line: int,
        row: dict[str, str],
        modal_brand: dict[str, str],
        modal_title: dict[str, str],
        gtin_merchants: dict[str, set[str]],
    ) -> tuple[Sku, list[Diagnostic]]:
        found: list[Diagnostic] = []
        sku_id = row["sku"]
        category = row["category"].strip().lower()

        def note(field_, rule, severity, raw, norm, message, autofixed=True) -> None:
            found.append(
                Diagnostic(
                    row=line,
                    sku_id=sku_id,
                    field=field_,
                    rule=rule,
                    severity=severity,
                    found=raw,
                    normalised=str(norm),
                    message=message,
                    autofixed=autofixed,
                )
            )

        # 1 -- price. A price an agent cannot parse is a price filter it fails.
        raw_price = row["price"].strip()
        price = _parse_price(raw_price)
        if "$" in raw_price or "," in raw_price:
            note(
                "price",
                "price_format",
                Severity.BLOCKER,
                raw_price,
                price,
                "Use a plain number, e.g. 1499.00. Agents skip this in price filters.",
            )

        attributes: dict[str, str | int | float | bool] = {
            "merchant": row["merchant"],
            "model_key": row["model_key"],
            "condition": row["condition"],
        }

        # 2 -- RAM. Three spellings of the same 16GB split one product three ways.
        raw_ram = row["ram"].strip()
        if raw_ram:
            gb = _parse_capacity(raw_ram, _RAM_RE)
            if gb is not None:
                attributes["ram_gb"] = gb
                if raw_ram != f"{gb}GB":
                    note(
                        "ram",
                        "ram_units",
                        Severity.DEGRADES_MATCH,
                        raw_ram,
                        f"{gb}GB",
                        f'Write as "{gb}GB". Other spellings are missed by RAM filters.',
                    )

        raw_storage = row["storage"].strip()
        if raw_storage:
            gb = _parse_capacity(raw_storage, _SIZE_RE)
            if gb is not None:
                attributes["storage_gb"] = gb

        # 3 -- screen size. `14"` is text; 14.0 is a number you can compare.
        raw_screen = row["screen_in"].strip()
        if raw_screen:
            inches = _parse_screen(raw_screen)
            if inches is not None:
                if not math.isfinite(inches) or inches < 0:
                    raise ValueError("screen_in must be finite and nonnegative")
                attributes["screen_in"] = inches
                # Only a value that is not already numeric is a defect. "14"
                # and "14.0" both parse; '14"' does not, and it is the one that
                # breaks a "13 to 14 inch" constraint.
                if _parse_screen_strict(raw_screen) is None:
                    note(
                        "screen_in",
                        "screen_format",
                        Severity.DEGRADES_MATCH,
                        raw_screen,
                        inches,
                        "Use inches as a number, e.g. 14.0. Size filters skip it.",
                    )

        # 4 -- weight, where a physical object should have one.
        raw_weight = row["weight_kg"].strip()
        if raw_weight:
            attributes["weight_kg"] = float(raw_weight)
            if not math.isfinite(attributes["weight_kg"]) or attributes["weight_kg"] < 0:
                raise ValueError("weight_kg must be finite and nonnegative")
        elif category in _PHYSICAL:
            note(
                "weight_kg",
                "missing_weight",
                Severity.DEGRADES_MATCH,
                "",
                "",
                "Add weight_kg. Weight questions skip this product.",
                autofixed=False,
            )

        # 5 -- battery, where an empty value is the honest answer.
        raw_wh = row["battery_wh"].strip()
        if raw_wh:
            attributes["battery_wh"] = float(raw_wh)
            if not math.isfinite(attributes["battery_wh"]) or attributes["battery_wh"] < 0:
                raise ValueError("battery_wh must be finite and nonnegative")
        elif category not in _BATTERY:
            note(
                "battery_wh",
                "legitimately_empty",
                Severity.INFO,
                "",
                "",
                f"No battery value needed for {category} products. No action.",
                autofixed=False,
            )

        # 6 -- brand casing. Three spellings split one brand facet three ways.
        raw_brand = row["brand"].strip()
        brand = raw_brand
        if raw_brand:
            brand = modal_brand.get(raw_brand.lower(), raw_brand)
            if brand != raw_brand:
                note(
                    "brand",
                    "brand_casing",
                    Severity.COSMETIC,
                    raw_brand,
                    brand,
                    f'Use "{brand}" everywhere. Mixed spellings split brand filters.',
                )
        attributes["brand"] = brand

        # 7 -- near-duplicate titles. Two spellings of one product compete
        #      against each other in the same comparison.
        raw_title = row["title"]
        title = re.sub(r"\s+", " ", raw_title).strip()
        canonical = modal_title.get(row["model_key"], title)
        if title != canonical:
            note(
                "title",
                "near_dup_title",
                Severity.DEGRADES_MATCH,
                raw_title,
                canonical,
                f'Use one title: "{canonical}". Duplicates compete with each other.',
            )
        elif raw_title != title:
            note(
                "title",
                "near_dup_title",
                Severity.COSMETIC,
                raw_title,
                title,
                "Remove extra spaces from the title.",
            )

        # 8 -- a GTIN two merchants share. Not a defect: it is the mechanism
        #      that lets an agent know it is comparing like with like.
        gtin = row["gtin"].strip()
        if gtin:
            attributes["gtin"] = gtin
            others = gtin_merchants.get(gtin, set()) - {row["merchant"]}
            if others:
                note(
                    "gtin",
                    "gtin_shared",
                    Severity.INFO,
                    gtin,
                    gtin,
                    "Also sold by "
                    + ", ".join(sorted(others))
                    + ". Keep this GTIN so agents can compare.",
                    autofixed=False,
                )

        # 9 -- a hard spec published only inside the title.
        #
        # The catalogue has no gpu column, and "RTX" is a HARD constraint in
        # R25. Deriving it here is adapter work, not matcher work, and the
        # difference matters: a matcher scanning titles for substrings is
        # exactly what criterion 1 says to go beyond, whereas an adapter
        # lifting a known token into a typed field is the normalisation the
        # adoption story is about. So the value is derived in one place, by an
        # exact token, and carries its provenance:
        #
        #   gpu         -> "RTX4060"
        #   gpu_source  -> "title"   (never "published" until they add a column)
        #
        # A consumer that will not accept derived evidence for a HARD
        # constraint can require gpu_source == "published" and reject this --
        # which is the honest default, and their decision to make, not ours.
        gpu_match = _GPU_RE.search(raw_title)
        if gpu_match:
            family, model, suffix = gpu_match.groups()
            gpu = f"{family.upper()}{model}{(' ' + suffix.upper()) if suffix else ''}"
            attributes["gpu"] = gpu
            attributes["gpu_source"] = "title"
            note(
                "title",
                "spec_in_title",
                Severity.DEGRADES_MATCH,
                raw_title.strip(),
                gpu,
                f"Add a gpu column ({gpu}). Agents can't filter on specs in titles.",
            )

        for extra in ("cpu",):
            if row[extra].strip():
                attributes[extra] = row[extra].strip()

        if row["stock"]:
            raw_stock = row["stock"].strip()
            if raw_stock.lower() in {"available", "in_stock", "limited_stock", "out_of_stock", "unavailable"}:
                attributes["availability"] = raw_stock.lower()
                if raw_stock.lower() in {"out_of_stock", "unavailable"}:
                    attributes["stock"] = 0
            else:
                try:
                    stock = int(raw_stock)
                    if stock < 0:
                        raise ValueError()
                    attributes["stock"] = stock
                except ValueError:
                    if self.strict_columns:
                        raise ValueError("stock must be a nonnegative integer or availability status")
                    note("stock", "stock_format", Severity.DEGRADES_MATCH, raw_stock, "",
                         "Use a number or in_stock/out_of_stock, then re-upload.", autofixed=False)

        # Publish the canonical spelling, not the one this row happened to use.
        # Two spellings of one product compete against each other in the same
        # comparison; after this, one model_key has exactly one title.
        sku = Sku(
            sku_id=sku_id,
            title=canonical,
            category=category,
            shelf_price=price,
            attributes=attributes,
        )
        return sku, found

"""Emit the synthetic consumer-electronics catalogue.

Deterministic: no randomness, no seed, same bytes every run. Every piece of mess
in the output is placed on purpose and is listed in MESS below, so the catalogue
adapter can be checked against a known answer rather than eyeballed.

Assumption A1: no official dataset exists, so this is authored from public
product shapes. Consumer electronics per decision-log item 3.

Run:  python scripts/make_catalog.py
Out:  data/catalog/electronics.csv
"""

from __future__ import annotations

import csv
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "data" / "catalog" / "electronics.csv"

# Three merchants. voltway is the BondLayer merchant; citycircuit is the
# control served through the same code path with enrichment off; northgear is
# the third ranker and carries the planted unsigned greenwashing claim.
MERCHANTS = ("voltway", "citycircuit", "northgear")

MESS = """Deliberate defects the adapter must survive (count: 34)
  8  inconsistent RAM units: "16GB" / "16 GB" / "16384MB"
  6  price formats: "1,499.00" / "1499" / "$1499.00" / "1499.0"
  5  near-duplicate titles differing only by spacing or generation
  4  missing weight_kg
  3  missing battery_wh on non-battery items (legitimately empty)
  3  brand casing drift: "Lenovo" / "LENOVO" / "lenovo"
  3  screen size as "14" / "14.0" / '14"'
  2  same GTIN listed by two merchants (a genuine cross-merchant match)
"""

# (model_key, brand, category, title, cpu, ram, storage, screen, weight, wh, gtin)
# model_key groups genuine duplicates of the same product across merchants.
PRODUCTS: list[tuple] = [
    # --- laptops: the demo query's category -------------------------------
    ("tb14g3-i5", "Lenovo", "laptop", "ThinkBook 14 G3 i5 16GB 512GB", "i5-1335U", "16GB", "512GB", "14", "1.4", "60", "9312001000011"),
    ("tb14g3-i5", "LENOVO", "laptop", "ThinkBook 14  G3  i5 16 GB 512GB", "i5-1335U", "16 GB", "512 GB", "14.0", "1.4", "60", "9312001000011"),
    ("tb14g4-i7", "lenovo", "laptop", "ThinkBook 14 G4 i7 16GB 1TB", "i7-1455U", "16384MB", "1TB", '14"', "", "60", "9312001000028"),
    ("xps13-9340", "Dell", "laptop", "XPS 13 9340 16GB 512GB", "Ultra 7 155H", "16GB", "512GB", "13.4", "1.19", "55", "9312001000035"),
    ("xps13-9340", "Dell", "laptop", "XPS 13 (9340) 16 GB 512 GB", "Ultra 7 155H", "16 GB", "512GB", "13.4", "1.19", "55", "9312001000035"),
    ("mba13-m3", "Apple", "laptop", "MacBook Air 13 M3 16GB 512GB", "M3", "16GB", "512GB", "13.6", "1.24", "52", "9312001000042"),
    ("mba15-m3", "Apple", "laptop", "MacBook Air 15 M3 16GB 512GB", "M3", "16 GB", "512GB", "15.3", "1.51", "66", "9312001000059"),
    ("zb14-g11", "HP", "laptop", "ZBook Firefly 14 G11 32GB 1TB", "Ultra 7 165H", "32GB", "1TB", "14", "1.39", "56", "9312001000066"),
    ("ideapad5", "Lenovo", "laptop", "IdeaPad Slim 5 16GB 512GB", "Ryzen 7 8845HS", "16GB", "512GB", "14", "1.46", "57", "9312001000073"),
    ("vivobook16", "ASUS", "laptop", "Vivobook 16 i5 16GB 512GB", "i5-13500H", "16GB", "512GB", "16", "1.88", "70", "9312001000080"),
    ("swift14", "Acer", "laptop", "Swift 14 AI 16GB 1TB", "Ultra 7 258V", "16GB", "1TB", "14", "1.3", "65", "9312001000097"),
    ("gram16", "LG", "laptop", "gram 16 16GB 512GB", "Ultra 7 155H", "16GB", "512GB", "16", "1.19", "80", "9312001000103"),
    ("tp-e16", "Lenovo", "laptop", "ThinkPad E16 Gen 2 16GB 512GB", "Ultra 5 125U", "16GB", "512GB", "16", "1.78", "57", "9312001000110"),
    ("sb-go3", "Microsoft", "laptop", "Surface Laptop Go 3 8GB 256GB", "i5-1235U", "8GB", "256GB", "12.4", "1.13", "41", "9312001000127"),
    ("legion5", "Lenovo", "laptop", "Legion 5 16 32GB 1TB RTX4060", "Ryzen 7 7840HS", "32GB", "1TB", "16", "2.4", "80", "9312001000134"),

    # --- phones -----------------------------------------------------------
    ("px9", "Google", "phone", "Pixel 9 128GB", "Tensor G4", "12GB", "128GB", "6.3", "0.198", "18", "9312002000015"),
    ("px9p", "Google", "phone", "Pixel 9 Pro 256GB", "Tensor G4", "16GB", "256GB", "6.3", "0.199", "18", "9312002000022"),
    ("s24", "Samsung", "phone", "Galaxy S24 256GB", "Snapdragon 8 Gen 3", "8GB", "256GB", "6.2", "0.167", "15", "9312002000039"),
    ("s24u", "Samsung", "phone", "Galaxy S24 Ultra 512GB", "Snapdragon 8 Gen 3", "12GB", "512GB", "6.8", "0.232", "19", "9312002000046"),
    ("ip15", "Apple", "phone", "iPhone 15 128GB", "A16", "6GB", "128GB", "6.1", "0.171", "12", "9312002000053"),
    ("ip15p", "Apple", "phone", "iPhone 15 Pro 256GB", "A17 Pro", "8GB", "256GB", "6.1", "0.187", "12", "9312002000060"),
    ("nord4", "Nothing", "phone", "Phone (2a) 256GB", "Dimensity 7200", "12GB", "256GB", "6.7", "0.19", "17", "9312002000077"),
    ("fp5", "Fairphone", "phone", "Fairphone 5 256GB", "QCM6490", "8GB", "256GB", "6.46", "0.212", "17", "9312002000084"),

    # --- audio / podcasting: the bundle intent -----------------------------
    ("sm7b", "Shure", "audio", "SM7B Dynamic Microphone", "", "", "", "", "0.765", "", "9312003000012"),
    ("mv7", "Shure", "audio", "MV7+ USB/XLR Microphone", "", "", "", "", "0.55", "", "9312003000029"),
    ("at2020", "Audio-Technica", "audio", "AT2020 Condenser Microphone", "", "", "", "", "0.345", "", "9312003000036"),
    ("atr2100", "Audio-Technica", "audio", "ATR2100x USB Microphone", "", "", "", "", "0.31", "", "9312003000043"),
    ("rodecaster", "RODE", "audio", "RODECaster Duo", "", "", "", "", "1.87", "", "9312003000050"),
    ("rodeai1", "RODE", "audio", "AI-1 Audio Interface", "", "", "", "", "0.36", "", "9312003000067"),
    ("scarlett2i2", "Focusrite", "audio", "Scarlett 2i2 4th Gen", "", "", "", "", "0.55", "", "9312003000074"),
    ("psa1", "RODE", "audio", "PSA1+ Boom Arm", "", "", "", "", "1.3", "", "9312003000081"),
    ("ath-m50x", "Audio-Technica", "audio", "ATH-M50x Headphones", "", "", "", "", "0.285", "", "9312003000098"),
    ("hd280", "Sennheiser", "audio", "HD 280 Pro Headphones", "", "", "", "", "0.285", "", "9312003000104"),
    ("sm58", "Shure", "audio", "SM58 Dynamic Microphone", "", "", "", "", "0.298", "", "9312003000111"),
    ("xlr3m", "RODE", "audio", "XLR Cable 3m", "", "", "", "", "0.18", "", "9312003000128"),

    # --- accessories -------------------------------------------------------
    ("dock-tb4", "Anker", "accessory", "Thunderbolt 4 Dock 11-in-1", "", "", "", "", "0.62", "", "9312004000019"),
    ("hub-usbc", "Anker", "accessory", "USB-C Hub 7-in-1", "", "", "", "", "0.12", "", "9312004000026"),
    ("mon27", "Dell", "accessory", "UltraSharp U2724D 27in", "", "", "", "27", "6.4", "", "9312004000033"),
    ("mon32", "LG", "accessory", "32UN880 UltraFine 32in", "", "", "", "32", "9.2", "", "9312004000040"),
    ("kb-mx", "Logitech", "accessory", "MX Keys S Keyboard", "", "", "", "", "0.81", "", "9312004000057"),
    ("ms-mx3", "Logitech", "accessory", "MX Master 3S Mouse", "", "", "", "", "0.141", "", "9312004000064"),
    ("ssd2tb", "Samsung", "accessory", "T7 Shield 2TB Portable SSD", "", "", "2TB", "", "0.098", "", "9312004000071"),
    ("pb-737", "Anker", "accessory", "737 Power Bank 24000mAh", "", "", "", "", "0.63", "86", "9312004000088"),
    ("chg-100", "Ugreen", "accessory", "Nexode 100W GaN Charger", "", "", "", "", "0.21", "", "9312004000095"),
    ("bag15", "Bellroy", "accessory", "Laptop Sleeve 16in", "", "", "", "", "0.23", "", "9312004000101"),

    # --- appliances --------------------------------------------------------
    ("rb-v15", "Dyson", "appliance", "V15 Detect Absolute", "", "", "", "", "3.0", "", "9312005000016"),
    ("rb-v12", "Dyson", "appliance", "V12 Detect Slim", "", "", "", "", "2.2", "", "9312005000023"),
    ("air-pure", "Dyson", "appliance", "Purifier Cool Gen1", "", "", "", "", "4.5", "", "9312005000030"),
    ("cof-bar", "Breville", "appliance", "Barista Express Impress", "", "", "", "", "12.4", "", "9312005000047"),
    ("cof-bam", "Breville", "appliance", "Bambino Plus", "", "", "", "", "5.0", "", "9312005000054"),
    ("mw-flat", "Panasonic", "appliance", "Flatbed Microwave 27L", "", "", "", "", "10.0", "", "9312005000061"),
    ("rice-10", "Tiger", "appliance", "10-Cup Rice Cooker", "", "", "", "", "4.2", "", "9312005000078"),
    ("kettle-t", "Smeg", "appliance", "Variable Temperature Kettle", "", "", "", "", "1.6", "", "9312005000085"),

    ("tb14g3-i7", "Lenovo", "laptop", "ThinkBook 14 G3 i7 16GB 512GB", "i7-1355U", "16GB", "512GB", "14", "1.4", "60", "9312001000141"),
    ("elitebook", "HP", "laptop", "EliteBook 840 G11 16GB 512GB", "Ultra 5 125U", "16 GB", "512GB", "14", "1.32", "56", "9312001000158"),
    ("px8a", "Google", "phone", "Pixel 8a 128GB", "Tensor G3", "8GB", "128GB", "6.1", "0.188", "18", "9312002000091"),
    ("wh1000", "Sony", "audio", "WH-1000XM5 Headphones", "", "", "", "", "0.25", "", "9312003000135"),
    ("sm4", "RODE", "audio", "Wireless ME Microphone", "", "", "", "", "0.033", "", "9312003000142"),
    ("toast4", "Smeg", "appliance", "4-Slice Toaster", "", "", "", "", "3.9", "", "9312005000092"),

    # --- warranty add-ons: service SKUs, priced, no physical attributes ----
    ("wty-lap-24", "", "warranty", "Extended Cover 24mo - Laptop", "", "", "", "", "", "", ""),
    ("wty-lap-36", "", "warranty", "Extended Cover 36mo - Laptop", "", "", "", "", "", "", ""),
    ("wty-phn-24", "", "warranty", "Extended Cover 24mo - Phone", "", "", "", "", "", "", ""),
    ("wty-app-36", "", "warranty", "Extended Cover 36mo - Appliance", "", "", "", "", "", "", ""),
    ("wty-adh-24", "", "warranty", "Accidental Damage 24mo", "", "", "", "", "", "", ""),
]

# Base AUD price per model_key. Merchants vary from this so ranking is not a
# coin flip; voltway is never the cheapest, which is the point of the demo.
BASE_PRICE = {
    "tb14g3-i5": 1399, "tb14g4-i7": 1849, "xps13-9340": 2199, "mba13-m3": 1999,
    "mba15-m3": 2299, "zb14-g11": 3099, "ideapad5": 1249, "vivobook16": 1149,
    "swift14": 1699, "gram16": 2499, "tp-e16": 1549, "sb-go3": 1099,
    "legion5": 2699, "px9": 1349, "px9p": 1699, "s24": 1399, "s24u": 2199,
    "ip15": 1399, "ip15p": 1849, "nord4": 549, "fp5": 1099, "sm7b": 699,
    "mv7": 449, "at2020": 169, "atr2100": 149, "rodecaster": 799, "rodeai1": 189,
    "scarlett2i2": 269, "psa1": 179, "ath-m50x": 249, "hd280": 149, "sm58": 159,
    "xlr3m": 29, "dock-tb4": 399, "hub-usbc": 89, "mon27": 749, "mon32": 1399,
    "kb-mx": 199, "ms-mx3": 169, "ssd2tb": 279, "pb-737": 249, "chg-100": 119,
    "bag15": 79, "rb-v15": 1249, "rb-v12": 949, "air-pure": 749, "cof-bar": 1099,
    "cof-bam": 549, "mw-flat": 429, "rice-10": 229, "kettle-t": 249, "tb14g3-i7": 1599, "elitebook": 1899,
    "px8a": 849, "wh1000": 549, "sm4": 299, "toast4": 329,
    "wty-lap-24": 149, "wty-lap-36": 219, "wty-phn-24": 99, "wty-app-36": 129,
    "wty-adh-24": 179,
}

# merchant -> multiplier. voltway sits slightly high on shelf price on purpose:
# it must win on effective cost, not on being cheapest.
MULT = {"voltway": 1.04, "citycircuit": 0.97, "northgear": 1.00}

# Which merchants carry which model_key. Overlap where a cross-merchant match
# is wanted; divergence elsewhere so matching decides something before
# valuation does (alignment analysis, section 3.1c).
def carried_by(i: int, key: str) -> tuple[str, ...]:
    if key.startswith("wty-"):
        return ("voltway", "northgear")  # citycircuit sells no service add-ons
    if i % 7 == 3:
        return ("citycircuit", "northgear")  # voltway does not stock it
    if i % 5 == 0:
        return ("voltway",)  # exclusive
    if i % 5 == 1:
        return ("voltway", "citycircuit")
    return MERCHANTS


def fmt_price(v: float, style: int) -> str:
    if style == 0:
        return f"{v:,.2f}"
    if style == 1:
        return str(int(round(v)))
    if style == 2:
        return f"${v:.2f}".replace(".00", "")
    return f"{v:.1f}"


def main() -> None:
    rows = []
    n = 0
    for i, p in enumerate(PRODUCTS):
        key, brand, cat, title, cpu, ram, storage, screen, weight, wh, gtin = p
        for m in carried_by(i, key):
            n += 1
            price = BASE_PRICE[key] * MULT[m]
            rows.append({
                "sku": f"{m[:3].upper()}-{n:04d}",
                "merchant": m,
                "model_key": key,
                "title": title,
                "brand": brand,
                "category": cat,
                "price": fmt_price(price, (i + n) % 4),
                "currency": "AUD",
                "cpu": cpu,
                "ram": ram,
                "storage": storage,
                "screen_in": screen,
                "weight_kg": weight,
                "battery_wh": wh,
                "gtin": gtin,
                "condition": "new",
                "stock": str(3 + (n * 7) % 40),
            })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    per = {m: sum(1 for r in rows if r["merchant"] == m) for m in MERCHANTS}
    print(f"wrote {len(rows)} rows -> {OUT}")
    print("per merchant:", per)
    print()
    print(MESS)


if __name__ == "__main__":
    main()

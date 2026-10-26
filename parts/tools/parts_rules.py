"""Rules for parts.json. Same rules as the app (PartsCatalogValidator.kt).
The app rejects the WHOLE file if one rule fails, so everything is checked here first.
"""
import re

ISO = re.compile(r"^\d{4}-\d{2}(-\d{2})?$")
ID_RE = re.compile(r"[a-z0-9_]{1,40}")
TRACKING = re.compile(r"(utm_|aff|ref=|tag=)")
REQ = {
    "cpu": ["socket", "cores", "threads", "tdp_w", "memory_type"],
    "gpu": ["vram_gb", "vram_type", "bus_bits", "board_power_w", "recommended_psu_w"],
    "ram": ["capacity_gb", "type", "speed_mts", "modules"],
    "storage": ["capacity_gb", "interface"],
    "motherboard": ["socket", "chipset", "memory_type", "form_factor"],
    "psu": ["watts", "efficiency"],
}
RANGES = {"cores": (1, 128), "threads": (1, 256), "tdp_w": (1, 2000), "vram_gb": (0, 64),
          "bus_bits": (32, 1024), "board_power_w": (1, 2000), "recommended_psu_w": (1, 2000),
          "capacity_gb": (1, 64000), "speed_mts": (800, 12000), "modules": (1, 8), "watts": (1, 2000),
          # optional official details (catalog v3): checked only when present
          "max_power_w": (1, 2000), "cache_mb": (1, 1024), "boost_mhz": (100, 5000), "length_mm": (50, 500),
          "displays": (1, 8)}
DECIMAL_RANGES = {"base_ghz": (0.5, 7.0), "boost_ghz": (0.5, 7.0)}
BOOLEAN_SPECS = ("integrated_graphics", "cooler_included")
# launch_msrp = maker's launch price, reference = other reference price, rcp = Intel Recommended Customer Price
PRICE_KINDS = ("launch_msrp", "reference", "rcp")
CURRENCIES = {"MAD", "USD", "EUR", "GBP", "JPY", "CNY", "CHF", "CAD", "AUD", "INR", "KRW",
              "BRL", "MXN", "ZAR", "TRY", "SEK", "SAR", "AED"}


def is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def check_catalog(cat):
    """Return a list of error strings (empty = valid)."""
    err = []
    e = err.append
    if cat.get("schema") != 1:
        e("schema must be 1")
    if not ISO.match(str(cat.get("as_of", ""))):
        e("catalog as_of must be YYYY-MM-DD")
    if cat.get("currency") != "USD":
        e("currency must be USD")
    parts = cat.get("parts") or []
    if not 1 <= len(parts) <= 2000:
        e("part count must be 1..2000")
    ids = [p.get("id") for p in parts]
    for d in sorted({x for x in ids if ids.count(x) > 1}, key=str):
        e(f"duplicate id {d}")

    for p in parts:
        pid = p.get("id", "<no id>")
        for k in ("id", "type", "name", "specs", "spec_source"):
            if k not in p:
                e(f"{pid}: missing field {k}")
        if not ID_RE.fullmatch(str(pid)):
            e(f"{pid}: id must be 1..40 chars of a-z, 0-9, _")
        if not 1 <= len(str(p.get("name", ""))) <= 80:
            e(f"{pid}: name must be 1..80 chars")
        t = p.get("type")
        if t not in REQ:
            e(f"{pid}: unknown type {t}")
            continue
        specs = p.get("specs") or {}
        for k in REQ[t]:
            if k not in specs:
                e(f"{pid}: missing spec {k}")
        for k, (lo, hi) in RANGES.items():
            if k in specs:
                if not is_int(specs[k]):
                    e(f"{pid}: {k} must be a whole number")
                elif not lo <= specs[k] <= hi:
                    e(f"{pid}: {k} out of range {lo}..{hi}")
        for k, (lo, hi) in DECIMAL_RANGES.items():
            if k in specs:
                v = specs[k]
                if not isinstance(v, (int, float)) or isinstance(v, bool) or not lo <= v <= hi:
                    e(f"{pid}: {k} out of range {lo}..{hi}")
        for k in BOOLEAN_SPECS:
            if k in specs and not isinstance(specs[k], bool):
                e(f"{pid}: {k} must be true or false")
        if p.get("spec_checked") is not None and not ISO.match(str(p["spec_checked"])):
            e(f"{pid}: spec_checked must be YYYY-MM-DD")
        if t == "cpu" and is_int(specs.get("threads")) and is_int(specs.get("cores")) \
                and specs["threads"] < specs["cores"]:
            e(f"{pid}: threads<cores")

        b = p.get("bench")
        if b is not None:
            if not b.get("source") or not ISO.match(str(b.get("as_of", ""))):
                e(f"{pid}: bench without source/as_of")
            for k, v in b.items():
                if k in ("source", "as_of"):
                    continue
                if not is_int(v) or not 1 <= v <= 1000:
                    e(f"{pid}: bench {k} must be a whole number 1..1000")

        pr = p.get("price")
        generic = p.get("generic", False) is True
        if pr is not None:
            if not is_int(pr.get("reference")) or not 1 <= pr["reference"] <= 20000:
                e(f"{pid}: price.reference must be a whole number 1..20000")
            if pr.get("usual") is not None and not is_int(pr["usual"]):
                e(f"{pid}: price.usual must be a whole number or null")
            if pr.get("kind") not in PRICE_KINDS:
                e(f"{pid}: price.kind must be one of {', '.join(PRICE_KINDS)}")
            if not pr.get("source") or not ISO.match(str(pr.get("as_of", ""))):
                e(f"{pid}: price without source/as_of")
        if not generic and not str(p.get("spec_source", "")).startswith("https://"):
            e(f"{pid}: branded part needs https spec_source")
        if generic and pr is not None:
            e(f"{pid}: generic part must not carry a price")

    fx = cat.get("fx") or {}
    rates = fx.get("rates") or {}
    if fx.get("base") != "USD":
        e("fx base must be USD")
    if set(rates) != CURRENCIES:
        e(f"fx currency codes differ: {sorted(set(rates) ^ CURRENCIES)}")
    if any(not isinstance(v, (int, float)) or v <= 0 for v in rates.values()):
        e("fx rate must be > 0")
    if rates.get("USD") != 1.0:
        e("fx USD must be 1")
    if not ISO.match(str(fx.get("as_of", ""))):
        e("fx as_of must be YYYY-MM-DD")
    elif str(fx.get("as_of")) > str(cat.get("as_of", "")):
        e("fx as_of is newer than catalog as_of")

    regions = set()
    for c in cat.get("comparators") or []:
        cid = c.get("id", "<no id>")
        url = str(c.get("search_url", ""))
        if not url.startswith("https://") or "{query}" not in url:
            e(f"{cid}: url must be https and contain {{query}}")
        if TRACKING.search(url):
            e(f"{cid}: tracking parameter")
        for r in c.get("regions") or []:
            if r in regions:
                e(f"region {r} duplicated")
            regions.add(r)
    if "global" not in regions:
        e("no global fallback comparator")

    by = lambda t: [p for p in parts if p.get("type") == t]
    for c in by("cpu"):
        s = c.get("specs") or {}
        mt = str(s.get("memory_type", "")).split("/")
        if not any((b.get("specs") or {}).get("socket") == s.get("socket")
                   and (b.get("specs") or {}).get("memory_type") in mt for b in by("motherboard")):
            e(f"{c.get('id')}: no compatible board")
    for b in by("motherboard"):
        mt = (b.get("specs") or {}).get("memory_type")
        if not any((r.get("specs") or {}).get("type") == mt for r in by("ram")):
            e(f"{b.get('id')}: no matching RAM")
    return err

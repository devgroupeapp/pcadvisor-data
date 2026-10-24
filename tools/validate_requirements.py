"""Validate requirements/requirements.json (software requirements format v1).

  python tools/validate_requirements.py                      -> checks requirements/requirements.json
  python tools/validate_requirements.py path/to/file.json    -> checks another file
  python tools/validate_requirements.py file.json --allow-examples
                                                             -> also accepts example.com sources (test fixtures only)

Prints one line per problem as  ERROR [record_id] field.path: message  and exits 1 if any error.
The format is described in requirements/README.md. This file is NOT read by the app yet.
"""
import datetime, json, pathlib, re, sys
from urllib.parse import urlsplit, parse_qsl

FORMAT = "pcadvisor-requirements"
SCHEMA_VERSION = 1

STATUSES = {"verified", "partially_verified", "no_official_spec",
            "discontinued", "verification_blocked"}
# Why a field has no value. Never use 0 or "" for these.
MISSING_REASONS = {"not_specified",   # the publisher's page does not give this value
                   "not_verified",    # nobody has checked this value yet
                   "blocked",         # the official page could not be opened
                   "not_applicable"}  # the field makes no sense for this app (e.g. GPU for a web app)
OS_KEYS = {"windows", "macos", "linux", "web"}
LEVELS = ("minimum", "recommended")
# Field name -> allowed Python types of "value". Only fields an official page can state.
FIELDS = {"os": (str,), "cpu": (str,), "cpu_cores": (int,), "ram_gb": (int, float),
          "gpu": (str,), "vram_gb": (int, float), "storage_gb": (int, float), "display": (str,)}
NUMERIC = {"cpu_cores", "ram_gb", "vram_gb", "storage_gb"}
NUMERIC_MAX = {"cpu_cores": 128, "ram_gb": 1024, "vram_gb": 128, "storage_gb": 10000}

ID_RE = re.compile(r"[a-z0-9_]{1,40}")
DOMAIN_RE = re.compile(r"(?:[a-z0-9-]+\.)+[a-z]{2,}")
CTRL_RE = re.compile(r"[\x00-\x1f\x7f]")
EXAMPLE_DOMAINS = {"example.com", "example.org", "example.net"}
# Tracking / affiliate query keys (same rule as the parts catalog, checked on query keys only so
# names such as "affinity" in a path are not rejected).
TRACKING_KEYS = re.compile(r"^(utm_.*|aff|aff_id|affid|affiliate|ref|tag|gclid|fbclid)$", re.I)

TOP_KEYS = {"format", "schema_version", "generated_on", "records"}
RECORD_KEYS = {"id", "name", "publisher", "applies_to", "status", "checked_on",
               "sources", "platforms", "notes"}
NOTE_KINDS = {"quote", "normalized", "maintainer"}


class Report:
    def __init__(self):
        self.errors, self.warnings = [], []

    def err(self, rid, path, msg):
        self.errors.append(f"[{rid}] {path}: {msg}")

    def warn(self, rid, path, msg):
        self.warnings.append(f"[{rid}] {path}: {msg}")


def parse_date(s):
    if not isinstance(s, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return None
    try:
        return datetime.date.fromisoformat(s)
    except ValueError:
        return None


def check_date(rep, rid, path, s, today):
    d = parse_date(s)
    if d is None:
        rep.err(rid, path, f"must be a date YYYY-MM-DD, got {s!r}")
    elif d > today:
        rep.err(rid, path, f"{s} is in the future")
    elif d.year < 2000:
        rep.err(rid, path, f"{s} is too old")
    return d


def unknown_keys(rep, rid, path, obj, allowed):
    for k in sorted(set(obj) - allowed):
        rep.err(rid, f"{path}.{k}" if path else k, "unknown field (not part of format v1)")


def host_of(url):
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def on_domain(host, domains):
    return any(host == d or host.endswith("." + d) for d in domains)


def check_url(rep, rid, path, url, domains, allow_examples):
    if not isinstance(url, str) or not url.startswith("https://") or CTRL_RE.search(url) or " " in url:
        rep.err(rid, path, f"must be an https URL, got {url!r}")
        return
    parts = urlsplit(url)
    host = host_of(url)
    if not host or not DOMAIN_RE.fullmatch(host):
        rep.err(rid, path, f"invalid host in {url!r}")
        return
    for key, _ in parse_qsl(parts.query, keep_blank_values=True):
        if TRACKING_KEYS.match(key):
            rep.err(rid, path, f"tracking/affiliate parameter {key!r} is not allowed")
    if host in EXAMPLE_DOMAINS or any(host.endswith("." + d) for d in EXAMPLE_DOMAINS):
        if not allow_examples:
            rep.err(rid, path, "example.com sources are only allowed in test fixtures")
        return
    if not on_domain(host, domains):
        rep.err(rid, path, f"host {host} is not one of the publisher's domains {sorted(domains)}")


def check_field(rep, rid, path, f):
    """Returns ('value', v) or ('missing', reason) or None if malformed."""
    if not isinstance(f, dict) or len(f) == 0:
        rep.err(rid, path, 'must be {"value": ...} or {"missing": "<reason>"}')
        return None
    name = path.rsplit(".", 1)[-1]
    if "value" in f and "missing" in f:
        rep.err(rid, path, "cannot have both value and missing")
        return None
    if "missing" in f:
        unknown_keys(rep, rid, path, f, {"missing"})
        if f["missing"] not in MISSING_REASONS:
            rep.err(rid, path, f"missing must be one of {sorted(MISSING_REASONS)}, got {f['missing']!r}")
            return None
        return ("missing", f["missing"])
    if "value" not in f:
        rep.err(rid, path, 'needs "value" or "missing"')
        return None
    unknown_keys(rep, rid, path, f, {"value", "quote"})
    v = f["value"]
    if v is None:
        rep.err(rid, path, 'value is null: use {"missing": "<reason>"} instead')
        return None
    types = FIELDS[name]
    if isinstance(v, bool) or not isinstance(v, types):
        rep.err(rid, path, f"value must be {'/'.join(t.__name__ for t in types)}, got {type(v).__name__}")
        return None
    if name in NUMERIC and not (0 < v <= NUMERIC_MAX[name]):
        rep.err(rid, path, f"value {v} out of range (0, {NUMERIC_MAX[name]}]; "
                           "use missing instead of 0 when the page gives no number")
        return None
    if isinstance(v, str) and (not v.strip() or len(v) > 200 or CTRL_RE.search(v)):
        rep.err(rid, path, "text value must be 1..200 chars, no control characters")
        return None
    if "quote" in f and (not isinstance(f["quote"], str) or not 1 <= len(f["quote"]) <= 200):
        rep.err(rid, f"{path}.quote", "must be text of 1..200 chars")
    return ("value", v)


def check_record(rep, r, today, allow_examples, known_ids):
    rid = r.get("id") if isinstance(r, dict) and isinstance(r.get("id"), str) else "<no id>"
    if not isinstance(r, dict):
        rep.err(rid, "record", "must be an object")
        return
    missing = [k for k in sorted(RECORD_KEYS) if k not in r]
    for k in missing:
        rep.err(rid, k, "required field is missing (use null where the format allows it)")
    unknown_keys(rep, rid, "", r, RECORD_KEYS)
    if missing:
        return

    if not ID_RE.fullmatch(r["id"]):
        rep.err(rid, "id", "must be 1..40 chars of a-z, 0-9, _")
    elif known_ids is not None and r["id"] not in known_ids:
        rep.warn(rid, "id", "not an app catalogue id (baseline/apps.v1.json): the app would ignore it")
    if not isinstance(r["name"], str) or not 1 <= len(r["name"]) <= 80 or CTRL_RE.search(r["name"]):
        rep.err(rid, "name", "must be 1..80 chars, no control characters")

    # publisher
    pub = r["publisher"]
    domains = set()
    if not isinstance(pub, dict):
        rep.err(rid, "publisher", "must be an object {name, domains}")
    else:
        unknown_keys(rep, rid, "publisher", pub, {"name", "domains"})
        if not isinstance(pub.get("name"), str) or not 1 <= len(pub["name"]) <= 80:
            rep.err(rid, "publisher.name", "must be 1..80 chars")
        ds = pub.get("domains")
        if not isinstance(ds, list) or not ds:
            rep.err(rid, "publisher.domains", "must be a non-empty list of domains such as adobe.com")
        else:
            for i, d in enumerate(ds):
                if not isinstance(d, str) or not DOMAIN_RE.fullmatch(d):
                    rep.err(rid, f"publisher.domains[{i}]", f"not a plain domain: {d!r}")
                else:
                    domains.add(d)

    # applies_to: version/edition exactly as the official page names them, or null if it names none
    at = r["applies_to"]
    if not isinstance(at, dict):
        rep.err(rid, "applies_to", "must be an object {version, edition}")
    else:
        unknown_keys(rep, rid, "applies_to", at, {"version", "edition"})
        for k in ("version", "edition"):
            if k not in at:
                rep.err(rid, f"applies_to.{k}", "required (null if the official page names none)")
            elif at[k] is not None and (not isinstance(at[k], str) or not 1 <= len(at[k]) <= 60):
                rep.err(rid, f"applies_to.{k}", "must be null or 1..60 chars")

    status = r["status"]
    if status not in STATUSES:
        rep.err(rid, "status", f"must be one of {sorted(STATUSES)}, got {status!r}")
    checked = check_date(rep, rid, "checked_on", r["checked_on"], today)

    # sources
    srcs = r["sources"]
    if not isinstance(srcs, list):
        rep.err(rid, "sources", "must be a list")
        srcs = []
    for i, s in enumerate(srcs):
        p = f"sources[{i}]"
        if not isinstance(s, dict):
            rep.err(rid, p, "must be an object {url, title, retrieved_on}")
            continue
        unknown_keys(rep, rid, p, s, {"url", "title", "retrieved_on"})
        for k in ("url", "title", "retrieved_on"):
            if k not in s:
                rep.err(rid, f"{p}.{k}", "required")
        if "url" in s:
            check_url(rep, rid, f"{p}.url", s["url"], domains, allow_examples)
        if "title" in s and (not isinstance(s["title"], str) or not 1 <= len(s["title"]) <= 150):
            rep.err(rid, f"{p}.title", "must be 1..150 chars")
        if "retrieved_on" in s:
            d = check_date(rep, rid, f"{p}.retrieved_on", s["retrieved_on"], today)
            if d and checked and d > checked:
                rep.err(rid, f"{p}.retrieved_on", "is later than the record's checked_on")
    urls = [s.get("url") for s in srcs if isinstance(s, dict)]
    for u in {u for u in urls if urls.count(u) > 1}:
        rep.err(rid, "sources", f"duplicate source url {u}")

    # platforms
    plats = r["platforms"]
    values, reasons = [], []
    if not isinstance(plats, dict):
        rep.err(rid, "platforms", "must be an object keyed by os (windows, macos, linux, web)")
        plats = {}
    for os_key in sorted(set(plats) - OS_KEYS):
        rep.err(rid, f"platforms.{os_key}", f"unknown platform (allowed: {sorted(OS_KEYS)})")
    for os_key in sorted(set(plats) & OS_KEYS):
        plat = plats[os_key]
        pp = f"platforms.{os_key}"
        if not isinstance(plat, dict):
            rep.err(rid, pp, "must be an object {minimum, recommended}")
            continue
        unknown_keys(rep, rid, pp, plat, set(LEVELS))
        parsed = {}
        for lvl in LEVELS:
            if lvl not in plat:
                rep.err(rid, f"{pp}.{lvl}", "required (every field listed, with value or missing)")
                continue
            lv = plat[lvl]
            if not isinstance(lv, dict):
                rep.err(rid, f"{pp}.{lvl}", "must be an object")
                continue
            unknown_keys(rep, rid, f"{pp}.{lvl}", lv, set(FIELDS))
            parsed[lvl] = {}
            for name in FIELDS:
                fp = f"{pp}.{lvl}.{name}"
                if name not in lv:
                    rep.err(rid, fp, 'required: give {"value": ...} or {"missing": "<reason>"}')
                    continue
                res = check_field(rep, rid, fp, lv[name])
                if res:
                    parsed[lvl][name] = res
                    (values if res[0] == "value" else reasons).append((fp, res[1]))
        # recommended can never be lower than minimum
        mn, rc = parsed.get("minimum", {}), parsed.get("recommended", {})
        for name in NUMERIC:
            a, b = mn.get(name), rc.get(name)
            if a and b and a[0] == b[0] == "value" and b[1] < a[1]:
                rep.err(rid, f"{pp}.recommended.{name}", f"{b[1]} is lower than minimum {a[1]}")

    # notes: quoted / normalized official text vs maintainer remarks, never mixed
    notes = r["notes"]
    if not isinstance(notes, list):
        rep.err(rid, "notes", "must be a list")
        notes = []
    for i, n in enumerate(notes):
        p = f"notes[{i}]"
        if not isinstance(n, dict):
            rep.err(rid, p, "must be an object {kind, text}")
            continue
        unknown_keys(rep, rid, p, n, {"kind", "text"})
        if n.get("kind") not in NOTE_KINDS:
            rep.err(rid, f"{p}.kind", f"must be one of {sorted(NOTE_KINDS)}")
        if not isinstance(n.get("text"), str) or not 1 <= len(n["text"]) <= 300:
            rep.err(rid, f"{p}.text", "must be 1..300 chars")

    # status invariants
    if status in ("verified", "partially_verified", "discontinued"):
        if not srcs:
            rep.err(rid, "sources", f"status {status} needs at least one official source")
        # a discontinued product may have no requirements page left: its source is the announcement
        if not plats and status != "discontinued":
            rep.err(rid, "platforms", f"status {status} needs at least one platform")
    if status == "verified":
        for fp, reason in reasons:
            if reason in ("not_verified", "blocked"):
                rep.err(rid, fp, f"status verified cannot have a field marked {reason}")
    if status == "partially_verified" and plats and not values:
        rep.err(rid, "platforms", "status partially_verified needs at least one checked value")
    if status in ("no_official_spec", "verification_blocked"):
        for fp, _ in values:
            rep.err(rid, fp, f"status {status} cannot carry values (there is no official page to take them from)")
    if status == "verification_blocked":
        if not srcs:
            rep.err(rid, "sources", "status verification_blocked must list the page that could not be opened")
        for fp, reason in reasons:
            if reason != "blocked":
                rep.err(rid, fp, "status verification_blocked: every field must be missing: blocked")
    if status == "no_official_spec":
        for fp, reason in reasons:
            if reason not in ("not_specified", "not_applicable"):
                rep.err(rid, fp, "status no_official_spec: fields must be missing: not_specified or not_applicable")


def validate(doc, today=None, allow_examples=False, known_ids=None):
    today = today or datetime.date.today()
    rep = Report()
    if not isinstance(doc, dict):
        rep.err("file", "root", "must be a JSON object")
        return rep
    for k in sorted(TOP_KEYS - set(doc)):
        rep.err("file", k, "required top-level field is missing")
    unknown_keys(rep, "file", "", doc, TOP_KEYS)
    if doc.get("format") != FORMAT:
        rep.err("file", "format", f"must be {FORMAT!r}")
    if doc.get("schema_version") != SCHEMA_VERSION:
        rep.err("file", "schema_version", f"must be {SCHEMA_VERSION} (this validator only knows v1)")
    if "generated_on" in doc:
        check_date(rep, "file", "generated_on", doc["generated_on"], today)
    recs = doc.get("records")
    if not isinstance(recs, list):
        rep.err("file", "records", "must be a list")
        return rep
    ids = [r.get("id") for r in recs if isinstance(r, dict)]
    for d in sorted({x for x in ids if isinstance(x, str) and ids.count(x) > 1}):
        rep.err(d, "id", "duplicate id (each id must appear once)")
    for r in recs:
        check_record(rep, r, today, allow_examples, known_ids)
    return rep


def load_known_ids(root):
    base = root / "baseline" / "apps.v1.json"
    if not base.exists():
        return None
    return {r["id"] for r in json.loads(base.read_text(encoding="utf-8"))}


def main(argv):
    root = pathlib.Path(__file__).resolve().parent.parent
    args = [a for a in argv if not a.startswith("--")]
    allow_examples = "--allow-examples" in argv
    path = pathlib.Path(args[0]) if args else root / "requirements" / "requirements.json"
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"ERROR [file] {path}: cannot read JSON: {e}")
        return 1
    rep = validate(doc, allow_examples=allow_examples,
                   known_ids=None if allow_examples else load_known_ids(root))
    for w in rep.warnings:
        print("WARN ", w)
    for e in rep.errors:
        print("ERROR", e)
    n = len(doc.get("records", [])) if isinstance(doc, dict) and isinstance(doc.get("records"), list) else 0
    print(f"\n{path.name}: {n} records, {len(rep.errors)} errors, {len(rep.warnings)} warnings")
    return 1 if rep.errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

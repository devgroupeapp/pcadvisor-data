"""Publish a new PARTS catalog version (parts, prices, exchange rates, price-comparison sites).

  python parts/tools/publish_parts.py               -> checks parts.json, data_version + 1, signs
  python parts/tools/publish_parts.py --sign-only   -> keeps parts.json and parts_manifest.json, only (re)signs
  python parts/tools/publish_parts.py --min-app 5   -> also sets min_app_version_code (default: keep, or 4)

Then run parts/tools/validate_parts.py and upload parts.json, parts_manifest.json AND parts_manifest.json.sig.
This is separate from apps.json / manifest.json (tools/publish.py). Neither script touches the other's files.
"""
import datetime, hashlib, json, pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent          # parts/tools
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent / "tools"))   # shared signing.py (same key as apps.json)
from signing import sign, verify, need_crypto
from parts_rules import check_catalog

need_crypto()
root = HERE.parent                                       # parts/
PARTS = root / "parts.json"
MANIFEST = root / "parts_manifest.json"
SIG = root / "parts_manifest.json.sig"
MAX_BYTES = 2 * 1024 * 1024  # same limit as the app
DEFAULT_MIN_APP = 4

args = sys.argv[1:]
sign_only = "--sign-only" in args
min_app = None
if "--min-app" in args:
    try:
        min_app = int(args[args.index("--min-app") + 1])
    except (IndexError, ValueError):
        sys.exit("Use: --min-app <versionCode>, for example --min-app 5")

if not sign_only:
    if not PARTS.exists():
        sys.exit(f"Not found: {PARTS}")
    try:
        cat = json.loads(PARTS.read_text(encoding="utf-8"))
    except json.JSONDecodeError as ex:
        sys.exit(f"parts.json is not valid JSON: {ex}")
    errors = check_catalog(cat)
    if errors:
        for m in errors:
            print("ERROR", m)
        sys.exit(f"\n{len(errors)} errors. Nothing was published. Fix parts.json and run again.")

    data = (json.dumps(cat, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    if len(data) > MAX_BYTES:
        sys.exit(f"parts.json is {len(data)} bytes; the app refuses files over {MAX_BYTES}.")

    old = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    manifest = {
        "schema_version": 1,
        "data_version": int(old.get("data_version", 0)) + 1,
        "published_on": datetime.date.today().isoformat(),
        "parts_file": "parts.json",
        "parts_sha256": hashlib.sha256(data).hexdigest(),
        "parts_count": len(cat["parts"]),
        "min_app_version_code": min_app if min_app is not None
        else int(old.get("min_app_version_code", DEFAULT_MIN_APP)),
    }
    PARTS.write_bytes(data)
    MANIFEST.write_bytes((json.dumps(manifest, indent=2) + "\n").encode("utf-8"))
elif not MANIFEST.exists():
    sys.exit("parts_manifest.json does not exist yet. Run without --sign-only first.")

# Unix line endings, then sign the exact bytes the app will download.
manifest_bytes = MANIFEST.read_bytes().replace(b"\r\n", b"\n")
MANIFEST.write_bytes(manifest_bytes)
sig = sign(manifest_bytes)
if not verify(manifest_bytes, sig):
    sys.exit("Signature self-check FAILED: the private key does not match tools/data_signing_public.txt (in the main tools folder)")
SIG.write_bytes((sig + "\n").encode("ascii"))

m = json.loads(manifest_bytes)
print(f"{'Re-signed' if sign_only else 'Published'} parts data_version {m['data_version']} "
      f"({m['parts_count']} parts) -> parts_manifest.json.sig written")
print("Next: python parts/tools/validate_parts.py")

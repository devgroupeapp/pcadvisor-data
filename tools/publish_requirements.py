"""Publish a new SOFTWARE REQUIREMENTS version (requirements/requirements.json).

  python tools/publish_requirements.py               -> validates, data_version + 1, signs
  python tools/publish_requirements.py --sign-only   -> keeps the files, only (re)signs
  python tools/publish_requirements.py --min-app 5   -> also sets min_app_version_code (default: keep, or 4)

Then upload requirements/requirements.json, requirements/requirements_manifest.json AND
requirements/requirements_manifest.json.sig to GitHub (same folder names).
Copy requirements/requirements.json byte-for-byte into the Android project:
  app/src/main/assets/requirements.json
Never edit the Android copy by hand: a unit test in the app checks it.
This script does not touch apps.json, parts.json or their manifests.
"""
import datetime, hashlib, json, pathlib, sys
from signing import sign, verify, need_crypto
from validate_requirements import validate, load_known_ids

need_crypto()
root = pathlib.Path(__file__).resolve().parent.parent
DATA = root / "requirements" / "requirements.json"
MANIFEST = root / "requirements" / "requirements_manifest.json"
SIG = root / "requirements" / "requirements_manifest.json.sig"
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
    if not DATA.exists():
        sys.exit(f"Not found: {DATA}")
    data = DATA.read_bytes()
    if b"\r\n" in data:
        sys.exit("requirements.json has Windows line endings. Save it with Unix (LF) line endings.")
    try:
        doc = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as ex:
        sys.exit(f"requirements.json is not valid JSON: {ex}")
    rep = validate(doc, known_ids=load_known_ids(root))
    for w in rep.warnings:
        print("WARN ", w)
    if rep.errors:
        for m in rep.errors:
            print("ERROR", m)
        sys.exit(f"\n{len(rep.errors)} errors. Nothing was published. Fix requirements.json and run again.")
    if len(data) > MAX_BYTES:
        sys.exit(f"requirements.json is {len(data)} bytes; the app refuses files over {MAX_BYTES}.")

    old = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    manifest = {
        "schema_version": 1,
        "data_version": int(old.get("data_version", 0)) + 1,
        "published_on": datetime.date.today().isoformat(),
        "requirements_file": "requirements.json",
        "requirements_sha256": hashlib.sha256(data).hexdigest(),
        "records_count": len(doc["records"]),
        "min_app_version_code": min_app if min_app is not None
        else int(old.get("min_app_version_code", DEFAULT_MIN_APP)),
    }
    MANIFEST.write_bytes((json.dumps(manifest, indent=2) + "\n").encode("utf-8"))
elif not MANIFEST.exists():
    sys.exit("requirements_manifest.json does not exist yet. Run without --sign-only first.")

# Unix line endings, then sign the exact bytes the app will download.
manifest_bytes = MANIFEST.read_bytes().replace(b"\r\n", b"\n")
MANIFEST.write_bytes(manifest_bytes)
sig = sign(manifest_bytes)
if not verify(manifest_bytes, sig):
    sys.exit("Signature self-check FAILED: the private key does not match tools/data_signing_public.txt")
SIG.write_bytes((sig + "\n").encode("ascii"))

m = json.loads(manifest_bytes)
print(f"{'Re-signed' if sign_only else 'Published'} requirements data_version {m['data_version']} "
      f"({m['records_count']} records) -> requirements_manifest.json.sig written")
print("Next: copy requirements/requirements.json to the app's app/src/main/assets/requirements.json")

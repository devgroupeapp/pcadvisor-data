"""Check the PUBLISHED software requirements release before/after uploading:
requirements/requirements.json + requirements_manifest.json + requirements_manifest.json.sig.

  python tools/validate_requirements_release.py

- None of the three files present  -> "not published yet", exit 0 (nothing to check).
- Some but not all present          -> exit 1 (half-finished upload).
- All three present                 -> same checks as the app, in the same order: signature,
                                       manifest fields, sha256, record count, then every record
                                       (tools/validate_requirements.py). Exit 1 on any error.
Unlike the older validators, a missing `cryptography` library is an ERROR here, never a skip.
"""
import hashlib, json, pathlib, sys

TOOLS = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
root = TOOLS.parent
FOLDER = root / "requirements"
DATA = FOLDER / "requirements.json"
MANIFEST = FOLDER / "requirements_manifest.json"
SIG = FOLDER / "requirements_manifest.json.sig"
MAX_BYTES = 2 * 1024 * 1024
errors = []

present = [f for f in (DATA, MANIFEST, SIG) if f.exists()]
if not present:
    print("requirements: not published yet (no requirements/requirements_manifest.json): skipped")
    sys.exit(0)
if len(present) != 3:
    for f in (DATA, MANIFEST, SIG):
        if not f.exists():
            print(f"ERROR requirements/{f.name} is missing: upload all three files together")
    sys.exit(1)

try:
    import cryptography  # noqa: F401
    from signing import verify
except ImportError:
    print("ERROR cryptography not installed: the signature cannot be checked (python -m pip install cryptography)")
    sys.exit(1)

raw = DATA.read_bytes()
manifest_raw = MANIFEST.read_bytes()

# 1. Signature (the app checks this first)
if b"\r\n" in manifest_raw:
    errors.append("requirements_manifest.json has Windows line endings (run tools/publish_requirements.py --sign-only)")
elif not verify(manifest_raw, SIG.read_text(encoding="ascii")):
    errors.append("requirements_manifest.json.sig does NOT match requirements_manifest.json / public key")

# 2. Manifest fields
try:
    manifest = json.loads(manifest_raw.decode("utf-8"))
except ValueError as e:
    print(f"ERROR requirements_manifest.json is not valid JSON: {e}")
    sys.exit(1)
for k in ("schema_version", "data_version", "requirements_file", "requirements_sha256",
          "records_count", "min_app_version_code"):
    if k not in manifest:
        errors.append(f"requirements_manifest.json is missing {k}")
if manifest.get("schema_version") != 1:
    errors.append("requirements_manifest schema_version must be 1")
if not isinstance(manifest.get("data_version"), int) or manifest.get("data_version", 0) < 1:
    errors.append("data_version must be a whole number of at least 1")
if manifest.get("requirements_file") != "requirements.json":
    errors.append("requirements_file must be requirements.json")

# 3. File integrity
if len(raw) > MAX_BYTES:
    errors.append("requirements.json is over 2 MB (the app refuses it)")
if hashlib.sha256(raw).hexdigest() != str(manifest.get("requirements_sha256", "")).lower():
    errors.append("requirements_sha256 does not match requirements.json (edited after publishing?)")
try:
    doc = json.loads(raw.decode("utf-8"))
except ValueError as e:
    errors.append(f"requirements.json is not valid JSON: {e}")
    doc = None
if isinstance(doc, dict) and manifest.get("records_count") != len(doc.get("records") or []):
    errors.append("records_count does not match the number of records in requirements.json")

for m in errors:
    print("ERROR", m)

# 4. Every record (same rules as before publishing)
from validate_requirements import main as validate_records  # noqa: E402
records_exit = validate_records([str(DATA)]) if doc is not None else 1

print(f"\nrequirements release: data_version {manifest.get('data_version')}, {len(errors)} release errors")
sys.exit(1 if errors or records_exit else 0)

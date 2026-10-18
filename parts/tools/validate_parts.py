"""Check parts.json + parts_manifest.json + parts_manifest.json.sig before uploading.

  python parts/tools/validate_parts.py

Exit code 0 = safe to upload. Same checks the app makes, in the same order.
"""
import hashlib, json, pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent          # parts/tools
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent / "tools"))   # shared signing.py
from parts_rules import check_catalog

root = HERE.parent                                       # parts/
PARTS = root / "parts.json"
MANIFEST = root / "parts_manifest.json"
SIG = root / "parts_manifest.json.sig"
errors, warnings = [], []

for f in (PARTS, MANIFEST, SIG):
    if not f.exists():
        errors.append(f"{f.name} is missing (run parts/tools/publish_parts.py)")
if errors:
    for m in errors:
        print("ERROR", m)
    sys.exit(1)

raw = PARTS.read_bytes()
manifest_raw = MANIFEST.read_bytes()
manifest = json.loads(manifest_raw.decode("utf-8"))
cat = json.loads(raw.decode("utf-8"))

# 1. Signature (the app checks this first)
try:
    import cryptography  # noqa: F401
    from signing import verify
    if b"\r\n" in manifest_raw:
        errors.append("parts_manifest.json has Windows line endings (run parts/tools/publish_parts.py --sign-only)")
    elif not verify(manifest_raw, SIG.read_text(encoding="ascii")):
        errors.append("parts_manifest.json.sig does NOT match parts_manifest.json / public key")
except ImportError:
    warnings.append("cryptography not installed: signature NOT checked (python -m pip install cryptography)")

# 2. Manifest fields
for k in ("schema_version", "data_version", "parts_file", "parts_sha256", "parts_count",
          "min_app_version_code"):
    if k not in manifest:
        errors.append(f"parts_manifest.json is missing {k}")
if manifest.get("schema_version") != 1:
    errors.append("parts_manifest schema_version must be 1")
pf = str(manifest.get("parts_file", ""))
if pf != "parts.json":
    errors.append("parts_file must be parts.json")

# 3. File integrity
if len(raw) > 2 * 1024 * 1024:
    errors.append("parts.json is over 2 MB (the app refuses it)")
if hashlib.sha256(raw).hexdigest() != str(manifest.get("parts_sha256", "")).lower():
    errors.append("parts_sha256 does not match parts.json (did you edit parts.json after publishing?)")
if manifest.get("parts_count") != len(cat.get("parts") or []):
    errors.append("parts_count does not match the number of parts in parts.json")
if b"\r\n" in raw:
    warnings.append("parts.json has Windows line endings (fine only if the sha256 above matches)")

# 4. Catalog rules
errors += check_catalog(cat)

for w in warnings:
    print("WARN ", w)
for m in errors:
    print("ERROR", m)
print(f"\n{len(cat.get('parts') or [])} parts, data_version {manifest.get('data_version')}, "
      f"{len(errors)} errors, {len(warnings)} warnings")
sys.exit(1 if errors else 0)

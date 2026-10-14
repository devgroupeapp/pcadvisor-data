"""Publish a new data version, or re-sign the current one.

  python tools/publish.py              -> data_version + 1, new manifest.json, signs it
  python tools/publish.py --sign-only  -> keeps apps.json and manifest.json as they are, only (re)signs

Always run tools/validate.py afterwards, then upload apps.json, manifest.json AND manifest.json.sig.
"""
import json, hashlib, datetime, pathlib, sys
from signing import SIG_FILE, sign, verify, need_crypto

need_crypto()
root = pathlib.Path(__file__).resolve().parent.parent
sign_only = "--sign-only" in sys.argv

if not sign_only:
    doc = json.loads((root / "apps.json").read_text(encoding="utf-8"))
    today = datetime.date.today().isoformat()
    doc["data_version"] += 1
    doc["generated_on"] = today

    data = (json.dumps(doc, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    (root / "apps.json").write_bytes(data)

    manifest = {"schema_version": 1, "data_version": doc["data_version"],
                "published_on": today, "apps_file": "apps.json",
                "apps_sha256": hashlib.sha256(data).hexdigest(),
                "apps_count": len(doc["apps"]), "min_app_version_code": 3}
    (root / "manifest.json").write_bytes((json.dumps(manifest, indent=2) + "\n").encode("utf-8"))

# Normalise to Unix line endings (Windows text mode writes CRLF; git could change them later
# and break the signature), then sign the exact bytes the app will download.
manifest_bytes = (root / "manifest.json").read_bytes().replace(b"\r\n", b"\n")
(root / "manifest.json").write_bytes(manifest_bytes)
sig = sign(manifest_bytes)
if not verify(manifest_bytes, sig):
    sys.exit("Signature self-check FAILED: the private key does not match tools/data_signing_public.txt")
SIG_FILE.write_bytes((sig + "\n").encode("ascii"))

version = json.loads(manifest_bytes)["data_version"]
print(f"{'Re-signed' if sign_only else 'Published'} data_version {version} -> manifest.json.sig written")

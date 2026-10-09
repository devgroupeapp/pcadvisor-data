import json, hashlib, datetime, pathlib

root = pathlib.Path(__file__).resolve().parent.parent
base = json.loads((root / "baseline/apps.v1.json").read_text(encoding="utf-8"))
today = datetime.date.today().isoformat()

apps = []
for r in base:
    r = dict(r)
    r["source"] = {"url": None, "type": "baseline_export",
                   "status": "unverified", "verified_on": None}
    apps.append(r)

doc = {"schema_version": 1, "data_version": 1,
       "generated_on": today, "apps": apps}
text = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
data = text.encode("utf-8")
(root / "apps.json").write_bytes(data)

manifest = {"schema_version": 1, "data_version": 1, "published_on": today,
            "apps_file": "apps.json",
            "apps_sha256": hashlib.sha256(data).hexdigest(),
            "apps_count": len(apps), "min_app_version_code": 3}
(root / "manifest.json").write_text(
    json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
print(f"Wrote apps.json ({len(apps)} records) and manifest.json")
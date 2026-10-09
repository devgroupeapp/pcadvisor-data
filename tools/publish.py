import json, hashlib, datetime, pathlib

root = pathlib.Path(__file__).resolve().parent.parent
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
(root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
print(f"Published data_version {doc['data_version']}")
import json, hashlib, pathlib, sys

root = pathlib.Path(__file__).resolve().parent.parent
CATEGORIES = {"GAMING", "LIVE_STREAMING", "MUSIC_PRODUCTION", "PROGRAMMING",
              "CREATIVE_DESIGN", "ENGINEERING_CAD", "AI_DATA_SCIENCE",
              "VIRTUAL_MACHINES", "STUDY_OFFICE", "COMBINED_WORKLOADS"}
OS_TIERS = {"CROSS_PLATFORM", "WINDOWS_10", "WINDOWS_11", "WINDOWS_11_PRO",
            "MACOS_13", "MACOS_14", "LINUX"}
CONFIDENCE = {"HIGH", "MEDIUM", "LOW"}
INT_FIELDS = ["minCpuCores", "recCpuCores", "heavyCpuCores", "minRamGb",
              "recRamGb", "heavyRamGb", "recGpuVramGb", "heavyGpuVramGb",
              "installationStorageGb", "recStorageFreeGb",
              "heavyStorageFreeGb", "displayTier"]
RANGES = {"Cores": (1, 64), "Ram": (1, 512), "Vram": (0, 48),
          "Storage": (0, 2000)}

errors, warnings = [], []
def err(i, m): errors.append(f"[{i}] {m}")

def check_record(r):
    i = r.get("id", "<no id>")
    for f in ["id", "name", "category", "needsDedicatedGpu", "osRequirement",
              "osTier", "confidence", "notes", "source", "minGpuVramGb"] + INT_FIELDS:
        if f not in r:
            err(i, f"missing field {f}")
    if errors and errors[-1].startswith(f"[{i}] missing"):
        return
    for f in INT_FIELDS:
        if not isinstance(r[f], int) or isinstance(r[f], bool):
            err(i, f"{f} must be an integer")
            return
    if r["minGpuVramGb"] is not None and not isinstance(r["minGpuVramGb"], int):
        err(i, "minGpuVramGb must be integer or null"); return
    if r["category"] not in CATEGORIES: err(i, f"unknown category {r['category']}")
    if r["osTier"] not in OS_TIERS: err(i, f"unknown osTier {r['osTier']}")
    if r["confidence"] not in CONFIDENCE: err(i, f"unknown confidence {r['confidence']}")
    # rec >= min
    if r["recCpuCores"] < r["minCpuCores"]: err(i, "recCpuCores < minCpuCores")
    if r["recRamGb"] < r["minRamGb"]: err(i, "recRamGb < minRamGb")
    if r["minGpuVramGb"] is not None and r["recGpuVramGb"] < r["minGpuVramGb"]:
        err(i, "recGpuVramGb < minGpuVramGb")
    # heavy >= rec
    for a, b in [("heavyCpuCores", "recCpuCores"), ("heavyRamGb", "recRamGb"),
                 ("heavyGpuVramGb", "recGpuVramGb"),
                 ("heavyStorageFreeGb", "recStorageFreeGb")]:
        if r[a] < r[b]: err(i, f"{a} < {b}")
    if not 1 <= r["displayTier"] <= 5: err(i, "displayTier not in 1..5")
    if r["recStorageFreeGb"] < r["installationStorageGb"]:
        err(i, "recStorageFreeGb < installationStorageGb")
    for f in ["minCpuCores", "recCpuCores", "heavyCpuCores"]:
        if not RANGES["Cores"][0] <= r[f] <= RANGES["Cores"][1]: err(i, f"{f} out of range")
    for f in ["minRamGb", "recRamGb", "heavyRamGb"]:
        if not RANGES["Ram"][0] <= r[f] <= RANGES["Ram"][1]: err(i, f"{f} out of range")
    for f in ["recGpuVramGb", "heavyGpuVramGb"]:
        if not RANGES["Vram"][0] <= r[f] <= RANGES["Vram"][1]: err(i, f"{f} out of range")
    for f in ["installationStorageGb", "recStorageFreeGb", "heavyStorageFreeGb"]:
        if not RANGES["Storage"][0] <= r[f] <= RANGES["Storage"][1]: err(i, f"{f} out of range")
    s = r["source"]
    if s.get("type") != "baseline_export" and not (s.get("url") and s.get("verified_on")):
        err(i, "non-baseline record needs source.url and source.verified_on")

raw = (root / "apps.json").read_bytes()
manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
doc = json.loads(raw.decode("utf-8"))
baseline = json.loads((root / "baseline/apps.v1.json").read_text(encoding="utf-8"))

if hashlib.sha256(raw).hexdigest() != manifest["apps_sha256"]:
    errors.append("manifest sha256 does not match apps.json")
if manifest["apps_count"] != len(doc["apps"]):
    errors.append("manifest apps_count does not match apps.json")
if doc["schema_version"] != 1: errors.append("unsupported schema_version")

ids = [r.get("id") for r in doc["apps"]]
for d in {x for x in ids if ids.count(x) > 1}: errors.append(f"duplicate id {d}")
for r in doc["apps"]: check_record(r)

base_ids = {r["id"] for r in baseline}
for r in doc["apps"]:
    if r.get("id") not in base_ids:
        warnings.append(f"id {r.get('id')} is not in baseline (app will ignore it)")

if doc["data_version"] == 1:
    strip = lambda r: {k: v for k, v in r.items() if k != "source"}
    a = {r["id"]: strip(r) for r in doc["apps"]}
    b = {r["id"]: r for r in baseline}
    if a != b: errors.append("data_version 1 differs from baseline")

for w in warnings: print("WARN ", w)
for e in errors: print("ERROR", e)
print(f"\n{len(doc['apps'])} records, {len(errors)} errors, {len(warnings)} warnings")
sys.exit(1 if errors else 0)
# Software requirements — format v1

`requirements.json` holds the **official** hardware requirements of the software that PC Advisor
knows about, with where each value came from. It is the future replacement for the numbers in
`apps.json`.

**Status (24 Oct 2026): 35 records, data_version 1, signed.** It is published as three files that
always travel together: `requirements.json`, `requirements_manifest.json` and
`requirements_manifest.json.sig` (made by `python tools/publish_requirements.py`, checked by
`python tools/validate_requirements_release.py` and by the GitHub "Validate data" run).
App versions that contain the requirements downloader (`RemoteRequirementsRepository`) read it from
`https://devgroupeapp.github.io/pcadvisor-data/requirements/`. It is separate from `apps.json` /
`manifest.json`, which keep working exactly as before.

## Rules in one sentence each
1. Only values printed on a page **owned by the publisher** (adobe.com, autodesk.com …).
2. A value the page does not give is **never guessed**, never `0`, never `""`: it is `missing` with a reason.
3. Every record says **which version** the page is about (or `null` if the page names none) and **when** it was checked.
4. App-made estimates ("heavy use", display tiers, confidence) are **not** stored here. The app may compute
   them later, but it must label them as its own estimate.

## File layout
```json
{
  "format": "pcadvisor-requirements",
  "schema_version": 1,
  "generated_on": "2026-10-23",
  "records": [ ... ]
}
```

## One record
| Field | Meaning |
|---|---|
| `id` | Same id as the app catalogue (`baseline/apps.v1.json`, e.g. `premiere`). Ids are never renamed. A new app gets a new id; an old id is never reused for another app. The validator warns if an id is not in the app catalogue. |
| `name` | Name as the publisher writes it. |
| `publisher` | `{ "name": "Adobe", "domains": ["adobe.com"] }`. Every source URL must be on one of these domains (sub-domains such as `helpx.adobe.com` are fine). |
| `applies_to` | `{ "version": "25.x" or null, "edition": "Community" or null }` — exactly as the official page names it. |
| `status` | See the table below. |
| `checked_on` | Date (YYYY-MM-DD) the record was last checked against the source. |
| `sources` | List of `{ "url", "title", "retrieved_on" }`. https only, no tracking/affiliate parameters (`utm_…`, `ref`, `tag`, `aff` …). |
| `platforms` | Object keyed by `windows`, `macos`, `linux`, `web`. Only platforms the page covers. Each has `minimum` and `recommended`. |
| `notes` | List of `{ "kind", "text" }`. `kind` = `quote` (words from the page), `normalized` (how a value was turned into a number, e.g. "8 GB of RAM" → `8`), `maintainer` (our remark, not from the page). |

### Status
| `status` | When | What the validator requires |
|---|---|---|
| `verified` | Every field was checked against the official page. | ≥1 source, ≥1 platform, no field `not_verified` or `blocked`. |
| `partially_verified` | Some fields checked, others not yet. | ≥1 source, ≥1 platform, ≥1 real value. |
| `no_official_spec` | The publisher publishes no requirements. | No values at all; fields are `not_specified` / `not_applicable`. Sources may be empty. |
| `discontinued` | The product is no longer sold/supported (official announcement). Values, if any, come from its last official page. | ≥1 source (the announcement). Platforms may be empty. |
| `verification_blocked` | The official page could not be opened. | The page tried is listed in `sources`; no values; every field `blocked`. |

### Each requirement field
Every level (`minimum`, `recommended`) must list **all 8 fields**, so a reader always knows why
something is empty:

`os`, `cpu` (text as written, e.g. "Intel 6th Gen or newer"), `cpu_cores`, `ram_gb`, `gpu` (text),
`vram_gb`, `storage_gb` (install space), `display` (text, e.g. "1920x1080").

A field is **either**
- `{ "value": 8 }` — optionally `{ "value": 8, "quote": "8 GB of RAM" }`
- `{ "missing": "<reason>" }` with reason:

| reason | meaning |
|---|---|
| `not_specified` | The official page does not give this. |
| `not_verified` | Nobody has checked this on the page yet. |
| `blocked` | The page could not be opened. |
| `not_applicable` | Does not apply (e.g. GPU memory for a web app). |

Numbers must be greater than 0. `recommended` can never be lower than `minimum`.

## Check the file
From the `pcadvisor-data` folder:
```
python tools/validate_requirements.py
```
It prints `ERROR [record_id] field.path: message` for each problem and exits with code 1 if there
is any error (0 when the file is clean).

Run the validator's own tests (standard Python, nothing to install):
```
python requirements/tests/test_validate_requirements.py
```
The examples in `requirements/tests/fixtures/` are **fictional** (example.com publishers) and only
test the format. The validator refuses example.com sources in the real `requirements.json`.

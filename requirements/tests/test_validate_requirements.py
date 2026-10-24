"""Tests for tools/validate_requirements.py (standard library only).

  python -m unittest discover -s requirements/tests -v

All example records are FICTIONAL (example.com publishers). They test the format, not real specs.
"""
import copy, datetime, json, pathlib, subprocess, sys, unittest

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import validate_requirements as vr  # noqa: E402

TODAY = datetime.date(2026, 10, 23)
FIXTURES = HERE / "fixtures"
SCRIPT = ROOT / "tools" / "validate_requirements.py"


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def errors_for(doc):
    return vr.validate(doc, today=TODAY, allow_examples=True).errors


class ValidExamplesTest(unittest.TestCase):

    def test_valid_fixture_has_no_errors(self):
        self.assertEqual([], errors_for(load("valid_examples.json")))

    def test_real_data_file_is_valid(self):
        doc = json.loads((ROOT / "requirements" / "requirements.json").read_text(encoding="utf-8"))
        rep = vr.validate(doc, known_ids=vr.load_known_ids(ROOT))
        self.assertEqual([], rep.errors)

    def test_cli_exits_zero_on_valid_file(self):
        res = subprocess.run([sys.executable, "-I", str(SCRIPT), str(FIXTURES / "valid_examples.json"),
                              "--allow-examples"], capture_output=True, text=True)
        self.assertEqual(0, res.returncode, res.stdout)


class InvalidFixtureTest(unittest.TestCase):

    def test_cli_exits_nonzero_and_names_record_and_field(self):
        res = subprocess.run([sys.executable, "-I", str(SCRIPT), str(FIXTURES / "invalid_examples.json"),
                              "--allow-examples"], capture_output=True, text=True)
        self.assertEqual(1, res.returncode)
        out = res.stdout
        self.assertIn("[bad_guessed_zero] platforms.windows.minimum.vram_gb", out)
        self.assertIn("[bad_third_party_source] sources[0].url: host some-review-blog.net", out)
        self.assertIn("tracking/affiliate parameter 'utm_source'", out)
        self.assertIn("[bad_heuristic_field] platforms.windows.recommended.heavy_ram_gb: unknown field", out)
        self.assertIn("[bad_heuristic_field] platforms.windows.minimum.ram_gb: status no_official_spec cannot carry values", out)

    def test_cli_fails_on_unreadable_json(self):
        res = subprocess.run([sys.executable, "-I", str(SCRIPT), str(HERE / "does_not_exist.json")],
                             capture_output=True, text=True)
        self.assertEqual(1, res.returncode)
        self.assertIn("cannot read JSON", res.stdout)


class RuleTest(unittest.TestCase):
    """Each test breaks ONE rule on a copy of a valid record and checks the exact error."""

    def setUp(self):
        self.doc = load("valid_examples.json")
        self.rec = self.doc["records"][0]          # example_verified
        self.win = self.rec["platforms"]["windows"]

    def assertError(self, fragment):
        errs = errors_for(self.doc)
        self.assertTrue(any(fragment in e for e in errs), f"{fragment!r} not in {errs}")

    # file level
    def test_wrong_schema_version(self):
        self.doc["schema_version"] = 2
        self.assertError("[file] schema_version: must be 1")

    def test_wrong_format_name(self):
        self.doc["format"] = "apps"
        self.assertError("[file] format")

    def test_duplicate_id(self):
        self.doc["records"].append(copy.deepcopy(self.rec))
        self.assertError("[example_verified] id: duplicate id")

    # record keys and types
    def test_missing_required_key(self):
        del self.rec["checked_on"]
        self.assertError("[example_verified] checked_on: required field is missing")

    def test_unknown_record_key(self):
        self.rec["confidence"] = "HIGH"
        self.assertError("[example_verified] confidence: unknown field")

    def test_bad_id_format(self):
        self.rec["id"] = "Bad-ID"
        self.assertError("[Bad-ID] id: must be 1..40 chars")

    def test_bad_status(self):
        self.rec["status"] = "official"
        self.assertError("[example_verified] status: must be one of")

    def test_bad_date(self):
        self.rec["checked_on"] = "20/10/2026"
        self.assertError("checked_on: must be a date YYYY-MM-DD")

    def test_future_date(self):
        self.rec["checked_on"] = "2027-01-01"
        self.assertError("checked_on: 2027-01-01 is in the future")

    def test_retrieved_after_checked(self):
        self.rec["sources"][0]["retrieved_on"] = "2026-10-22"
        self.assertError("sources[0].retrieved_on: is later than the record's checked_on")

    def test_string_number_rejected(self):
        self.win["minimum"]["ram_gb"] = {"value": "8"}
        self.assertError("minimum.ram_gb: value must be int/float, got str")

    def test_bool_rejected(self):
        self.win["minimum"]["cpu_cores"] = {"value": True}
        self.assertError("minimum.cpu_cores: value must be int")

    # null / missing semantics
    def test_null_value_rejected(self):
        self.win["minimum"]["ram_gb"] = {"value": None}
        self.assertError('minimum.ram_gb: value is null: use {"missing"')

    def test_zero_instead_of_missing_rejected(self):
        self.win["minimum"]["vram_gb"] = {"value": 0}
        self.assertError("use missing instead of 0")

    def test_field_omitted_rejected(self):
        del self.win["recommended"]["display"]
        self.assertError("recommended.display: required")

    def test_unknown_missing_reason(self):
        self.win["minimum"]["display"] = {"missing": "unknown"}
        self.assertError("minimum.display: missing must be one of")

    def test_value_and_missing_together(self):
        self.win["minimum"]["ram_gb"] = {"value": 8, "missing": "not_specified"}
        self.assertError("cannot have both value and missing")

    def test_recommended_lower_than_minimum(self):
        self.win["recommended"]["ram_gb"] = {"value": 4}
        self.assertError("recommended.ram_gb: 4 is lower than minimum 8")

    def test_unknown_platform(self):
        self.rec["platforms"]["android"] = self.win
        self.assertError("platforms.android: unknown platform")

    # URLs and provenance
    def test_http_url_rejected(self):
        self.rec["sources"][0]["url"] = "http://help.example.com/editor"
        self.assertError("sources[0].url: must be an https URL")

    def test_affiliate_param_rejected(self):
        self.rec["sources"][0]["url"] = "https://help.example.com/editor?tag=abc"
        self.assertError("tracking/affiliate parameter 'tag'")

    def test_word_affinity_in_path_allowed(self):
        self.rec["sources"][0]["url"] = "https://help.example.com/affinity/requirements"
        self.assertEqual([], errors_for(self.doc))

    def test_example_domain_rejected_outside_fixtures(self):
        rep = vr.validate(self.doc, today=TODAY, allow_examples=False)
        self.assertTrue(any("example.com sources are only allowed in test fixtures" in e for e in rep.errors))

    def test_publisher_domain_enforced_for_real_hosts(self):
        self.rec["publisher"]["domains"] = ["adobe.com"]
        self.rec["sources"][0]["url"] = "https://www.techblog.net/adobe-requirements"
        rep = vr.validate(self.doc, today=TODAY, allow_examples=False)
        self.assertTrue(any("host www.techblog.net is not one of the publisher's domains" in e
                            for e in rep.errors), rep.errors)

    def test_publisher_subdomain_accepted(self):
        self.rec["publisher"]["domains"] = ["adobe.com"]
        self.rec["sources"][0]["url"] = "https://helpx.adobe.com/premiere-pro/system-requirements.html"
        rep = vr.validate(self.doc, today=TODAY, allow_examples=False)
        self.assertFalse(any("sources[0].url" in e and "[example_verified]" in e for e in rep.errors), rep.errors)

    # status invariants
    def test_verified_needs_source(self):
        self.rec["sources"] = []
        self.assertError("sources: status verified needs at least one official source")

    def test_verified_cannot_have_unchecked_fields(self):
        self.win["minimum"]["cpu"] = {"missing": "not_verified"}
        self.assertError("minimum.cpu: status verified cannot have a field marked not_verified")

    def test_partially_verified_needs_one_value(self):
        rec = self.doc["records"][1]               # example_partial
        rec["platforms"]["windows"]["minimum"]["os"] = {"missing": "not_verified"}
        rec["platforms"]["windows"]["minimum"]["ram_gb"] = {"missing": "not_verified"}
        self.assertError("[example_partial] platforms: status partially_verified needs at least one checked value")

    def test_blocked_cannot_carry_values(self):
        rec = self.doc["records"][3]               # example_blocked
        rec["platforms"] = copy.deepcopy({"windows": self.win})
        self.assertError("[example_blocked] platforms.windows.minimum.ram_gb: status verification_blocked cannot carry values")

    def test_blocked_must_list_attempted_page(self):
        self.doc["records"][3]["sources"] = []
        self.assertError("[example_blocked] sources: status verification_blocked must list the page")

    def test_no_spec_cannot_use_not_verified(self):
        rec = self.doc["records"][2]               # example_no_spec
        rec["platforms"]["web"]["minimum"]["ram_gb"] = {"missing": "not_verified"}
        self.assertError("[example_no_spec] platforms.web.minimum.ram_gb: status no_official_spec")

    def test_discontinued_may_have_no_platforms(self):
        self.rec["status"] = "discontinued"
        self.rec["platforms"] = {}
        self.assertEqual([], errors_for(self.doc))

    def test_discontinued_needs_announcement_source(self):
        self.rec["status"] = "discontinued"
        self.rec["sources"] = []
        self.assertError("sources: status discontinued needs at least one official source")

    def test_bad_note_kind(self):
        self.rec["notes"] = [{"kind": "guess", "text": "probably 32 GB"}]
        self.assertError("notes[0].kind: must be one of")


if __name__ == "__main__":
    unittest.main()

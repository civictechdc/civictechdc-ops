"""Local regression tests, not evidence of live API compatibility."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "luma.sh"
DUMMY = "offline-dummy-key-not-a-credential"


class LumaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="luma-offline-")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.log = self.directory / "calls.jsonl"
        mock = self.directory / "curl"
        shutil.copyfile(ROOT / "tests" / "mock_curl.py", mock)
        mock.chmod(0o700)
        # No inherited credentials, proxy, curl config, BASH_ENV or test PATH.
        self.env = {
            "PATH": f"{self.directory}:/usr/bin:/bin",
            "LC_ALL": "C", "HOME": str(self.directory), "MOCK_LOG": str(self.log),
        }

    def run_cli(self, *args, live=False, scenario="ok", extra=None, trace=False):
        env = self.env | {"MOCK_SCENARIO": scenario}
        if live:
            env |= {"LUMA_ENABLE_READS": "1", "LUMA_API_KEY": DUMMY}
        env |= extra or {}
        argv = ["/bin/bash"] + (["-x"] if trace else []) + [str(SCRIPT), *args]
        result = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=5)
        self.assertNotIn(DUMMY, result.stdout + result.stderr)
        self.assertNotIn("NEVER_PRINT_BODY", result.stdout + result.stderr)
        self.assertNotIn("private@example.invalid", result.stdout + result.stderr)
        return result

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def test_default_is_dry_run_without_key(self):
        result = self.run_cli("calendar")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout),
                         {"dry_run": True, "method": "GET",
                          "url": "https://public-api.luma.com/v1/calendars/get"})
        self.assertEqual(self.calls(), [])

    def test_help_without_key_and_extra_args_rejected(self):
        self.assertEqual(self.run_cli("--help").returncode, 0)
        for args in [("calendar", "extra"), ("event",), ("events", "a", "b", "c")]:
            with self.subTest(args=args):
                self.assertNotEqual(self.run_cli(*args).returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_writes_and_pii_endpoints_absent(self):
        for command in ["create_event", "add_guest", "add_host", "guests", "guests_csv",
                        "webhooks", "self", "resolve_event", "POST"]:
            with self.subTest(command=command):
                result = self.run_cli("--live", command, live=True)
                self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_live_requires_both_explicit_gates_and_key(self):
        self.assertNotEqual(self.run_cli("--live", "calendar",
                                        extra={"LUMA_API_KEY": DUMMY}).returncode, 0)
        self.assertNotEqual(self.run_cli("--live", "calendar",
                                        extra={"LUMA_ENABLE_READS": "1"}).returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_dry_run_stays_offline_even_if_key_and_gate_exist(self):
        result = self.run_cli("event", "evt-offline", live=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["dry_run"])
        self.assertEqual(self.calls(), [])

    def test_url_parsing_is_local_even_with_live_flag(self):
        inputs = ["plain-slug", "https://lu.ma/plain-slug", "lu.ma/plain-slug",
                  "https://luma.com/plain-slug?tracking=x#part", "luma.com/plain-slug/",
                  "https://lu.ma/plain-slug/?tracking=x"]
        for value in inputs:
            with self.subTest(value=value):
                result = self.run_cli("--live", "slug", value)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "plain-slug\n")
        self.assertEqual(self.calls(), [])

    def test_malicious_url_hosts_paths_and_schemes_rejected(self):
        for value in ["https://lu.ma.evil.invalid/a", "https://evil.invalid/lu.ma/a",
                      "https://user@lu.ma/a", "http://lu.ma/a", "https://lu.ma/a/b",
                      "https://lu.ma/", "slug&other=value", "https://lu.ma/a%0d%0aX"]:
            with self.subTest(value=value):
                self.assertNotEqual(self.run_cli("slug", value).returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_invalid_event_ids_and_dates_rejected(self):
        for value in ["evt-a&secret=x", "https://lu.ma/slug", "../event", "evt-"]:
            self.assertNotEqual(self.run_cli("event", value).returncode, 0)
        for value in ["2030-02-30T12:00:00Z", "2030-01-01", "2030-01-01T00:00:00+00:00"]:
            self.assertNotEqual(self.run_cli("events", value).returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_query_encoding_and_current_parameter_names(self):
        cursor = "opaque&event_id=other /+?#"
        result = self.run_cli("events", "2030-01-01T00:00:00Z", cursor)
        self.assertEqual(result.returncode, 0, result.stderr)
        url = urlsplit(json.loads(result.stdout)["url"])
        self.assertEqual(url.netloc, "public-api.luma.com")
        self.assertEqual(parse_qs(url.query), {
            "pagination_limit": ["50"], "sort_column": ["start_at"],
            "sort_direction": ["asc"], "after": ["2030-01-01T00:00:00Z"],
            "pagination_cursor": [cursor],
        })
        self.assertEqual(self.calls(), [])

    def test_mocked_calendar_header_stdin_and_key_scrubbing(self):
        result = self.run_cli("--live", "calendar", live=True, trace=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(set(json.loads(result.stdout)), {"name", "slug", "url"})
        calls = self.calls()
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0]["stdin_auth_ok"])
        for flag in ["secret_in_argv", "secret_in_environment", "key_environment_present"]:
            self.assertFalse(calls[0][flag])

    def test_mocked_event_strips_host_and_meeting_pii(self):
        result = self.run_cli("--live", "event", "evt-offline", live=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertNotIn("hosts", data)
        self.assertNotIn("meeting_url", data)
        self.assertEqual(data["guest_counts"],
                         {"approved": {"guests": 2, "tickets": 3},
                          "invited": {"guests": 1, "tickets": 0}})

    def test_mocked_events_are_one_page_not_infinite_pagination(self):
        result = self.run_cli("--live", "events", "2030-01-01T00:00:00Z", live=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertTrue(data["has_more"])
        self.assertEqual(data["next_cursor"], "cursor&= /+")
        self.assertEqual(len(self.calls()), 1)
        self.assertNotIn("submitted_by", data["entries"][0])

    def test_http_errors_redirects_and_rate_limits_do_not_retry_or_leak(self):
        for status in ["401", "429", "302", "503", "bad_status"]:
            with self.subTest(status=status):
                result = self.run_cli("--live", "calendar", live=True, scenario=status)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
        self.assertEqual(len(self.calls()), 5)

    def test_transport_and_schema_failures_are_generic(self):
        for scenario in ["transport_error", "bad_json", "wrong_schema"]:
            result = self.run_cli("--live", "calendar", live=True, scenario=scenario)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
        self.assertEqual(len(self.calls()), 3)

    def test_header_injection_rejected_before_curl(self):
        for value in ["bad\nX-Header: value", "bad\rvalue", "bad key", ""]:
            result = self.run_cli("--live", "calendar", live=True,
                                  extra={"LUMA_API_KEY": value})
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn(value or "nonexistent", result.stdout + result.stderr)
        self.assertEqual(self.calls(), [])

    def test_templates_are_private_nonpublishable_drafts(self):
        files = list((ROOT / "event-templates").glob("*.json"))
        self.assertEqual(len(files), 5)
        for path in files:
            draft = json.loads(path.read_text())
            self.assertEqual(draft["start_at"], "REPLACE_START_UTC")
            self.assertEqual(draft["end_at"], "REPLACE_END_UTC")
            self.assertEqual(draft["geo_address_json"]["place_id"], "REPLACE_PLACE_ID")
            self.assertEqual(draft["visibility"], "private")
            self.assertFalse(draft["show_guest_list"])
            self.assertTrue(draft["reminders_disabled"])
            self.assertEqual(draft["_template_notes"]["status"], "draft_requires_owner_review")
            self.assertNotIn("2026", path.read_text())


if __name__ == "__main__":
    host_namespace = os.environ.get("LUMA_TEST_HOST_NET")
    if not host_namespace or os.readlink("/proc/self/ns/net") == host_namespace:
        raise SystemExit("Run through run-offline.sh; host-network tests are forbidden.")
    unittest.main(verbosity=2)

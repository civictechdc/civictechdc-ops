#!/usr/bin/python3
"""Network-free curl replacement. Never forwards anything to real curl."""
import json
import os
import sys

DUMMY = "offline-dummy-key-not-a-credential"
args = sys.argv[1:]
header = sys.stdin.read()
record = {
    "args": args,
    "stdin_auth_ok": header == f"x-luma-api-key: {DUMMY}\n",
    "secret_in_argv": any(DUMMY in a for a in args),
    "secret_in_environment": any(DUMMY in v for v in os.environ.values()),
    "key_environment_present": "LUMA_API_KEY" in os.environ,
}
with open(os.environ["MOCK_LOG"], "a", encoding="utf-8") as stream:
    stream.write(json.dumps(record) + "\n")
expected_prefix = [
    "-q", "--silent", "--proto", "=https", "--request", "GET", "--header", "@-",
    "--header", "Accept: application/json", "--connect-timeout", "5",
    "--max-time", "20", "--max-filesize", "1048576",
    "--write-out", "\n%{http_code}", "--url",
]
if (args[:-1] != expected_prefix or not record["stdin_auth_ok"]
        or record["secret_in_argv"] or record["secret_in_environment"]
        or record["key_environment_present"]):
    sys.exit(91)
url = args[-1]
if not url.startswith("https://public-api.luma.com/v1/"):
    sys.exit(92)
scenario = os.environ.get("MOCK_SCENARIO", "ok")
if scenario == "transport_error":
    sys.stderr.write("NEVER_PRINT_BODY")
    sys.exit(7)
if scenario in {"401", "429", "302", "503", "bad_status"}:
    print('{"error":"NEVER_PRINT_BODY","email":"private@example.invalid"}')
    print("garbage" if scenario == "bad_status" else scenario, end="")
    sys.exit(0)
if scenario == "bad_json":
    print("NEVER_PRINT_BODY\n200", end="")
    sys.exit(0)
if scenario == "wrong_schema":
    print('{"error":"NEVER_PRINT_BODY"}\n200', end="")
    sys.exit(0)

event = {
    "id": "evt-offline", "name": "Offline fixture", "start_at": "2030-01-01T23:00:00Z",
    "end_at": "2030-01-02T01:00:00Z", "timezone": "America/New_York",
    "url": "https://luma.com/offline-fixture", "visibility": "private",
    "max_capacity": 40,
    "hosts": [{"email": "private@example.invalid"}],
    "submitted_by": {"email": "private@example.invalid"},
    "meeting_url": "https://example.invalid/PRIVATE_MEETING",
    "guest_counts": {
        "approved": {"guests": 2, "tickets": 3, "email": "private@example.invalid"},
        "invited": {"guests": 1, "tickets": 0},
        "unknown": {"email": "private@example.invalid"},
    },
}
if url.endswith("/v1/calendars/get"):
    body = {"name": "Offline calendar", "slug": "offline", "url": "https://luma.com/offline",
            "description": "private@example.invalid"}
elif "/v1/calendars/events/list?" in url:
    body = {"entries": [event], "has_more": True, "next_cursor": "cursor&= /+"}
elif "/v1/events/get?event_id=evt-" in url:
    body = event
else:
    # In particular, a mistaken lookup/guest/write endpoint fails closed.
    sys.exit(93)
print(json.dumps(body))
print("200", end="")

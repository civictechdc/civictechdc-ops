"""Synthetic, SDK-free offline tests. Invoke only through run-offline.sh."""

import copy
from dataclasses import replace
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import sqlite3
import stat
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True

host_net = os.environ.get("BRIDGE_TEST_HOST_NET")
if not host_net or os.readlink("/proc/self/ns/net") == host_net:
    raise SystemExit("isolated network namespace required")


def network_forbidden(*args, **kwargs):
    raise AssertionError("network forbidden in offline tests")


# Defense in depth: not even a loopback fixture server is permitted.
socket.socket.connect = network_forbidden
socket.socket.connect_ex = network_forbidden
socket.create_connection = network_forbidden
socket.getaddrinfo = network_forbidden

SOURCE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "test_approval_bridge", SOURCE / "__init__.py",
    submodule_search_locations=[str(SOURCE)])
package = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = package
spec.loader.exec_module(package)
from test_approval_bridge.config import Config, Refused
from test_approval_bridge.core import Bridge, Gate, RateLimited
from test_approval_bridge.paperclip import Issue, Paperclip
from test_approval_bridge.store import Store

entry_spec = importlib.util.spec_from_file_location("bridge_entry_test", SOURCE / "slack_bridge.py")
entry = importlib.util.module_from_spec(entry_spec)
entry_spec.loader.exec_module(entry)

ISSUE_ID = "00000000-0000-4000-8000-000000000002"
THREAD = "1700000000.000001"
SENTINEL = "SYNTHETIC_REQUEST_SENTINEL_NOT_FOR_SLACK_OUTPUT"


def config_data(directory):
    return {
        "workspace_id": "TTEST01", "app_id": "ATEST01",
        "bot_user_id": "UTESTBOT", "bot_id": "BTEST01",
        "channel_id": "CTEST01", "allowed_user_ids": ["UTESTHUMAN"],
        "company_id": "00000000-0000-4000-8000-000000000001",
        "company_prefix": "TEST", "paperclip_api_url": "http://127.0.0.1:12345/api",
        "paperclip_public_url": "https://paperclip.example.invalid",
        "state_path": str(Path(directory) / "state.sqlite"),
        "poll_interval_seconds": 60, "integration_approved": True,
    }


def payload(event_id="event-1", thread=None, text=SENTINEL):
    event = {"type": "app_mention", "channel": "CTEST01", "user": "UTESTHUMAN",
             "ts": THREAD, "text": "<@UTESTBOT> " + text}
    if thread is not None:
        event["thread_ts"] = thread
    return {
        "type": "event_callback", "team_id": "TTEST01", "api_app_id": "ATEST01",
        "event_id": event_id, "event": event,
        "authorizations": [{"team_id": "TTEST01", "user_id": "UTESTBOT", "is_bot": True}],
    }


class Crash(BaseException):
    pass


class Slack:
    def __init__(self):
        self.auth = {"ok": True, "team_id": "TTEST01", "user_id": "UTESTBOT",
                     "bot_id": "BTEST01"}
        self.channel = {
            "id": "CTEST01", "is_private": True, "is_member": True,
            "is_archived": False, "is_shared": False,
            "is_ext_shared": False, "is_org_shared": False,
        }
        self.pages = {"": {"ok": True, "members": ["UTESTHUMAN", "UTESTBOT"],
                           "response_metadata": {"next_cursor": ""}}}
        self.sent = []
        self.send_error = None
        self.member_calls = []

    def auth_test(self):
        return copy.deepcopy(self.auth)

    def conversations_info(self, **kwargs):
        assert kwargs == {"channel": "CTEST01"}
        return {"ok": True, "channel": copy.deepcopy(self.channel)}

    def conversations_members(self, **kwargs):
        assert kwargs["channel"] == "CTEST01" and kwargs["limit"] == 200
        self.member_calls.append(kwargs["cursor"])
        result = self.pages[kwargs["cursor"]]
        if isinstance(result, BaseException):
            raise result
        return copy.deepcopy(result)

    def chat_postMessage(self, **kwargs):
        self.sent.append(kwargs)
        if self.send_error is not None:
            raise self.send_error
        return {"ok": True, "channel": "CTEST01", "ts": "1700000001.000001"}


class PaperclipFake:
    def __init__(self):
        self.created = []
        self.error = None
        self.safety_error = None
        self.current_status = "backlog"
        self.status_calls = []

    def check_safe(self):
        if self.safety_error is not None:
            raise self.safety_error

    def create_proposal(self, text, thread):
        self.created.append((text, thread))
        if self.error is not None:
            raise self.error
        return Issue(ISSUE_ID, "TEST-1")

    def status(self, issue_id):
        assert issue_id == ISSUE_ID
        self.status_calls.append(issue_id)
        return self.current_status

    def issue_url(self, identifier):
        assert identifier == "TEST-1"
        return "https://paperclip.example.invalid/TEST/issues/TEST-1"


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = Config.parse(config_data(self.temp.name))
        self.store = Store(self.config.state_path)
        self.slack = Slack()
        self.paperclip = PaperclipFake()
        self.bridge = Bridge(self.config, self.store, self.slack, self.paperclip, clock=lambda: 100)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def queue(self, event_id="event-1", text=SENTINEL):
        self.bridge.accept("envelope-" + event_id, payload(event_id, text=text))

    def create(self):
        self.queue()
        self.assertTrue(self.bridge.work_once())
        self.assertEqual(self.store.proposal(THREAD)["state"], "created")

    def test_syntactic_gate_is_mention_only_and_binds_identity(self):
        cases = []
        for key, value in (("type", "message"), ("type", "message.im"),
                           ("channel", "CTESTOTHER"), ("user", "UTESTOTHER"),
                           ("user", "UTESTBOT"), ("subtype", "file_share"),
                           ("bot_id", "BTESTOTHER"), ("bot_profile", {}),
                           ("text", "not an explicit mention"),
                           ("text", "<@UTESTBOT> " + "x" * 4096),
                           ("channel_type", "im")):
            p = payload()
            p["event"][key] = value
            cases.append(p)
        for key, value in (("team_id", "TTESTOTHER"), ("api_app_id", "ATESTOTHER"),
                           ("authorizations", [])):
            p = payload()
            p[key] = value
            cases.append(p)
        p = payload()
        p["authorizations"][0]["user_id"] = "UTESTOTHER"
        cases.append(p)
        for p in cases:
            self.bridge.accept("envelope-rejected", p)
        self.assertIsNone(self.store.pending_event())
        self.assertEqual(self.paperclip.created, [])
        self.assertEqual(self.slack.sent, [])
        self.assertEqual(self.slack.member_calls, [])

    def test_identity_privacy_and_requester_membership_gate_fail_closed(self):
        for change in (
                lambda: self.slack.auth.update(team_id="TTESTOTHER"),
                lambda: self.slack.auth.update(user_id="UTESTOTHER"),
                lambda: self.slack.auth.update(bot_id="BTESTOTHER"),
                lambda: self.slack.channel.update(is_private=False),
                lambda: self.slack.channel.update(is_archived=True),
                lambda: self.slack.channel.update(is_member=False),
                lambda: self.slack.channel.pop("is_shared"),
                lambda: self.slack.pages[""].update(members=["UTESTBOT"])):
            self.slack = Slack()
            change()
            with self.assertRaises(Refused):
                Gate(self.config, self.slack).check("UTESTHUMAN")
        self.slack = Slack()
        with self.assertRaises(Refused):
            Gate(self.config, self.slack).check("UTESTOTHER")

    def test_paginated_membership_never_accepts_a_partial_first_page(self):
        for second in (
                {"ok": True, "members": ["UTESTOTHER"],
                 "response_metadata": {"next_cursor": ""}},
                {"ok": True, "members": ["UTESTBOT"]},
                TimeoutError("synthetic private error not logged")):
            self.slack.pages = {
                "": {"ok": True, "members": ["UTESTHUMAN"],
                     "response_metadata": {"next_cursor": "page-2"}},
                "page-2": second,
            }
            with self.assertRaises(Refused):
                self.bridge.gate.check("UTESTHUMAN")
        self.queue()
        self.bridge.work_once()
        self.assertEqual(self.paperclip.created, [])
        self.assertEqual(self.slack.sent, [])
        self.assertEqual(self.store.proposal(THREAD)["state"], "rejected")
        self.assertIsNone(self.store.proposal(THREAD)["text"])

    def test_two_page_membership_success_checks_every_page(self):
        self.slack.pages = {
            "": {"ok": True, "members": ["UTESTHUMAN"],
                 "response_metadata": {"next_cursor": "page-2"}},
            "page-2": {"ok": True, "members": ["UTESTBOT"],
                       "response_metadata": {"next_cursor": ""}},
        }
        self.bridge.gate.check("UTESTHUMAN")
        self.assertEqual(self.slack.member_calls, ["", "page-2"])

    def test_optional_is_member_requires_complete_bot_membership_proof(self):
        del self.slack.channel["is_member"]
        self.bridge.gate.check("UTESTHUMAN")
        self.slack.pages[""]["members"] = ["UTESTHUMAN"]
        with self.assertRaises(Refused):
            self.bridge.gate.check("UTESTHUMAN")

    def test_envelope_ack_is_after_durable_intake_and_database_failure_is_not_acked(self):
        acknowledgements = []

        def ack(response):
            with sqlite3.connect(self.config.state_path) as connection:
                self.assertEqual(connection.execute("SELECT count(*) FROM events").fetchone()[0], 1)
            acknowledgements.append(response.envelope_id)

        request = SimpleNamespace(type="events_api", envelope_id="env-ack", payload=payload())
        client = SimpleNamespace(send_socket_mode_response=ack)
        entry.dispatch(client, request, self.bridge.accept, SimpleNamespace)
        self.assertEqual(acknowledgements, ["env-ack"])
        with patch.object(self.store, "accept", side_effect=sqlite3.OperationalError(SENTINEL)), \
                patch("sys.stderr", new_callable=io.StringIO) as error:
            entry.dispatch(client, request, self.bridge.accept, SimpleNamespace)
        self.assertEqual(acknowledgements, ["env-ack"])
        self.assertNotIn(SENTINEL, error.getvalue())

    def test_envelope_event_and_thread_dedupe_do_not_forward_followup_content(self):
        p = payload()
        self.bridge.accept("env-1", p)
        self.bridge.accept("env-1", p)
        self.bridge.accept("env-replay", p)
        self.bridge.work_once()
        self.bridge.accept("env-followup", payload("event-2", THREAD, "NEW_UNREVIEWED_TEXT"))
        self.bridge.work_once()
        self.assertEqual(len(self.paperclip.created), 1)
        self.assertEqual(len(self.slack.sent), 2)
        self.assertIn("already has a proposal", self.slack.sent[1]["text"])
        self.assertNotIn("NEW_UNREVIEWED_TEXT", str(self.paperclip.created))
        self.assertNotIn("NEW_UNREVIEWED_TEXT", Path(self.config.state_path).read_bytes().decode(
            "utf-8", errors="ignore"))
        self.assertIsNone(self.store.pending_event())

    def test_text_is_cleared_after_creation_and_not_echoed_to_slack(self):
        self.create()
        self.assertIsNone(self.store.proposal(THREAD)["text"])
        self.assertNotIn(SENTINEL.encode(), Path(self.config.state_path).read_bytes())
        message = self.slack.sent[0]
        self.assertNotIn(SENTINEL, message["text"])
        self.assertFalse(message["mrkdwn"])
        self.assertFalse(message["unfurl_links"])
        self.assertFalse(message["unfurl_media"])
        self.assertEqual(message["thread_ts"], THREAD)

    def test_creation_crash_and_ambiguous_outcome_are_never_retried(self):
        for index, error in enumerate((TimeoutError(SENTINEL), Crash())):
            # Separate threads reserve independent proposals for each scenario.
            thread = THREAD if isinstance(error, TimeoutError) else "1700000002.000001"
            p = payload("event-" + str(index))
            p["event"]["ts"] = thread
            self.bridge.accept("env-" + str(index), p)
            self.paperclip.error = error
            if isinstance(error, Crash):
                with self.assertRaises(Crash):
                    self.bridge.work_once()
                self.assertEqual(self.store.proposal(thread)["state"], "creating")
            else:
                self.bridge.work_once()
            self.store.recover()
            self.assertEqual(self.store.proposal(thread)["state"], "uncertain")
            self.assertIsNone(self.store.proposal(thread)["text"])
            count = len(self.paperclip.created)
            self.bridge.work_once()
            replay = payload("followup-" + str(index), thread)
            self.bridge.accept("replay-" + str(index), replay)
            self.bridge.work_once()
            self.assertEqual(len(self.paperclip.created), count)
        self.assertEqual(self.slack.sent, [])

    def test_pretransport_creating_receipt_survives_restart_without_post(self):
        self.queue()
        self.store.begin_create(THREAD)
        self.store.close()
        self.store = Store(self.config.state_path)
        self.store.recover()
        self.bridge = Bridge(self.config, self.store, self.slack, self.paperclip)
        self.bridge.work_once()
        self.assertEqual(self.paperclip.created, [])
        self.assertEqual(self.store.proposal(THREAD)["state"], "uncertain")

    def test_slack_crash_receipt_and_ambiguous_send_are_never_retried(self):
        self.slack.send_error = Crash()
        self.queue()
        with self.assertRaises(Crash):
            self.bridge.work_once()
        self.store.recover()
        self.slack.send_error = None
        self.bridge.work_once()
        self.assertEqual(len(self.slack.sent), 1)
        receipt = self.store.db.execute("SELECT state FROM deliveries").fetchone()[0]
        self.assertEqual(receipt, "uncertain")
        # Later status transport can also be ambiguous, but not blindly retried.
        self.paperclip.current_status = "done"
        self.slack.send_error = TimeoutError(SENTINEL)
        self.bridge.poll_statuses()
        self.store.recover()
        self.slack.send_error = None
        self.bridge.poll_statuses()
        self.assertEqual(len(self.slack.sent), 2)

    def test_rate_limited_creation_is_terminal_with_saved_delay(self):
        self.paperclip.error = RateLimited(45)
        self.queue()
        self.bridge.work_once()
        p = self.store.proposal(THREAD)
        self.assertEqual((p["state"], p["retry_after"]), ("rate_limited", 45))
        self.bridge.work_once()
        self.assertEqual(len(self.paperclip.created), 1)

    def test_slack_definite_rate_limit_records_delay_without_retry(self):
        error = RuntimeError(SENTINEL)
        error.response = SimpleNamespace(status_code=429, headers={"Retry-After": "41"})
        self.slack.send_error = error
        self.create()
        self.store.recover()
        self.bridge.work_once()
        receipt = self.store.db.execute("SELECT state,retry_after FROM deliveries").fetchone()
        self.assertEqual(tuple(receipt), ("rate_limited", 41))
        self.assertEqual(len(self.slack.sent), 1)

    def test_status_publications_are_fixed_and_have_durable_receipts(self):
        self.create()
        for status in ("backlog", "todo", "in_progress", "in_review", "blocked", "done", "cancelled"):
            self.paperclip.current_status = status
            self.bridge.poll_statuses()
            self.bridge.poll_statuses()
        # Terminal completion stops future polling, including later transitions.
        self.assertEqual(len(self.slack.sent), 4)
        for message in self.slack.sent[1:]:
            self.assertRegex(
                message["text"], r"^Proposal status: (in_review|done|blocked|cancelled)\. "
                r"https://paperclip\.example\.invalid/TEST/issues/TEST-1$")

    def test_unchanged_statuses_use_one_batch_snapshot_and_no_repeat_send_gate(self):
        for index in range(3):
            p = payload("event-" + str(index))
            p["event"]["ts"] = f"170000000{index}.000001"
            self.bridge.accept("env-" + str(index), p)
            self.bridge.work_once()
        self.slack.member_calls.clear()
        self.paperclip.current_status = "in_review"
        self.bridge.poll_statuses()
        self.assertEqual(len(self.slack.member_calls), 4)  # Batch + 3 actual publications.
        self.assertEqual(len(self.slack.sent), 6)
        self.bridge.poll_statuses()
        self.assertEqual(len(self.slack.member_calls), 5)  # Only one new batch snapshot.
        self.assertEqual(len(self.slack.sent), 6)
        self.assertEqual(len(self.paperclip.status_calls), 6)

    def test_publication_rechecks_revocation_after_batch_snapshot(self):
        self.create()

        def status_after_membership_changed(issue_id):
            self.slack.pages[""]["members"].append("UTESTOTHER")
            return "in_review"

        with patch.object(self.paperclip, "status", side_effect=status_after_membership_changed):
            self.bridge.poll_statuses()
        self.assertEqual(len(self.slack.sent), 1)  # Initial acknowledgement only.
        self.assertFalse(self.store.has_delivery("status:" + THREAD + ":in_review"))

    def test_bounded_poll_batches_retire_closed_tasks_but_preserve_thread_references(self):
        for index in range(12):
            p = payload("event-" + str(index))
            p["event"]["ts"] = f"{1700000000 + index}.000001"
            self.bridge.accept("env-" + str(index), p)
            self.bridge.work_once()
        self.slack.member_calls.clear()
        self.paperclip.current_status = "cancelled"
        self.bridge.poll_statuses()
        self.assertEqual(len(self.paperclip.status_calls), 10)  # Fixed batch bound.
        self.bridge.poll_statuses()
        self.assertEqual(len(self.paperclip.status_calls), 12)
        spent_calls = len(self.slack.member_calls)
        for _ in range(3):
            self.bridge.poll_statuses()
        self.assertEqual(len(self.slack.member_calls), spent_calls)
        self.assertEqual(len(self.paperclip.status_calls), 12)
        self.assertEqual(self.store.db.execute(
            "SELECT count(*) FROM proposals WHERE polling=0").fetchone()[0], 12)
        self.bridge.accept("env-reference", payload("event-reference", THREAD, "NOT_FOR_TASK"))
        self.bridge.work_once()
        self.assertEqual(len(self.paperclip.created), 12)
        self.assertIn("already has a proposal", self.slack.sent[-1]["text"])
        self.assertNotIn("NOT_FOR_TASK", str(self.paperclip.created))

    def test_terminal_send_crash_stops_polling_durably_without_losing_reference(self):
        self.create()
        self.paperclip.current_status = "done"
        self.slack.send_error = Crash()
        with self.assertRaises(Crash):
            self.bridge.poll_statuses()
        self.store.close()
        self.store = Store(self.config.state_path)
        self.store.recover()
        self.bridge = Bridge(self.config, self.store, self.slack, self.paperclip, clock=lambda: 100)
        self.slack.send_error = None
        self.slack.member_calls.clear()
        self.bridge.poll_statuses()
        self.assertEqual(self.slack.member_calls, [])
        self.assertEqual(len(self.paperclip.status_calls), 1)
        self.assertEqual(self.store.db.execute(
            "SELECT state FROM deliveries WHERE id LIKE 'status:%'").fetchone()[0], "uncertain")
        self.bridge.accept("env-reference", payload("event-reference", THREAD))
        self.bridge.work_once()
        self.assertIn("already has a proposal", self.slack.sent[-1]["text"])

    def test_expiry_sweep_erases_all_eligible_pending_text_before_fifo_processing(self):
        self.queue()
        second = payload("event-second")
        second["event"]["ts"] = "1700000002.000001"
        self.bridge.accept("env-second", second)
        self.bridge.clock = lambda: 3700
        self.bridge.work_once()
        self.assertEqual(self.store.proposal(second["event"]["ts"])["state"], "rejected")
        self.assertIsNone(self.store.proposal(second["event"]["ts"])["text"])
        self.assertIsNotNone(self.store.pending_event())  # Second event was not processed yet.
        self.assertEqual(self.slack.member_calls, [])
        self.assertEqual(self.paperclip.created, [])

    def test_poll_sweep_expires_pending_text_even_with_no_tracked_tasks(self):
        self.queue()
        self.bridge.clock = lambda: 3700
        self.bridge.poll_statuses()
        self.assertEqual(self.store.proposal(THREAD)["state"], "rejected")
        self.assertIsNone(self.store.proposal(THREAD)["text"])
        self.assertEqual(self.slack.member_calls, [])

    def test_membership_is_rechecked_before_followups_and_status_publication(self):
        self.create()
        self.slack.pages[""]["members"].append("UTESTOTHER")
        self.queue("event-2")
        self.bridge.work_once()
        self.paperclip.current_status = "done"
        self.bridge.poll_statuses()
        self.assertEqual(len(self.slack.sent), 1)
        self.assertEqual(len(self.paperclip.created), 1)

    def test_expired_and_unsafe_proposals_are_rejected_and_text_erased(self):
        self.queue()
        self.paperclip.safety_error = Refused()
        self.bridge.work_once()
        self.assertEqual(self.store.proposal(THREAD)["state"], "rejected")
        self.assertIsNone(self.store.proposal(THREAD)["text"])
        p = payload("event-expired")
        p["event"]["ts"] = "1700000005.000001"
        self.bridge.accept("env-expired", p)
        self.bridge.clock = lambda: 4001
        self.bridge.work_once()
        self.assertEqual(self.store.proposal(p["event"]["ts"])["state"], "rejected")
        self.assertEqual(self.paperclip.created, [])

    def test_state_cannot_be_rebound_to_another_private_channel(self):
        with self.assertRaises(Refused):
            self.store.bind(replace(self.config, channel_id="CTESTOTHER"))


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = Config.parse(config_data(self.temp.name))
        self.client = Paperclip(self.config)
        self.calls = []

    def tearDown(self):
        self.temp.cleanup()

    def issue(self, **extra):
        return {"id": ISSUE_ID, "identifier": "TEST-1", "companyId": self.config.company_id,
                "status": "backlog", "visibility": "private",
                "assigneeAgentId": None, "assigneeUserId": None,
                "projectId": "00000000-0000-4000-8000-000000000003", **extra}

    def test_create_contract_has_private_backlog_null_assignments_and_stable_key(self):
        def request(method, path, body=None):
            self.calls.append((method, path, body))
            return self.issue()
        self.client._request = request
        self.client.create_proposal(SENTINEL, THREAD)
        self.client.create_proposal("different text", THREAD)
        _, path, body = self.calls[0]
        self.assertEqual(path, "/companies/" + self.config.company_id + "/issues")
        self.assertEqual(body["status"], "backlog")
        self.assertEqual(body["visibility"], "private")
        for key in ("assigneeAgentId", "assigneeUserId", "projectId",
                    "parentId", "executionPolicy", "watchdog"):
            self.assertIsNone(body[key])
        self.assertTrue(body["allowDuplicate"])
        self.assertEqual(body["idempotencyKey"], self.calls[1][2]["idempotencyKey"])
        self.assertLessEqual(len(body["idempotencyKey"]), 255)
        self.assertNotIn("run", body)
        self.assertNotIn("comment", body)

    def test_created_issue_requires_private_unassigned_backlog(self):
        for invalid in ({"status": "todo"}, {"visibility": "open"},
                        {"assigneeAgentId": ISSUE_ID}, {"assigneeUserId": "user-test"},
                        {"companyId": ISSUE_ID}, {"identifier": "TEST-1\n@everyone"}):
            self.client._request = lambda *args: self.issue(**invalid)
            with self.assertRaises(Refused):
                self.client.create_proposal(SENTINEL, THREAD)

    def test_guard_blocks_any_plugins_routines_heartbeat_or_malformed_data(self):
        company = "/companies/" + self.config.company_id
        valid = {"/plugins": [], company + "/routines": [],
                 company + "/agents": [{"runtimeConfig": {"heartbeat": {
                     "enabled": False, "intervalSec": 0}}}]}
        self.client._request = lambda method, path: valid[path]
        self.client.check_safe()
        for route, value in (
                ("/plugins", [{"id": "synthetic-plugin"}]),
                (company + "/routines", [{"id": "synthetic-routine"}]),
                (company + "/agents", [{}]),
                (company + "/agents", {"items": []}),
                (company + "/agents", [{"runtimeConfig": {"heartbeat": {
                    "enabled": True, "intervalSec": 60}}}])):
            invalid = {**valid, route: value}
            self.client._request = lambda method, path: invalid[path]
            with self.assertRaises(Refused):
                self.client.check_safe()

    def test_status_discards_worker_content_and_rejects_cross_company_issue(self):
        self.client._request = lambda *args: self.issue(
            status="done", description=SENTINEL, comments=[SENTINEL], draft=SENTINEL)
        self.assertEqual(self.client.status(ISSUE_ID), "done")
        self.assertNotIn(SENTINEL, self.client.issue_url("TEST-1"))
        self.client._request = lambda *args: self.issue(companyId=ISSUE_ID)
        with self.assertRaises(Refused):
            self.client.status(ISSUE_ID)

    def test_http_transport_never_redirects_or_uses_proxy_and_does_not_retry(self):
        with patch.object(self.client.http, "open", side_effect=TimeoutError(SENTINEL)) as send:
            with self.assertRaises(Refused) as error:
                self.client._request("POST", "/synthetic", {})
        self.assertEqual(send.call_count, 1)
        self.assertNotIn(SENTINEL, str(error.exception))
        redirect = next(h for h in self.client.http.handlers if h.__class__.__name__ == "NoRedirect")
        with self.assertRaises(Refused):
            redirect.redirect_request(None, None, 302, None, None, "https://example.invalid")


class EntrypointTests(unittest.TestCase):
    def test_root_managed_config_mode_and_effective_group_are_exact(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text("{}")
            for owner, group, mode, accepted in (
                    (0, 1001, 0o640, True), (0, 1002, 0o640, False),
                    (0, 1001, 0o644, False), (1001, 1001, 0o600, True),
                    (1001, 1001, 0o640, False), (0, 1001, 0o600, False)):
                info = SimpleNamespace(st_mode=stat.S_IFREG | mode, st_uid=owner,
                                       st_gid=group, st_nlink=1)
                with patch.object(entry.os, "geteuid", return_value=1001), \
                        patch.object(entry.os, "getegid", return_value=1001), \
                        patch.object(entry.os, "fstat", return_value=info):
                    if accepted:
                        os.close(entry.private_file(path, settings=True))
                    else:
                        with self.assertRaises(Exception):
                            entry.private_file(path, settings=True)
            with patch.object(entry.os, "geteuid", return_value=1001), \
                    patch.object(entry.os, "getegid", return_value=1001), \
                    patch.object(entry.os, "fstat", return_value=SimpleNamespace(
                        st_mode=stat.S_IFREG | 0o640, st_uid=0, st_gid=1001, st_nlink=1)):
                with self.assertRaises(Exception):
                    entry.private_file(path)  # Never accepted for state or lock.

    def test_invalid_configuration_and_unapproved_integration_refuse(self):
        with tempfile.TemporaryDirectory() as directory:
            valid = config_data(directory)
            for change in ({"integration_approved": False},
                           {"allowed_user_ids": ["UTESTBOT"]},
                           {"paperclip_api_url": "https://example.invalid/api"},
                           {"paperclip_public_url": "https://example.invalid/path"},
                           {"paperclip_public_url": "https://example.invalid\n@everyone"},
                           {"poll_interval_seconds": True}, {"unknown_setting": True}):
                with self.assertRaises(Refused):
                    Config.parse({**valid, **change})

    def test_check_is_read_only_and_sdk_http_retries_are_disabled(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps(config_data(directory)))
            path.chmod(0o600)
            sdk_calls = []
            slack = Slack()

            def web_client(**kwargs):
                sdk_calls.append(kwargs)
                return slack

            fake_modules = {
                "slack_sdk": SimpleNamespace(WebClient=web_client),
                "slack_sdk.socket_mode": SimpleNamespace(SocketModeClient=network_forbidden),
                "slack_sdk.socket_mode.response": SimpleNamespace(SocketModeResponse=SimpleNamespace),
            }
            with patch.dict(sys.modules, fake_modules), \
                    patch.dict(os.environ, {"SLACK_BOT_TOKEN": "xoxb-synthetic",
                                           "SLACK_APP_TOKEN": "xapp-synthetic"}, clear=True), \
                    patch.object(entry, "Paperclip", return_value=PaperclipFake()), \
                    patch.object(sys, "argv", ["slack_bridge.py", "check", "--config", str(path)]), \
                    patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(entry.main(), 0)
            self.assertEqual(sdk_calls[0]["retry_handlers"], [])
            self.assertEqual(sorted(p.name for p in Path(directory).iterdir()), ["config.json"])

    def test_network_is_structurally_blocked(self):
        self.assertNotEqual(os.readlink("/proc/self/ns/net"), host_net)
        with self.assertRaises(AssertionError):
            socket.create_connection(("example.invalid", 443))


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as home:
        os.environ["HOME"] = home
        os.environ["XDG_CACHE_HOME"] = home
        unittest.main(verbosity=2)

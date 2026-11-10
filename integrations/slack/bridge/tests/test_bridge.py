"""Synthetic, SDK-free offline tests. Invoke only through run-offline.sh."""

import copy
from dataclasses import replace
import hashlib
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
from test_approval_bridge.core import CHAT_UNAVAILABLE, DRAFT_SUFFIX
from test_approval_bridge.coordinator import Coordinator, CoordinatorError, validate_request
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


class CoordinatorFake:
    def __init__(self):
        self.calls = []
        self.reply = "Synthetic coordinator advice."
        self.error = None
        self.during_query = None

    def query(self, text, history):
        validate_request(text, history)
        self.calls.append((text, copy.deepcopy(history)))
        if self.during_query is not None:
            self.during_query()
        if self.error is not None:
            raise self.error
        return self.reply


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


class ChannelMembershipTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = Config.parse({
            **config_data(self.temp.name), "access_mode": "channel_members", "allowed_user_ids": [],
        })
        self.store = Store(self.config.state_path)
        self.slack = Slack()
        self.paperclip = PaperclipFake()
        self.bridge = Bridge(self.config, self.store, self.slack, self.paperclip, clock=lambda: 100)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def queue(self, user="UTESTHUMAN", event_id="event-1", thread=THREAD):
        p = payload(event_id)
        p["event"].update(user=user, ts=thread)
        self.bridge.accept("env-" + event_id, p)

    def test_new_members_are_eligible_without_roster_config_changes_or_thread_append(self):
        self.queue()
        self.bridge.work_once()
        self.slack.pages[""]["members"].append("UTESTNEW")
        self.queue("UTESTNEW", "event-new", "1700000002.000001")
        self.bridge.work_once()
        self.assertEqual(len(self.paperclip.created), 2)
        self.assertEqual(self.config.allowed_user_ids, frozenset())
        self.queue("UTESTNEW", "event-reference")
        self.bridge.work_once()
        self.assertEqual(len(self.paperclip.created), 2)
        self.assertIn("already has a proposal", self.slack.sent[-1]["text"])
        self.store.bind(self.config)  # Live roster changes do not rebind policy.

    def test_callback_durably_queues_valid_ids_without_network_but_outsiders_are_rejected(self):
        with patch.object(self.slack, "auth_test", side_effect=network_forbidden), \
                patch.object(self.slack, "conversations_info", side_effect=network_forbidden), \
                patch.object(self.slack, "conversations_members", side_effect=network_forbidden):
            self.queue("UTESTOUTSIDER")
        self.assertIsNotNone(self.store.pending_event())
        self.bridge.work_once()
        self.assertEqual(self.paperclip.created, [])
        self.assertEqual(self.slack.sent, [])
        self.assertEqual(self.store.proposal(THREAD)["state"], "rejected")
        self.assertIsNone(self.store.proposal(THREAD)["text"])

    def test_members_leaving_after_intake_or_during_preflight_cannot_create(self):
        self.queue()
        self.slack.pages[""]["members"].remove("UTESTHUMAN")
        self.bridge.work_once()
        self.assertEqual(self.paperclip.created, [])
        self.slack.pages[""]["members"].append("UTESTHUMAN")
        self.queue(event_id="event-precreate", thread="1700000002.000001")
        with patch.object(self.paperclip, "check_safe", side_effect=lambda:
                          self.slack.pages[""]["members"].remove("UTESTHUMAN")):
            self.bridge.work_once()
        self.assertEqual(self.paperclip.created, [])
        self.assertEqual(self.slack.sent, [])

    def test_departure_before_publication_denies_posts_and_status_reads_until_rejoin(self):
        self.queue()
        original_create = self.paperclip.create_proposal

        def create_then_leave(text, thread):
            issue = original_create(text, thread)
            self.slack.pages[""]["members"].remove("UTESTHUMAN")
            return issue

        with patch.object(self.paperclip, "create_proposal", side_effect=create_then_leave):
            self.bridge.work_once()
        self.assertEqual(self.store.proposal(THREAD)["state"], "created")
        self.assertEqual(self.slack.sent, [])
        self.paperclip.current_status = "in_review"
        self.bridge.poll_statuses()
        self.assertEqual(self.paperclip.status_calls, [])
        self.slack.pages[""]["members"].append("UTESTHUMAN")
        self.bridge.poll_statuses()
        self.assertEqual(len(self.slack.sent), 1)
        self.assertIn("Proposal status: in_review", self.slack.sent[0]["text"])

    def test_complete_pagination_includes_apps_but_does_not_authorize_bot_events(self):
        self.slack.pages = {
            "": {"ok": True, "members": ["UTESTHUMAN", "UTESTBOT"],
                 "response_metadata": {"next_cursor": "page-2"}},
            "page-2": {"ok": True, "members": ["UTESTNEW", "UBOTOTHER"],
                       "response_metadata": {"next_cursor": ""}},
        }
        self.bridge.gate.check("UTESTNEW")
        self.assertEqual(self.slack.member_calls, ["", "page-2"])
        for fields in ({"user": "UBOTOTHER", "bot_id": "BOTHER"},
                       {"user": "UBOTOTHER", "subtype": "bot_message"},
                       {"user": "UBOTOTHER", "bot_profile": {}},
                       {"user": "UTESTBOT"}, {"user": "not-a-user-id"},
                       {"user": ["UTESTNEW"]}):
            p = payload()
            p["event"].update(fields)
            self.bridge.accept("env-bot", p)
        self.assertIsNone(self.store.pending_event())
        self.assertEqual(self.paperclip.created, [])
        self.assertEqual(self.slack.sent, [])

    def test_late_page_errors_and_invalid_member_ids_never_accept_partial_membership(self):
        limited = RuntimeError(SENTINEL)
        limited.response = SimpleNamespace(status_code=429)
        for index, (page, code) in enumerate((
                ({"ok": True, "members": ["malformed-member-id"],
                  "response_metadata": {"next_cursor": ""}}, "slack_membership_invalid"),
                ({"ok": True, "members": ["UTESTNEW"]}, "slack_membership_invalid"),
                (limited, "slack_rate_limited"),
                (TimeoutError(SENTINEL), "slack_membership_unavailable"))):
            self.slack.pages = {
                "": {"ok": True, "members": ["UTESTHUMAN", "UTESTBOT"],
                     "response_metadata": {"next_cursor": "page-2"}},
                "page-2": page,
            }
            with self.assertRaises(Refused) as error:
                self.bridge.gate.check("UTESTHUMAN")
            self.assertEqual(error.exception.code, code)
            self.queue(event_id="event-" + str(index), thread=f"{1700000000 + index}.000001")
            self.bridge.work_once()
        self.assertEqual(self.paperclip.created, [])
        self.assertEqual(self.slack.sent, [])

    def test_policy_binding_is_explicit_and_cannot_be_changed_on_existing_ledger(self):
        with self.assertRaises(Refused):
            self.store.bind(replace(self.config, access_mode="allowlist",
                                    allowed_user_ids=frozenset({"UTESTHUMAN"})))
        values = [getattr(self.config, key) for key in (
            "workspace_id", "app_id", "bot_user_id", "bot_id", "channel_id",
            "company_id", "company_prefix", "paperclip_api_url", "paperclip_public_url")]
        values.append([])
        legacy_empty_digest = hashlib.sha256(json.dumps(values).encode("utf-8")).hexdigest()
        actual = self.store.db.execute("SELECT digest FROM binding").fetchone()[0]
        self.assertNotEqual(actual, legacy_empty_digest)
        values.append({"access_mode": "channel_members"})
        self.assertEqual(actual, hashlib.sha256(json.dumps(values).encode("utf-8")).hexdigest())


class ConversationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = Config.parse({
            **config_data(self.temp.name), "access_mode": "channel_members", "allowed_user_ids": [],
            "interaction_mode": "conversation", "coordinator_socket": "/run/approval-test.sock",
        })
        self.store = Store(self.config.state_path)
        self.slack, self.paperclip, self.coordinator = Slack(), PaperclipFake(), CoordinatorFake()
        self.now = 100
        self.bridge = Bridge(self.config, self.store, self.slack, self.paperclip,
                             clock=lambda: self.now, coordinator=self.coordinator)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def queue(self, event="chat-1", text="A synthetic question", user="UTESTHUMAN", thread=THREAD):
        p = payload(event, text=text)
        p["event"].update(user=user, thread_ts=thread)
        self.bridge.accept("env-" + event, p)
        return p

    def reopen(self):
        self.store.close()
        self.store = Store(self.config.state_path)
        self.store.bind(self.config)
        self.store.recover()
        self.bridge = Bridge(self.config, self.store, self.slack, self.paperclip,
                             clock=lambda: self.now, coordinator=self.coordinator)

    def test_chat_queues_before_ack_invokes_once_and_never_contacts_paperclip(self):
        p = self.queue()
        self.assertEqual(self.coordinator.calls, [])
        with sqlite3.connect(self.config.state_path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM chat_turns").fetchone()[0], 1)
        with patch.object(self.paperclip, "check_safe", side_effect=network_forbidden) as preflight, \
                patch.object(self.paperclip, "create_proposal", side_effect=network_forbidden) as create:
            self.bridge.work_once()
            preflight.assert_not_called()
            create.assert_not_called()
        self.bridge.accept("env-replay", p)
        self.bridge.work_once()
        self.assertEqual(self.coordinator.calls, [("A synthetic question", [])])
        self.assertEqual(len(self.slack.sent), 1)
        self.assertEqual(self.slack.sent[0]["thread_ts"], THREAD)
        self.assertEqual(self.store.chat_turn("chat-1")["state"], "sent")

    def test_only_human_task_prefix_uses_legacy_private_proposal_path(self):
        self.queue("task-event", "task: prepare a proposal")
        self.bridge.work_once()
        self.assertEqual(len(self.paperclip.created), 1)
        self.assertEqual(self.coordinator.calls, [])
        self.assertIn("queued for human review", self.slack.sent[0]["text"])
        self.coordinator.reply = 'task: do not execute {"channel":"CTESTOTHER","thread":"other"}'
        self.queue("chat-event", "Explain the proposal")
        self.bridge.work_once()
        self.assertEqual(len(self.paperclip.created), 1)
        self.assertEqual(self.slack.sent[-1]["thread_ts"], THREAD)
        self.assertEqual(self.slack.sent[-1]["channel"], "CTEST01")

    def test_model_markup_mentions_and_links_are_escaped_with_fixed_advice_suffix(self):
        self.coordinator.reply = "<!channel> <@UTESTOTHER> & <https://example.invalid|link> @everyone"
        self.queue()
        self.bridge.work_once()
        message = self.slack.sent[0]
        self.assertNotIn("<", message["text"])
        self.assertIn("&lt;!channel&gt;", message["text"])
        self.assertIn("&lt;@UTESTOTHER&gt;", message["text"])
        self.assertIn("&amp;", message["text"])
        self.assertTrue(message["text"].endswith(DRAFT_SUFFIX))
        self.assertFalse(message["mrkdwn"])
        self.assertFalse(message["link_names"])
        self.assertFalse(message["unfurl_links"])
        self.assertFalse(message["unfurl_media"])
        self.assertEqual(message["parse"], "none")

    def test_new_members_work_but_departure_before_generation_or_post_is_denied(self):
        self.queue("left-before-generation")
        self.slack.pages[""]["members"].remove("UTESTHUMAN")
        self.bridge.work_once()
        self.assertEqual(self.coordinator.calls, [])
        self.slack.pages[""]["members"].append("UTESTHUMAN")
        self.queue(user="UTESTNEW")
        self.bridge.work_once()
        self.assertEqual(self.coordinator.calls, [])
        self.slack.pages[""]["members"].append("UTESTNEW")
        self.queue("chat-new", user="UTESTNEW")
        self.coordinator.during_query = lambda: self.slack.pages[""]["members"].remove("UTESTNEW")
        self.bridge.work_once()
        self.assertEqual(len(self.coordinator.calls), 1)
        self.assertEqual(self.slack.sent, [])
        self.assertEqual(self.store.chat_turn("chat-new")["state"], "rejected")
        self.assertIsNone(self.store.chat_turn("chat-new")["reply"])

    def test_late_page_rate_limit_prevents_generation_and_unauthorized_error_post(self):
        limited = RuntimeError(SENTINEL)
        limited.response = SimpleNamespace(status_code=429)
        self.slack.pages = {
            "": {"ok": True, "members": ["UTESTHUMAN", "UTESTBOT"],
                 "response_metadata": {"next_cursor": "page-2"}},
            "page-2": limited,
        }
        self.queue()
        self.bridge.work_once()
        self.assertEqual(self.coordinator.calls, [])
        self.assertEqual(self.slack.sent, [])
        self.assertIsNone(self.store.chat_turn("chat-1")["prompt"])

    def test_history_is_same_thread_recent_sent_pairs_with_three_pair_budget(self):
        for index in range(5):
            self.queue("chat-" + str(index), "question-" + str(index))
            self.bridge.work_once()
        history = self.coordinator.calls[-1][1]
        self.assertEqual(len(history), 6)
        self.assertEqual([m["content"] for m in history[::2]],
                         ["question-1", "question-2", "question-3"])
        self.queue("chat-other-thread", thread="1700000002.000001")
        self.bridge.work_once()
        self.assertEqual(self.coordinator.calls[-1][1], [])
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM events").fetchone()[0], 0)

    def test_history_character_and_utf8_budgets_skip_oversized_whole_pairs(self):
        self.coordinator.reply = "\U0001f642" * 3000
        self.queue("large-pair", "x" * 4000)
        self.bridge.work_once()
        self.coordinator.reply = "\U0001f642" * 999
        for index in range(2):
            self.queue("budget-" + str(index), "\U0001f642" * 2000)
            self.bridge.work_once()
        self.queue("budget-final", "A short final query")
        self.bridge.work_once()
        history = self.coordinator.calls[-1][1]
        self.assertEqual(len(history), 4)
        self.assertLessEqual(sum(len(m["content"]) for m in history), 6000)
        self.assertLessEqual(sum(len(m["content"].encode()) for m in history), 24000)
        self.assertNotIn("x" * 4000, str(history))

    def test_own_literal_bot_mentions_are_absent_from_query_and_both_history_roles(self):
        self.coordinator.reply = "Advice mentioning <@UTESTBOT> literally."
        self.queue("chat-first", "Question with another <@UTESTBOT> literal.")
        self.bridge.work_once()
        self.queue("chat-followup", "Followup <@UTESTBOT>")
        self.bridge.work_once()
        query, history = self.coordinator.calls[-1]
        self.assertNotIn("<@UTESTBOT>", query)
        self.assertNotIn("<@UTESTBOT>", json.dumps(history))
        self.assertEqual(set(history[0]), {"role", "content"})
        self.assertEqual(len(history), 2)

    def test_history_drops_all_indirect_context_after_any_sent_contributor_leaves(self):
        self.slack.pages[""]["members"].append("UTESTNEW")
        self.queue("chat-original", "Original private context")
        self.bridge.work_once()
        self.queue("chat-new", "A response possibly quoting original context", user="UTESTNEW")
        self.bridge.work_once()
        self.assertEqual(len(self.coordinator.calls[-1][1]), 2)
        self.slack.pages[""]["members"].remove("UTESTHUMAN")
        self.queue("chat-after-departure", "A fresh question", user="UTESTNEW")
        self.bridge.work_once()
        self.assertEqual(self.coordinator.calls[-1][1], [])

    def test_history_contributor_departure_during_generation_blocks_publication(self):
        self.slack.pages[""]["members"].append("UTESTNEW")
        self.queue()
        self.bridge.work_once()
        self.queue("chat-new", user="UTESTNEW")
        self.coordinator.during_query = lambda: self.slack.pages[""]["members"].remove("UTESTHUMAN")
        self.bridge.work_once()
        self.assertEqual(len(self.slack.sent), 1)
        self.assertEqual(self.store.chat_turn("chat-new")["state"], "rejected")

    def test_older_unselected_contributor_departure_blocks_indirect_quote_publication(self):
        self.slack.pages[""]["members"].append("UTESTNEW")
        self.queue("old-b", "OLDER_B_PROMPT_NOT_SELECTED", user="UTESTNEW")
        self.bridge.work_once()
        self.coordinator.reply = "Recent A advice indirectly quoting older B private context."
        for index in range(3):
            self.queue("recent-a-" + str(index), "Recent A question " + str(index))
            self.bridge.work_once()
        history, contributors = self.store.chat_history(
            THREAD, frozenset(self.slack.pages[""]["members"]), self.now)
        self.assertEqual(len(history), 6)
        self.assertNotIn("OLDER_B_PROMPT_NOT_SELECTED", str(history))
        self.assertTrue(all("older B private context" in message["content"]
                            for message in history if message["role"] == "assistant"))
        self.queue("final-a", "A follow-up relying on recent indirect quotes")
        self.coordinator.during_query = lambda: self.slack.pages[""]["members"].remove("UTESTNEW")
        self.bridge.work_once()
        self.assertEqual(self.coordinator.calls[-1][1], history)
        self.assertEqual(len(self.slack.sent), 4)
        self.assertEqual(self.store.chat_turn("final-a")["state"], "rejected")
        self.assertIsNone(self.store.chat_turn("final-a")["prompt"])
        self.assertIsNone(self.store.chat_turn("final-a")["reply"])
        self.assertEqual(contributors, frozenset({"UTESTHUMAN", "UTESTNEW"}))

    def test_pending_expiry_and_sent_history_erasure_retain_only_minimal_receipts(self):
        self.queue("sent", SENTINEL)
        self.bridge.work_once()
        self.queue("expired", "PENDING_RAW_SYNTHETIC_TEXT")
        self.now = 700
        self.bridge.work_once()
        self.assertEqual(self.store.chat_turn("expired")["state"], "expired")
        self.assertIsNone(self.store.chat_turn("expired")["prompt"])
        self.now = 86500
        self.bridge.work_once()
        row = self.store.chat_turn("sent")
        self.assertEqual(row["state"], "sent")
        self.assertIsNone(row["prompt"])
        self.assertIsNone(row["reply"])
        self.assertIsNotNone(row["attempted"])
        self.assertNotIn(SENTINEL.encode(), Path(self.config.state_path).read_bytes())

    def test_pending_cap_is_durable_and_rolls_back_an_unqueued_envelope(self):
        for index in range(20):
            self.queue("queued-" + str(index))
        with self.assertRaises(Refused):
            self.queue("overflow")
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM chat_turns").fetchone()[0], 20)
        self.assertIsNone(self.store.db.execute(
            "SELECT 1 FROM envelopes WHERE id='env-overflow'").fetchone())
        self.assertEqual(self.coordinator.calls, [])

    def test_persistent_per_user_hour_global_hour_and_daily_attempt_caps(self):
        for count, requester, ago in ((10, "UTESTHUMAN", 1), (30, "UTESTOTHER", 1),
                                      (100, "UTESTOTHER", 7200)):
            with self.subTest(count=count):
                self.now = 10000
                with self.store.transaction() as db:
                    db.execute("DELETE FROM chat_turns")
                    db.execute("DELETE FROM envelopes")
                    db.execute("DELETE FROM deliveries")
                    for index in range(count):
                        db.execute(
                            "INSERT INTO chat_turns(id,thread,requester,mode,received,state,attempted) "
                            "VALUES (?,?,?,'conversation',?,'failed',?)",
                            ("seed-" + str(index), THREAD, requester, self.now - ago, self.now - ago))
                self.reopen()
                self.queue("over-limit", SENTINEL)
                before = len(self.coordinator.calls)
                self.bridge.work_once()
                self.assertEqual(len(self.coordinator.calls), before)
                self.assertEqual(self.store.chat_turn("over-limit")["state"], "rate_limited")
                self.assertIsNone(self.store.chat_turn("over-limit")["prompt"])
                self.assertEqual(self.slack.sent[-1]["text"], CHAT_UNAVAILABLE)

    def test_worker_errors_timeouts_and_invalid_replies_are_fixed_not_history(self):
        for index, error in enumerate((TimeoutError(SENTINEL), RuntimeError(SENTINEL),
                                       CoordinatorError("rate_limited"))):
            self.coordinator.error = error
            event = "failed-" + str(index)
            self.queue(event, SENTINEL)
            self.bridge.work_once()
            row = self.store.chat_turn(event)
            self.assertEqual(row["state"], "failed")
            self.assertIsNone(row["prompt"])
            self.assertIsNone(row["reply"])
            self.assertEqual(self.slack.sent[-1]["text"], CHAT_UNAVAILABLE)
            self.assertNotIn(SENTINEL, self.slack.sent[-1]["text"])
        self.coordinator.error = None
        self.coordinator.reply = "x" * 3001
        self.queue("invalid-reply")
        self.bridge.work_once()
        self.assertEqual(self.slack.sent[-1]["text"], CHAT_UNAVAILABLE)
        self.assertEqual(self.store.chat_history(THREAD, {"UTESTHUMAN"}, self.now)[0], [])

    def test_generation_and_publication_crashes_hold_without_model_or_post_replay(self):
        for index, at_send in enumerate((False, True)):
            self.coordinator.error = None if at_send else Crash()
            self.slack.send_error = Crash() if at_send else None
            event = "crash-" + str(index)
            p = self.queue(event)
            with self.assertRaises(Crash):
                self.bridge.work_once()
            self.assertEqual(self.store.chat_turn(event)["state"], "generating")
            self.assertIsNone(self.store.chat_turn(event)["prompt"])
            calls, sends = len(self.coordinator.calls), len(self.slack.sent)
            self.reopen()
            self.coordinator.error, self.slack.send_error = None, None
            self.bridge.accept("replay-" + str(index), p)
            self.bridge.work_once()
            self.assertEqual(self.store.chat_turn(event)["state"], "uncertain")
            self.assertEqual(len(self.coordinator.calls), calls)
            self.assertEqual(len(self.slack.sent), sends)
            self.assertIsNone(self.store.chat_turn(event)["reply"])

    def test_ambiguous_slack_post_never_retries_or_retains_model_reply(self):
        self.slack.send_error = TimeoutError(SENTINEL)
        p = self.queue()
        self.bridge.work_once()
        self.assertEqual(self.store.chat_turn("chat-1")["state"], "uncertain")
        self.assertIsNone(self.store.chat_turn("chat-1")["reply"])
        self.reopen()
        self.bridge.accept("another-envelope", p)
        self.bridge.work_once()
        self.assertEqual(len(self.coordinator.calls), 1)
        self.assertEqual(len(self.slack.sent), 1)

    def test_shared_event_dedupe_and_upgrade_preserve_legacy_proposals_and_receipts(self):
        legacy = replace(self.config, interaction_mode="proposal", coordinator_socket="")
        self.store.accept("legacy-envelope", "legacy-event", THREAD, "UTESTHUMAN", SENTINEL, self.now)
        self.store.begin_create(THREAD)
        self.store.created(THREAD, Issue(ISSUE_ID, "TEST-5"))
        self.store.finish_event("legacy-event")
        self.store.begin_delivery("event:legacy-event", THREAD)
        self.store.delivery_finished("event:legacy-event", "sent")
        self.store.stop_polling(THREAD)
        self.store.bind(legacy)  # Interaction capability is not an access-policy rebind.
        tables = ("events", "proposals", "deliveries", "binding", "envelopes")
        before = {table: [tuple(r) for r in self.store.db.execute("SELECT * FROM " + table)]
                  for table in tables}
        with self.store.transaction() as db:
            db.execute("DROP TABLE chat_turns")  # Synthetic pre-conversation schema.
        self.reopen()
        self.bridge.work_once()
        self.assertEqual(self.coordinator.calls, [])
        for table in tables:
            self.assertEqual([tuple(r) for r in self.store.db.execute("SELECT * FROM " + table)],
                             before[table])
        self.queue("legacy-event")
        self.assertIsNone(self.store.chat_turn("legacy-event"))
        self.queue("chat-event")
        self.store.accept("task-envelope", "chat-event", "1700000002.000001",
                          "UTESTHUMAN", "task: duplicate event", self.now)
        self.assertIsNone(self.store.proposal("1700000002.000001"))
        self.bridge.work_once()
        self.assertEqual(len(self.coordinator.calls), 1)
        self.assertIn("Synthetic coordinator advice", self.slack.sent[-1]["text"])
        self.assertNotIn("already has a proposal", self.slack.sent[-1]["text"])
        self.assertEqual(self.store.proposal(THREAD)["issue_identifier"], "TEST-5")
        self.assertEqual(self.paperclip.created, [])

    def test_mode_downgrade_does_not_reinterpret_or_run_pending_chat(self):
        self.queue()
        self.bridge = Bridge(replace(self.config, interaction_mode="proposal", coordinator_socket=""),
                             self.store, self.slack, self.paperclip, clock=lambda: self.now)
        self.bridge.work_once()
        self.assertEqual(self.store.chat_turn("chat-1")["state"], "rejected")
        self.assertEqual(self.coordinator.calls, [])
        self.assertEqual(self.paperclip.created, [])


class CoordinatorProtocolTests(unittest.TestCase):
    class Transport:
        def __init__(self, response):
            self.response, self.sent, self.connected = response, [], []
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def settimeout(self, value):
            assert 0 < value <= 120
        def connect(self, path):
            self.connected.append(path)
        def sendall(self, data):
            self.sent.append(data)
        def recv(self, count):
            data, self.response = self.response[:count], self.response[count:]
            return data

    def client(self, response):
        transport = self.Transport(response)
        return Coordinator("/run/approval-test.sock"), transport

    def test_exact_bounded_ndjson_uses_only_one_unix_connection(self):
        client, transport = self.client(
            b'{"version":1,"ok":true,"text":"A synthetic answer"}\n')
        history = [{"role": "user", "content": "Earlier"}, {"role": "assistant", "content": "Draft"}]
        with patch.object(client, "check"), \
                patch.object(socket, "socket", return_value=transport) as factory:
            self.assertEqual(client.query("Question", history), "A synthetic answer")
        factory.assert_called_once_with(socket.AF_UNIX, socket.SOCK_STREAM)
        self.assertEqual(transport.connected, ["/run/approval-test.sock"])
        self.assertEqual(json.loads(transport.sent[0]),
                         {"version": 1, "text": "Question", "history": history})
        self.assertTrue(transport.sent[0].endswith(b"\n"))
        self.assertLessEqual(len(transport.sent[0]), 65536)

    def test_request_validation_rejects_bad_or_oversized_history_before_connect(self):
        invalid = [
            ("", []), ("x" * 4097, []), ("\x00", []), ("\ud800", []),
            ("Question", [{"role": "user", "content": "Unpaired"}]),
            ("Question", [{"role": "assistant", "content": "Wrong first"},
                          {"role": "user", "content": "Wrong second"}]),
            ("Question", [{"role": "user", "content": "x" * 3001},
                          {"role": "assistant", "content": "x" * 3000}]),
            ("Question", [{"role": "user", "content": "x", "extra": True},
                          {"role": "assistant", "content": "x"}]),
            ("Question", [{"role": "user" if i % 2 == 0 else "assistant", "content": "x"}
                          for i in range(8)]),
        ]
        client = Coordinator("/run/approval-test.sock")
        with patch.object(socket, "socket", side_effect=network_forbidden) as factory:
            for text, history in invalid:
                with self.subTest(text=text), self.assertRaises(CoordinatorError):
                    client.query(text, history)
        factory.assert_not_called()

    def test_strict_response_schema_duplicate_keys_utf8_and_wire_bounds(self):
        invalid = [
            b'{"version":true,"ok":true,"text":"bad"}\n',
            b'{"version":1,"ok":1,"text":"bad"}\n',
            b'{"version":1,"ok":true,"text":"bad","thread":"other"}\n',
            b'{"version":1,"version":1,"ok":true,"text":"bad"}\n',
            b'{"version":1,"ok":true,"text":"bad"}',
            b'{"version":1,"ok":true,"text":"bad"}\n{}\n',
            b'{"version":1,"ok":true,"text":"\\ud800"}\n',
            b'\xff\n', b'x' * 65536 + b'\n',
            json.dumps({"version": 1, "ok": True, "text": "x" * 3001}).encode() + b"\n",
        ]
        for response in invalid:
            client, transport = self.client(response)
            with self.subTest(size=len(response)), patch.object(client, "check"), \
                    patch.object(socket, "socket", return_value=transport), \
                    self.assertRaises(CoordinatorError):
                client.query("Question", [])

    def test_wire_limit_includes_newline_and_unicode_response_bound_is_not_truncated(self):
        line = b'{"version":1,"ok":true,"text":"Answer"}'
        maximum = line + b" " * (65535 - len(line)) + b"\n"
        client, transport = self.client(maximum)
        with patch.object(client, "check"), patch.object(socket, "socket", return_value=transport):
            self.assertEqual(client.query("Question", []), "Answer")
        response = json.dumps({"version": 1, "ok": True, "text": "\U0001f642" * 3000},
                              ensure_ascii=False).encode() + b"\n"
        client, transport = self.client(response)
        with patch.object(client, "check"), patch.object(socket, "socket", return_value=transport):
            self.assertEqual(len(client.query("Question", []).encode()), 12000)
        client, transport = self.client(b"")
        with patch.object(client, "check"), patch.object(socket, "socket", return_value=transport), \
                patch("test_approval_bridge.coordinator.time.monotonic", side_effect=[0, 0, 121]), \
                self.assertRaises(CoordinatorError) as error:
            client.query("Question", [])
        self.assertEqual(error.exception.code, "timeout")
        self.assertEqual(len(transport.sent), 1)

    def test_only_fixed_worker_errors_are_retained_and_timeout_has_no_retry(self):
        for code in ("invalid_request", "rate_limited", "timeout", "unavailable", "generation_failed",
                     SENTINEL + "\nprivate", {"raw": SENTINEL}):
            client, transport = self.client(
                json.dumps({"version": 1, "ok": False, "error": code}).encode() + b"\n")
            with patch.object(client, "check"), patch.object(socket, "socket", return_value=transport), \
                    self.assertRaises(CoordinatorError) as error:
                client.query("Question", [])
            self.assertNotIn(SENTINEL, str(error.exception))
            self.assertEqual(len(transport.sent), 1)
        client, transport = self.client(b"")
        with patch.object(client, "check"), patch.object(socket, "socket", return_value=transport), \
                patch.object(transport, "recv", side_effect=TimeoutError(SENTINEL)), \
                self.assertRaises(CoordinatorError) as error:
            client.query("Question", [])
        self.assertEqual(error.exception.code, "timeout")
        self.assertEqual(len(transport.sent), 1)

    def test_stat_only_socket_and_parent_permissions_refuse_symlinks_or_mutable_ownership(self):
        safe = {
            "/": SimpleNamespace(st_mode=stat.S_IFDIR | 0o755, st_uid=0),
            "/run": SimpleNamespace(st_mode=stat.S_IFDIR | 0o755, st_uid=0),
            "/run/approval-test.sock": SimpleNamespace(
                st_mode=stat.S_IFSOCK | 0o660, st_uid=0, st_gid=os.getegid()),
        }
        client = Coordinator("/run/approval-test.sock")
        with patch.object(Path, "lstat", lambda path: safe[str(path)]), \
                patch.object(socket, "socket", side_effect=network_forbidden) as factory:
            client.check()
        factory.assert_not_called()
        for path, info in (
                ("/run", SimpleNamespace(st_mode=stat.S_IFDIR | 0o775, st_uid=0)),
                ("/run", SimpleNamespace(st_mode=stat.S_IFDIR | 0o755, st_uid=1001)),
                ("/run", SimpleNamespace(st_mode=stat.S_IFLNK | 0o777, st_uid=0)),
                ("/run/approval-test.sock", SimpleNamespace(
                    st_mode=stat.S_IFSOCK | 0o660, st_uid=1001, st_gid=os.getegid())),
                ("/run/approval-test.sock", SimpleNamespace(
                    st_mode=stat.S_IFSOCK | 0o660, st_uid=0, st_gid=os.getegid() + 1)),
                ("/run/approval-test.sock", SimpleNamespace(
                    st_mode=stat.S_IFSOCK | 0o666, st_uid=0, st_gid=os.getegid())),
                ("/run/approval-test.sock", SimpleNamespace(
                    st_mode=stat.S_IFLNK | 0o660, st_uid=0, st_gid=os.getegid()))):
            invalid = {**safe, path: info}
            with self.subTest(path=path), \
                    patch.object(Path, "lstat", lambda p: invalid[str(p)]), \
                    self.assertRaises(CoordinatorError):
                client.check()


class EntrypointTests(unittest.TestCase):
    def test_interaction_defaults_and_socket_configuration_are_strict(self):
        with tempfile.TemporaryDirectory() as directory:
            data = config_data(directory)
            legacy = Config.parse(data)
            self.assertEqual((legacy.interaction_mode, legacy.coordinator_socket), ("proposal", ""))
            self.assertEqual(legacy, Config.parse({
                **data, "interaction_mode": "proposal", "coordinator_socket": "",
            }))
            self.assertEqual(Config.parse({
                **data, "interaction_mode": "conversation", "coordinator_socket": "/run/example.sock",
            }).interaction_mode, "conversation")
            for change in (
                    {"interaction_mode": "other"}, {"interaction_mode": None},
                    {"interaction_mode": []}, {"coordinator_socket": "/run/example.sock"},
                    {"interaction_mode": "conversation"},
                    {"interaction_mode": "conversation", "coordinator_socket": "../example.sock"},
                    {"interaction_mode": "conversation", "coordinator_socket": "/run/../example.sock"},
                    {"interaction_mode": "conversation", "coordinator_socket": "/run/link//sock"},
                    {"interaction_mode": "conversation", "coordinator_socket": "/run/example.sock\n"},
                    {"interaction_mode": "conversation", "coordinator_socket": "/run/" + "x" * 108}):
                with self.subTest(change=change), self.assertRaises(Refused):
                    Config.parse({**data, **change})

    def test_conversation_preflight_only_stats_socket_and_never_invokes_model(self):
        coordinator = SimpleNamespace(check=lambda: None, query=network_forbidden)
        with patch.object(entry, "Coordinator", return_value=coordinator) as factory, \
                patch.object(coordinator, "check", wraps=coordinator.check) as check:
            self.assertEqual(self.invoke_preflight(config_change={
                "interaction_mode": "conversation", "coordinator_socket": "/run/approval-test.sock",
            }), (0, "preflight_ok_read_only\n", ""))
        factory.assert_called_once_with("/run/approval-test.sock")
        check.assert_called_once_with()

    def test_access_mode_is_optional_and_rejects_ambiguous_or_malformed_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            data = config_data(directory)
            legacy = Config.parse(data)
            self.assertEqual(legacy.access_mode, "allowlist")
            self.assertEqual(legacy, Config.parse({**data, "access_mode": "allowlist"}))
            self.assertEqual(Config(**{
                key: getattr(legacy, key) for key in Config.__dataclass_fields__ if key != "access_mode"
            }), legacy)
            self.assertEqual(Config.parse({
                **data, "access_mode": "channel_members", "allowed_user_ids": [],
            }).allowed_user_ids, frozenset())
            for change in (
                    {"access_mode": "unknown"}, {"access_mode": None},
                    {"access_mode": True}, {"access_mode": []},
                    {"access_mode": {}}, {"allowed_user_ids": []},
                    {"access_mode": "channel_members"},
                    {"access_mode": "channel_members", "allowed_user_ids": ["UTESTBOT"]},
                    {"access_mode": "channel_members", "allowed_user_ids": None},
                    {"access_mode": "channel_members", "allowed_user_ids": {}},
                    {"allowed_user_ids": ["not-a-user-id"]}):
                with self.subTest(change=change), self.assertRaises(Refused):
                    Config.parse({**data, **change})
            for mode in ("allowlist", "channel_members"):
                missing = {**data, "access_mode": mode}
                del missing["allowed_user_ids"]
                with self.assertRaises(Refused):
                    Config.parse(missing)

    def test_default_mode_preserves_legacy_ledger_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Config.parse(config_data(directory))
            values = [getattr(config, key) for key in (
                "workspace_id", "app_id", "bot_user_id", "bot_id", "channel_id",
                "company_id", "company_prefix", "paperclip_api_url", "paperclip_public_url")]
            values.append(sorted(config.allowed_user_ids))
            legacy_digest = hashlib.sha256(json.dumps(values).encode("utf-8")).hexdigest()
            store = Store(config.state_path)
            try:
                with store.transaction() as db:
                    db.execute("INSERT INTO binding VALUES (1,?)", (legacy_digest,))
                store.bind(config)
                store.bind(replace(config, access_mode="allowlist"))
                self.assertEqual(store.db.execute("SELECT digest FROM binding").fetchone()[0],
                                 legacy_digest)
                with self.assertRaises(Refused):
                    store.bind(replace(config, access_mode="channel_members",
                                       allowed_user_ids=frozenset()))
            finally:
                store.close()

    def invoke_preflight(self, command="check", slack=None, config_change=None,
                         credentials=True, dependency=True, web_error=None,
                         paperclip_error=None, gate_error=None):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({**config_data(directory), **(config_change or {})}))
            path.chmod(0o600)
            slack = slack or Slack()
            paperclip = PaperclipFake()
            paperclip.safety_error = paperclip_error

            def web_client(**kwargs):
                if web_error is not None:
                    raise web_error
                return slack

            modules = {
                "slack_sdk": SimpleNamespace(WebClient=web_client) if dependency else None,
                "slack_sdk.socket_mode": SimpleNamespace(SocketModeClient=network_forbidden),
                "slack_sdk.socket_mode.response": SimpleNamespace(SocketModeResponse=SimpleNamespace),
            }
            environment = ({"SLACK_BOT_TOKEN": "xoxb-synthetic", "SLACK_APP_TOKEN": "xapp-synthetic"}
                           if credentials else {})
            with patch.dict(sys.modules, modules), patch.dict(os.environ, environment, clear=True), \
                    patch.object(entry, "Paperclip", return_value=paperclip), \
                    patch.object(entry, "Gate", wraps=entry.Gate) as gate, \
                    patch.object(sys, "argv", ["slack_bridge.py", command, "--config", str(path)]), \
                    patch("sys.stdout", new_callable=io.StringIO) as stdout, \
                    patch("sys.stderr", new_callable=io.StringIO) as stderr:
                if gate_error is not None:
                    gate.side_effect = gate_error
                result = entry.main()
            self.assertEqual(sorted(p.name for p in Path(directory).iterdir()), ["config.json"])
            return result, stdout.getvalue(), stderr.getvalue()

    def assert_diagnostic(self, code, **kwargs):
        self.assertEqual(self.invoke_preflight(**kwargs), (1, "", "preflight_failed:" + code + "\n"))

    def test_empty_dynamic_allowlist_never_skips_startup_privacy_or_bot_membership_gate(self):
        policy = {"access_mode": "channel_members", "allowed_user_ids": []}
        slack = Slack()
        slack.pages[""]["members"].append("UTESTNEW")
        self.assertEqual(self.invoke_preflight(slack=slack, config_change=policy),
                         (0, "preflight_ok_read_only\n", ""))
        self.assertEqual(slack.member_calls, [""])
        for change, code in (
                (lambda s: s.channel.update(is_private=False), "slack_channel_not_private"),
                (lambda s: s.channel.update(is_shared=True), "slack_channel_not_safe"),
                (lambda s: s.channel.pop("is_archived"), "slack_channel_metadata_invalid"),
                (lambda s: s.pages[""].update(members=["UTESTHUMAN"]),
                 "slack_channel_not_member")):
            slack = Slack()
            change(slack)
            self.assert_diagnostic(code, slack=slack, config_change=policy)
            self.assertEqual(self.invoke_preflight(
                command="run", slack=slack, config_change=policy),
                (1, "", "bridge_failed_closed\n"))

    def test_allowlist_startup_uses_one_snapshot_and_checks_every_configured_requester(self):
        slack = Slack()
        slack.pages[""]["members"].append("UTESTOTHER")
        policy = {"allowed_user_ids": ["UTESTHUMAN", "UTESTOTHER"]}
        self.assertEqual(self.invoke_preflight(slack=slack, config_change=policy),
                         (0, "preflight_ok_read_only\n", ""))
        self.assertEqual(slack.member_calls, [""])
        slack.pages[""]["members"].remove("UTESTOTHER")
        self.assert_diagnostic("slack_requester_not_member", slack=slack, config_change=policy)

    def test_membership_mode_keeps_exact_manifest_scopes_and_subscription(self):
        manifest = json.loads((SOURCE / "manifest.json").read_text())
        self.assertEqual(manifest["oauth_config"]["scopes"]["bot"],
                         ["app_mentions:read", "chat:write", "groups:read"])
        self.assertEqual(manifest["settings"]["event_subscriptions"]["bot_events"],
                         ["app_mention"])

    def test_check_phase_failures_have_only_fixed_single_line_codes(self):
        for code, kwargs in (
                ("config_invalid", {"config_change": {"workspace_id": SENTINEL}}),
                ("credentials_missing", {"credentials": False}),
                ("dependency_unavailable", {"dependency": False}),
                ("validation_failed", {"web_error": RuntimeError(SENTINEL)}),
                ("paperclip_preflight_failed", {"paperclip_error": RuntimeError(SENTINEL)})):
            with self.subTest(code=code):
                self.assert_diagnostic(code, **kwargs)

    def test_check_distinguishes_identity_channel_and_complete_membership_failures(self):
        cases = [
            ("slack_auth_failed", lambda s: s.auth.update(ok=False, error="invalid_auth")),
            ("slack_identity_mismatch", lambda s: s.auth.update(user_id="UTESTOTHER")),
            ("slack_channel_not_private", lambda s: s.channel.update(is_private=False)),
            ("slack_channel_not_member", lambda s: s.channel.update(is_member=False)),
            ("slack_channel_not_safe", lambda s: s.channel.update(is_archived=True)),
            ("slack_channel_not_safe", lambda s: s.channel.update(is_shared=True)),
            ("slack_channel_metadata_invalid", lambda s: s.channel.pop("is_private")),
            ("slack_channel_metadata_invalid", lambda s: s.channel.update(is_member="false")),
            ("slack_member_not_allowed", lambda s: s.pages[""]["members"].append("UTESTOTHER")),
            ("slack_requester_not_member", lambda s: s.pages[""].update(members=["UTESTBOT"])),
            ("slack_channel_not_member", lambda s: s.pages[""].update(members=["UTESTHUMAN"])),
            ("slack_membership_invalid", lambda s: s.pages[""].pop("response_metadata")),
        ]
        for code, change in cases:
            with self.subTest(code=code):
                slack = Slack()
                change(slack)
                self.assert_diagnostic(code, slack=slack)
        slack = Slack()
        slack.pages = {
            "": {"ok": True, "members": ["UTESTHUMAN", "UTESTBOT"],
                 "response_metadata": {"next_cursor": "page-2"}},
            "page-2": {"ok": True, "members": ["UTESTOTHER"],
                       "response_metadata": {"next_cursor": ""}},
        }
        self.assert_diagnostic("slack_member_not_allowed", slack=slack)
        slack.pages["page-2"] = TimeoutError(SENTINEL)
        self.assert_diagnostic("slack_membership_unavailable", slack=slack)

    def test_check_whitelists_provider_errors_but_never_echoes_provider_text(self):
        cases = [
            ("auth_test", "invalid_auth", "slack_auth_failed"),
            ("auth_test", "token_revoked", "slack_auth_failed"),
            ("auth_test", "token_expired", "slack_auth_failed"),
            ("auth_test", "not_authed", "slack_auth_failed"),
            ("auth_test", "account_inactive", "slack_auth_failed"),
            ("conversations_info", "missing_scope", "slack_missing_scope"),
            ("conversations_info", "not_in_channel", "slack_channel_not_member"),
            ("conversations_info", "channel_not_found", "slack_channel_unavailable"),
            ("conversations_members", "ratelimited", "slack_rate_limited"),
            ("conversations_members", "rate_limited", "slack_rate_limited"),
        ]
        for method, provider, code in cases:
            with self.subTest(method=method, provider=provider):
                slack = Slack()
                # Exercise both normal ok:false responses and SDK exceptions.
                response = {"ok": False, "error": provider, "needed": SENTINEL}
                with patch.object(slack, method, return_value=response):
                    self.assert_diagnostic(code, slack=slack)
                error = RuntimeError(SENTINEL)
                error.response = response
                with patch.object(slack, method, side_effect=error):
                    self.assert_diagnostic(code, slack=slack)

    def test_check_transport_and_malicious_provider_values_use_stage_fallback(self):
        for method, code in (
                ("auth_test", "slack_auth_failed"),
                ("conversations_info", "slack_channel_unavailable"),
                ("conversations_members", "slack_membership_unavailable")):
            for value in (SENTINEL + "\nxoxb-synthetic", {"error": SENTINEL},
                          ["missing_scope"], "slack_missing_scope", None):
                with self.subTest(method=method, value=value):
                    slack = Slack()
                    error = TimeoutError(SENTINEL)
                    error.code = "slack_missing_scope\n" + SENTINEL
                    error.response = {"ok": False, "error": value, "payload": SENTINEL}
                    with patch.object(slack, method, side_effect=error):
                        self.assert_diagnostic(code, slack=slack)
            slack = Slack()
            with patch.object(slack, method, side_effect=TimeoutError(SENTINEL)):
                self.assert_diagnostic(code, slack=slack)
        error = RuntimeError(SENTINEL)
        error.response = SimpleNamespace(status_code=429, headers={"Retry-After": SENTINEL})
        slack = Slack()
        with patch.object(slack, "conversations_members", side_effect=error):
            self.assert_diagnostic("slack_rate_limited", slack=slack)

    def test_refused_normalizes_unknown_codes_and_check_revalidates_tampering(self):
        for value in (SENTINEL, "slack_missing_scope\n" + SENTINEL, None, {}, ["missing_scope"]):
            refused = entry.Refused(value)
            self.assertEqual(refused.code, "validation_failed")
            self.assertEqual(refused.args, ("validation_failed",))
            self.assert_diagnostic("validation_failed", gate_error=refused)
            refused.code = value
            self.assert_diagnostic("validation_failed", gate_error=refused)
        refused = entry.Refused("slack_missing_scope")
        del refused.code
        self.assert_diagnostic("validation_failed", gate_error=refused)
        self.assertEqual(len(entry.PREFLIGHT_CODES), 18)

    def test_run_failures_remain_generic_without_check_diagnostics(self):
        slack = Slack()
        slack.channel["is_private"] = False
        for kwargs in (
                {"config_change": {"workspace_id": SENTINEL}},
                {"credentials": False}, {"dependency": False}, {"slack": slack},
                {"paperclip_error": RuntimeError(SENTINEL)}):
            self.assertEqual(self.invoke_preflight(command="run", **kwargs),
                             (1, "", "bridge_failed_closed\n"))

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

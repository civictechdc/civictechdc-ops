"""Mention-only intake, authorization gates, and fixed notifications.

Transport clients are explicit constructor arguments, not plugins. Conversation
mode uses only bounded Unix RPC to a separately restricted coordinator.
"""

import html
import re
import time

from .config import Refused, identifier
from .coordinator import bounded_text

DRAFT_SUFFIX = "\n\nDraft/advice only; no work executed."
CHAT_UNAVAILABLE = "I couldn't safely complete that reply. Please try a new mention later." + DRAFT_SUFFIX


class RateLimited(Exception):
    def __init__(self, retry_after):
        self.retry_after = retry_after


def retry_after(error):
    """Only an explicit HTTP 429 is a definite rate limit, never a timeout."""
    response = getattr(error, "response", None)
    if response is None or getattr(response, "status_code", None) != 429:
        return None
    try:
        value = int(response.headers.get("Retry-After", response.headers.get("retry-after")))
        return max(1, min(value, 86400))
    except (ValueError, TypeError, AttributeError):
        return 60


def slack_failure_code(response, fallback):
    """Read only exact provider error names; never stringify response/errors."""
    try:
        if getattr(response, "status_code", None) == 429:
            return "slack_rate_limited"
        error = response.get("error")
        if type(error) is str:
            return {
                "missing_scope": "slack_missing_scope",
                "not_in_channel": "slack_channel_not_member",
                "channel_not_found": "slack_channel_unavailable",
                "ratelimited": "slack_rate_limited",
                "rate_limited": "slack_rate_limited",
                "invalid_auth": "slack_auth_failed",
                "not_authed": "slack_auth_failed",
                "token_revoked": "slack_auth_failed",
                "token_expired": "slack_auth_failed",
                "account_inactive": "slack_auth_failed",
            }.get(error, fallback)
    except Exception:
        pass
    return fallback


class Gate:
    def __init__(self, config, slack):
        self.config = config
        self.slack = slack

    def check(self, requester):
        c = self.config
        if not c.integration_approved or c.access_mode not in ("allowlist", "channel_members"):
            raise Refused("config_invalid")
        if (not identifier(requester, "[UW]") or requester == c.bot_user_id
                or (c.access_mode == "allowlist" and requester not in c.allowed_user_ids)):
            raise Refused("slack_member_not_allowed")
        members = self.snapshot()
        if requester not in members:
            raise Refused("slack_requester_not_member")
        return members

    def _read(self, method, unavailable, invalid, **kwargs):
        try:
            response = method(**kwargs)
        except Exception as error:
            # The SDK may attach a SlackResponse to an exception. Ignore its
            # body except for whitelisted error names/status; never print it.
            try:
                code = slack_failure_code(getattr(error, "response", None), unavailable)
            except Exception:
                code = unavailable
            raise Refused(code) from None
        try:
            ok = response.get("ok")
        except Exception:
            raise Refused(invalid) from None
        if ok is not True:
            code = slack_failure_code(response, unavailable) if ok is False else invalid
            raise Refused(code)
        return response

    def snapshot(self):
        """Fresh complete membership; used once per bounded read-only poll batch.

        This is not cached across batches or reused for a publication.
        """
        c = self.config
        if not c.integration_approved or c.access_mode not in ("allowlist", "channel_members"):
            raise Refused("config_invalid")
        invalid = "slack_auth_failed"
        try:
            auth = self._read(self.slack.auth_test, "slack_auth_failed", invalid)
            if (auth.get("team_id") != c.workspace_id
                    or auth.get("user_id") != c.bot_user_id
                    or auth.get("bot_id") != c.bot_id):
                raise Refused("slack_identity_mismatch")
            invalid = "slack_channel_metadata_invalid"
            response = self._read(self.slack.conversations_info,
                                  "slack_channel_unavailable", invalid, channel=c.channel_id)
            channel = response.get("channel")
            if not isinstance(channel, dict) or channel.get("id") != c.channel_id:
                raise Refused(invalid)
            if type(channel.get("is_private")) is not bool:
                raise Refused(invalid)
            if not channel["is_private"]:
                raise Refused("slack_channel_not_private")
            if "is_member" in channel:
                if type(channel["is_member"]) is not bool:
                    raise Refused(invalid)
                if not channel["is_member"]:
                    raise Refused("slack_channel_not_member")
            for key in ("is_archived", "is_shared", "is_ext_shared", "is_org_shared"):
                if type(channel.get(key)) is not bool:
                    raise Refused(invalid)
                if channel[key]:
                    raise Refused("slack_channel_not_safe")
            permitted = c.allowed_user_ids | {c.bot_user_id}
            members, cursors, cursor = set(), set(), ""
            invalid = "slack_membership_invalid"
            for _ in range(100):
                page = self._read(self.slack.conversations_members,
                                  "slack_membership_unavailable", invalid,
                                  channel=c.channel_id, limit=200, cursor=cursor)
                users = page.get("members")
                metadata = page.get("response_metadata")
                if (not isinstance(users, list) or not users or not isinstance(metadata, dict)
                        or not isinstance(metadata.get("next_cursor"), str)
                        or any(not identifier(u, "[UW]") for u in users)):
                    raise Refused(invalid)
                if c.access_mode == "allowlist" and any(u not in permitted for u in users):
                    raise Refused("slack_member_not_allowed")
                members.update(users)
                cursor = metadata["next_cursor"]
                if not cursor:
                    if c.bot_user_id not in members:
                        raise Refused("slack_channel_not_member")
                    return frozenset(members)
                if cursor in cursors or len(cursor) > 2048:
                    raise Refused(invalid)
                cursors.add(cursor)
            raise Refused(invalid)
        except Refused:
            raise
        except Exception:
            raise Refused(invalid) from None


class Bridge:
    def __init__(self, config, store, slack, paperclip, clock=time.time, coordinator=None):
        self.config, self.store, self.slack, self.paperclip = config, store, slack, paperclip
        self.gate, self.clock = Gate(config, slack), clock
        self.coordinator = coordinator
        store.bind(config)

    def accept(self, envelope_id, payload):
        """Return normally for irrelevant input; raise if durable queue fails.

        The Socket Mode adapter acknowledges only after this function returns.
        No external call or raw payload retention occurs here.
        """
        c = self.config
        if (not isinstance(payload, dict) or not c.integration_approved
                or c.access_mode not in ("allowlist", "channel_members")
                or c.interaction_mode not in ("proposal", "conversation")):
            return
        e = payload.get("event")
        if (payload.get("type") != "event_callback"
                or payload.get("team_id") != c.workspace_id
                or payload.get("api_app_id") != c.app_id or not isinstance(e, dict)):
            return
        authorizations = payload.get("authorizations")
        if not isinstance(authorizations, list) or len(authorizations) != 1:
            return
        auth = authorizations[0]
        if (not isinstance(auth, dict) or auth.get("team_id") != c.workspace_id
                or auth.get("user_id") != c.bot_user_id or auth.get("is_bot") is not True):
            return
        if (e.get("type") != "app_mention" or e.get("channel") != c.channel_id
                or not identifier(e.get("user"), "[UW]")
                or (c.access_mode == "allowlist" and e["user"] not in c.allowed_user_ids)
                or e.get("user") == c.bot_user_id
                or any(k in e for k in ("subtype", "bot_id", "bot_profile"))
                or e.get("channel_type") in ("im", "mpim")):
            return
        text = e.get("text")
        if (not isinstance(text, str) or not 1 <= len(text) <= 4096
                or "\x00" in text or f"<@{c.bot_user_id}>" not in text):
            return
        try:
            if len(text.encode("utf-8")) > 16384:
                return
        except UnicodeEncodeError:
            return
        event_id = payload.get("event_id")
        thread = e.get("thread_ts", e.get("ts"))
        if (not isinstance(event_id, str)
                or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", event_id)
                or not isinstance(envelope_id, str)
                or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", envelope_id)
                or not isinstance(e.get("ts"), str)
                or not re.fullmatch(r"\d{10,16}\.\d{6}", e["ts"])
                or not isinstance(thread, str)
                or not re.fullmatch(r"\d{10,16}\.\d{6}", thread)):
            return
        after_mention = text.split(f"<@{c.bot_user_id}>", 1)[1].lstrip()
        if c.interaction_mode == "conversation" and not after_mention.startswith("task:"):
            prompt = text.replace(f"<@{c.bot_user_id}>", "").strip()
            self.store.accept_chat(envelope_id, event_id, thread, e["user"], prompt, self.clock())
        else:
            self.store.accept(envelope_id, event_id, thread, e["user"], text, self.clock())

    def _send(self, key, proposal, requester, text, terminal=False, contributors=frozenset()):
        # A spent receipt causes no action, so needs no external authorization
        # calls. Every actual publication still gets a fresh complete gate.
        if self.store.has_delivery(key):
            if terminal:
                self.store.stop_polling(proposal["thread"])
            return
        members = self.gate.check(requester)
        if not contributors <= members:
            raise Refused("slack_requester_not_member")
        if not self.store.begin_delivery(key, proposal["thread"], terminal):
            return
        try:
            reply = self.slack.chat_postMessage(
                channel=self.config.channel_id, thread_ts=proposal["thread"],
                text=text, mrkdwn=False, parse="none", unfurl_links=False,
                unfurl_media=False, link_names=False,
            )
            # A truncated/odd response is not proof of failure. Hold, don't retry.
            if (reply.get("ok") is not True
                    or reply.get("channel") != self.config.channel_id
                    or not isinstance(reply.get("ts"), str)):
                raise Refused()
        except Exception as error:
            delay = retry_after(error)
            self.store.delivery_finished(
                key, "rate_limited" if delay is not None else "uncertain", delay)
            return
        self.store.delivery_finished(key, "sent")

    def work_once(self):
        self.store.expire_pending(self.clock())
        self.store.expire_chats(self.clock())
        event = self.store.pending_event()
        if event is None:
            return self._work_chat()
        p = self.store.proposal(event["thread"])
        if event["kind"] == "initial" and p["state"] == "pending":
            if self.clock() - p["received"] >= 3600:
                self.store.reject(p["thread"])
            else:
                try:
                    self.gate.check(event["requester"])
                    self.paperclip.check_safe()
                    self.gate.check(event["requester"])
                except Exception:
                    self.store.reject(p["thread"])
                else:
                    self.store.expire_pending(self.clock())
                    creating = self.store.begin_create(p["thread"])
                    if creating is not None:
                        try:
                            issue = self.paperclip.create_proposal(
                                creating["text"], p["thread"])
                        except RateLimited as error:
                            self.store.create_failed(p["thread"], error.retry_after)
                        except Exception:
                            self.store.create_failed(p["thread"])
                        else:
                            self.store.created(p["thread"], issue)
            p = self.store.proposal(event["thread"])
        if p["state"] == "created":
            # Never append later mentions to the issue, even after assignment.
            text = ("Proposal queued for human review. No agent was assigned by this bridge. "
                    if event["kind"] == "initial" else
                    "This thread already has a proposal. New text was not sent to the task. ")
            text += self.paperclip.issue_url(p["issue_identifier"])
            try:
                self._send("event:" + event["id"], p, event["requester"], text)
            except Refused:
                pass
        self.store.finish_event(event["id"])
        return True

    def _chat_notice(self, turn):
        try:
            self._send("chat:" + turn["id"], turn, turn["requester"], CHAT_UNAVAILABLE)
        except Refused:
            pass

    def _work_chat(self):
        turn = self.store.pending_chat()
        if turn is None:
            return False
        if (self.config.interaction_mode != "conversation" or self.coordinator is None
                or turn["mode"] != "conversation"):
            self.store.finish_chat(turn["id"], "rejected")
            return True
        try:
            members = self.gate.check(turn["requester"])
        except Refused:
            self.store.finish_chat(turn["id"], "rejected")
            return True
        prompt = turn["prompt"]
        if isinstance(prompt, str):
            prompt = prompt.replace(f"<@{self.config.bot_user_id}>", "").strip()
        if not bounded_text(prompt, 4096, 16384):
            self.store.finish_chat(turn["id"], "failed")
            self._chat_notice(turn)
            return True
        history, contributors = self.store.chat_history(
            turn["thread"], members, self.clock(), f"<@{self.config.bot_user_id}>")
        ready = self.store.begin_chat(turn["id"], self.clock())
        if ready is None:
            if self.store.chat_turn(turn["id"])["state"] == "rate_limited":
                self._chat_notice(turn)
            return True
        try:
            reply = self.coordinator.query(prompt, history)
            if not bounded_text(reply, 3000, 12000):
                raise Refused()
        except Exception:
            self.store.finish_chat(turn["id"], "failed")
            self._chat_notice(turn)
            return True
        try:
            self._send("chat:" + turn["id"], turn, turn["requester"],
                       html.escape(reply, quote=False) + DRAFT_SUFFIX, contributors=contributors)
        except Refused:
            self.store.finish_chat(turn["id"], "rejected")
        else:
            if self.store.delivery_state("chat:" + turn["id"]) == "sent":
                self.store.chat_sent(turn["id"], prompt, reply, self.clock())
            else:
                self.store.finish_chat(turn["id"], "uncertain")
        return True

    def poll_statuses(self):
        self.store.expire_pending(self.clock())
        self.store.expire_chats(self.clock())
        proposals = self.store.poll_batch()
        if not proposals:
            return
        try:
            # One fresh read-side snapshot per bounded batch, not per issue.
            # A publication always takes its own fresh complete Gate below.
            members = self.gate.snapshot()
        except Refused:
            return
        for p in proposals:
            self.store.expire_pending(self.clock())
            self.store.expire_chats(self.clock())
            if p["requester"] not in members:
                continue
            try:
                status = self.paperclip.status(p["issue_id"])
                if status not in ("in_review", "done", "blocked", "cancelled"):
                    continue
                text = ("Proposal status: " + status + ". "
                        + self.paperclip.issue_url(p["issue_identifier"]))
                self._send("status:" + p["thread"] + ":" + status, p, p["requester"], text,
                           terminal=status in ("done", "cancelled"))
            except Refused:
                continue

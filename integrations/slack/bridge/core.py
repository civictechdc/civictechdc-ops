"""Mention-only intake, authorization gates, and fixed notifications.

Slack and Paperclip clients are explicit constructor arguments, not plugins.
No model, shell, agent, comment, file, search, or history interfaces exist here.
"""

import re
import time

from .config import Refused


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


class Gate:
    def __init__(self, config, slack):
        self.config = config
        self.slack = slack

    def check(self, requester):
        c = self.config
        if not c.integration_approved or requester not in c.allowed_user_ids:
            raise Refused()
        if requester not in self.snapshot():
            raise Refused()

    def snapshot(self):
        """Fresh complete membership; used once per bounded read-only poll batch.

        This is not cached across batches or reused for a publication.
        """
        c = self.config
        if not c.integration_approved:
            raise Refused()
        try:
            auth = self.slack.auth_test()
            if (auth.get("ok") is not True or auth.get("team_id") != c.workspace_id
                    or auth.get("user_id") != c.bot_user_id
                    or auth.get("bot_id") != c.bot_id):
                raise Refused()
            response = self.slack.conversations_info(channel=c.channel_id)
            channel = response.get("channel", {})
            if (response.get("ok") is not True or channel.get("id") != c.channel_id
                    or channel.get("is_private") is not True
                    or ("is_member" in channel and channel["is_member"] is not True)
                    or any(channel.get(k) is not False for k in (
                        "is_archived", "is_shared", "is_ext_shared", "is_org_shared"))):
                raise Refused()
            permitted = c.allowed_user_ids | {c.bot_user_id}
            members, cursors, cursor = set(), set(), ""
            for _ in range(100):
                page = self.slack.conversations_members(
                    channel=c.channel_id, limit=200, cursor=cursor)
                users = page.get("members")
                metadata = page.get("response_metadata")
                if (page.get("ok") is not True or not isinstance(users, list)
                        or not users or not isinstance(metadata, dict)
                        or not isinstance(metadata.get("next_cursor"), str)
                        or any(not isinstance(u, str) or u not in permitted for u in users)):
                    raise Refused()
                members.update(users)
                cursor = metadata["next_cursor"]
                if not cursor:
                    if c.bot_user_id not in members:
                        raise Refused()
                    return frozenset(members)
                if cursor in cursors or len(cursor) > 2048:
                    raise Refused()
                cursors.add(cursor)
            raise Refused()
        except Exception:
            raise Refused() from None


class Bridge:
    def __init__(self, config, store, slack, paperclip, clock=time.time):
        self.config, self.store, self.slack, self.paperclip = config, store, slack, paperclip
        self.gate, self.clock = Gate(config, slack), clock
        store.bind(config)

    def accept(self, envelope_id, payload):
        """Return normally for irrelevant input; raise if durable queue fails.

        The Socket Mode adapter acknowledges only after this function returns.
        No external call or raw payload retention occurs here.
        """
        c = self.config
        if not isinstance(payload, dict) or not c.integration_approved:
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
                or not isinstance(e.get("user"), str)
                or e.get("user") not in c.allowed_user_ids
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
        self.store.accept(envelope_id, event_id, thread, e["user"], text, self.clock())

    def _send(self, key, proposal, requester, text, terminal=False):
        # A spent receipt causes no action, so needs no external authorization
        # calls. Every actual publication still gets a fresh complete gate.
        if self.store.has_delivery(key):
            if terminal:
                self.store.stop_polling(proposal["thread"])
            return
        self.gate.check(requester)
        if not self.store.begin_delivery(key, proposal["thread"], terminal):
            return
        try:
            reply = self.slack.chat_postMessage(
                channel=self.config.channel_id, thread_ts=proposal["thread"],
                text=text, mrkdwn=False, parse="none", unfurl_links=False,
                unfurl_media=False,
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
        event = self.store.pending_event()
        if event is None:
            return False
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

    def poll_statuses(self):
        self.store.expire_pending(self.clock())
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

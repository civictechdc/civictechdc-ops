"""Explicit private configuration. Core code never reads the environment."""

from dataclasses import dataclass
import re
import os
from urllib.parse import urlsplit
from uuid import UUID


PREFLIGHT_CODES = frozenset({
    "config_invalid", "credentials_missing", "dependency_unavailable",
    "slack_auth_failed", "slack_identity_mismatch", "slack_channel_unavailable",
    "slack_missing_scope", "slack_channel_not_private", "slack_channel_not_member",
    "slack_channel_not_safe", "slack_channel_metadata_invalid",
    "slack_member_not_allowed", "slack_requester_not_member",
    "slack_membership_unavailable", "slack_membership_invalid", "slack_rate_limited",
    "paperclip_preflight_failed", "validation_failed",
})


class Refused(Exception):
    """Boundary failure containing only a fixed, validated diagnostic code."""

    def __init__(self, code="validation_failed"):
        self.code = code if type(code) is str and code in PREFLIGHT_CODES else "validation_failed"
        super().__init__(self.code)


def identifier(value, prefix):
    return isinstance(value, str) and re.fullmatch(prefix + r"[A-Z0-9]{2,63}", value)


def base_url(value, api=False):
    if (not isinstance(value, str)
            or any(ord(ch) <= 32 or ord(ch) >= 127 for ch in value)
            or any(ch in value for ch in "<>\\\"'?#")):
        raise Refused()
    parsed = urlsplit(value)
    parsed.port  # Reject malformed or out-of-range ports.
    local_http = parsed.scheme == "http" and parsed.hostname in ("127.0.0.1", "::1")
    if ((parsed.scheme != "https" and not local_http)
            or not parsed.hostname or not (
                re.fullmatch(r"[A-Za-z0-9.-]+", parsed.hostname) or parsed.hostname == "::1")
            or parsed.username or parsed.password
            or parsed.query or parsed.fragment
            or parsed.path not in (("/api", "/api/") if api else ("", "/"))):
        raise Refused()
    # This initial adapter has no Paperclip credential. Restrict its trust
    # boundary to local-trust loopback, never an unauthenticated remote API.
    if api and not local_http:
        raise Refused()
    return value.rstrip("/")


@dataclass(frozen=True)
class Config:
    workspace_id: str
    app_id: str
    bot_user_id: str
    bot_id: str
    channel_id: str
    allowed_user_ids: frozenset
    company_id: str
    company_prefix: str
    paperclip_api_url: str
    paperclip_public_url: str
    state_path: str
    poll_interval_seconds: int
    integration_approved: bool

    @classmethod
    def parse(cls, data):
        try:
            if set(data) != set(cls.__dataclass_fields__):
                raise Refused()
            for key, prefix in (("workspace_id", "T"), ("app_id", "A"),
                                ("bot_user_id", "[UW]"), ("bot_id", "B"),
                                ("channel_id", "[CG]")):
                if not identifier(data[key], prefix):
                    raise Refused()
            humans = data["allowed_user_ids"]
            if (not isinstance(humans, list) or not 1 <= len(humans) <= 50
                    or any(not identifier(u, "[UW]") for u in humans)
                    or len(set(humans)) != len(humans)
                    or data["bot_user_id"] in humans):
                raise Refused()
            company = str(UUID(data["company_id"]))
            if not re.fullmatch(r"[A-Z][A-Z0-9]{1,15}", data["company_prefix"]):
                raise Refused()
            if (not isinstance(data["state_path"], str)
                    or not os.path.isabs(data["state_path"])
                    or data["state_path"].endswith("/")):
                raise Refused()
            interval = data["poll_interval_seconds"]
            if type(interval) is not int or not 30 <= interval <= 3600:
                raise Refused()
            if data["integration_approved"] is not True:
                raise Refused()
            return cls(
                **{k: data[k] for k in (
                    "workspace_id", "app_id", "bot_user_id", "bot_id", "channel_id")},
                allowed_user_ids=frozenset(humans), company_id=company,
                company_prefix=data["company_prefix"],
                paperclip_api_url=base_url(data["paperclip_api_url"], api=True),
                paperclip_public_url=base_url(data["paperclip_public_url"]),
                state_path=data["state_path"], poll_interval_seconds=interval,
                integration_approved=True,
            )
        except (ValueError, TypeError, KeyError, AttributeError):
            raise Refused() from None

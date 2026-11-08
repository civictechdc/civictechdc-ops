#!/usr/bin/env python3
"""Private operator entry point; also works with python -I and any source-dir name."""

import argparse
import fcntl
import importlib.util
import json
import logging
import os
from pathlib import Path
import stat
import sys
import threading
import time

# Load only this package, never the caller's current directory or home.
sys.dont_write_bytecode = True
_source = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location(
    "_approval_slack_bridge", _source / "__init__.py",
    submodule_search_locations=[str(_source)],
)
_package = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _package
_spec.loader.exec_module(_package)
from _approval_slack_bridge.config import Config, PREFLIGHT_CODES, Refused  # noqa: E402
from _approval_slack_bridge.core import Bridge, Gate  # noqa: E402
from _approval_slack_bridge.paperclip import Paperclip  # noqa: E402
from _approval_slack_bridge.store import Store  # noqa: E402


def private_file(path, flags=os.O_RDONLY, settings=False):
    fd = os.open(path, flags | os.O_NOFOLLOW, 0o600)
    info = os.fstat(fd)
    owned = info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o600
    root_settings = (
        settings and os.geteuid() != 0 and info.st_uid == 0
        and info.st_gid == os.getegid() and stat.S_IMODE(info.st_mode) == 0o640
    )
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not (owned or root_settings):
        os.close(fd)
        raise Refused()
    return fd


def load_config(path):
    with os.fdopen(private_file(path, settings=True)) as source:
        raw = source.read(16385)
    if len(raw) > 16384:
        raise Refused()
    config = Config.parse(json.loads(raw))
    parent = Path(config.state_path).parent
    info = parent.stat()
    if (not parent.is_dir() or parent.is_symlink()
            or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700):
        raise Refused()
    if os.path.lexists(config.state_path):
        os.close(private_file(config.state_path))
    return config


def dispatch(client, request, accept, response_type):
    """Queue before acknowledging; injectable only to test the SDK callback order."""
    if request.type != "events_api":
        return
    try:
        accept(request.envelope_id, request.payload)
    except Exception:
        sys.stderr.write("intake_not_acknowledged\n")
        return
    try:
        client.send_socket_mode_response(response_type(envelope_id=request.envelope_id))
    except Exception:
        # Slack may replay; the committed envelope/event IDs absorb the replay.
        sys.stderr.write("envelope_ack_uncertain\n")


def main():
    parser = argparse.ArgumentParser(description="Approval-first, mention-only Slack intake")
    parser.add_argument("command", choices=("check", "run"))
    parser.add_argument("--config", required=True, metavar="PRIVATE_JSON")
    args = parser.parse_args()
    # No third-party logs, exception repr, traceback, payload or HTTP response.
    logging.disable(logging.CRITICAL)
    logger = logging.getLogger("approval_slack_bridge")
    logger.disabled = True
    sys.excepthook = lambda *_: sys.stderr.write("bridge_failed_closed\n")
    threading.excepthook = lambda *_: sys.stderr.write("background_failed_closed\n")
    store, socket_client, lock_fd = None, None, None
    phase = "config_invalid"
    try:
        config = load_config(args.config)
        # This is the only process environment boundary.
        phase = "credentials_missing"
        bot_token = os.environ.get("SLACK_BOT_TOKEN", "")
        app_token = os.environ.get("SLACK_APP_TOKEN", "")
        if not bot_token.startswith("xoxb-") or not app_token.startswith("xapp-"):
            raise Refused("credentials_missing")
        phase = "dependency_unavailable"
        from slack_sdk import WebClient
        from slack_sdk.socket_mode import SocketModeClient
        from slack_sdk.socket_mode.response import SocketModeResponse
        phase = "validation_failed"
        slack = WebClient(token=bot_token, retry_handlers=[], timeout=10, logger=logger)
        # Read-only preflight. "check" never opens the DB or lock file, or socket.
        for requester in sorted(config.allowed_user_ids):
            Gate(config, slack).check(requester)
        phase = "paperclip_preflight_failed"
        paperclip = Paperclip(config)
        paperclip.check_safe()
        if args.command == "check":
            print("preflight_ok_read_only")
            return 0
        lock_fd = private_file(config.state_path + ".lock", os.O_RDWR | os.O_CREAT)
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        store = Store(config.state_path)
        store.bind(config)
        store.recover()
        bridge = Bridge(config, store, slack, paperclip)
        socket_client = SocketModeClient(
            app_token=app_token, web_client=slack, logger=logger)
        socket_client.socket_mode_request_listeners.append(
            lambda client, request: dispatch(
                client, request, bridge.accept, SocketModeResponse))
        socket_client.connect()
        next_poll = time.monotonic() + config.poll_interval_seconds
        stopped = threading.Event()
        print("bridge_running_proposal_only", flush=True)
        while not stopped.is_set():
            worked = bridge.work_once()
            if time.monotonic() >= next_poll:
                bridge.poll_statuses()
                next_poll = time.monotonic() + config.poll_interval_seconds
            if not worked:
                stopped.wait(0.25)
    except KeyboardInterrupt:
        if args.command == "check":
            sys.stderr.write("preflight_failed:validation_failed\n")
            return 1
        return 0
    except Exception as error:
        if args.command == "check":
            # Only our validated code type may override a fixed phase. Do not
            # trust arbitrary exception.code/args, SDK errors, or response text.
            code = getattr(error, "code", None) if type(error) is Refused else None
            if type(code) is not str or code not in PREFLIGHT_CODES or code == "validation_failed":
                code = phase
            sys.stderr.write("preflight_failed:" + code + "\n")
        else:
            sys.stderr.write("bridge_failed_closed\n")
        return 1
    finally:
        if socket_client is not None:
            try:
                socket_client.close()
            except Exception:
                pass
        if store is not None:
            store.close()
        if lock_fd is not None:
            os.close(lock_fd)


if __name__ == "__main__":
    raise SystemExit(main())

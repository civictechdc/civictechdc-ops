"""Bounded Unix RPC only; no model SDK, subprocess, HTTP, or credential access."""

import json
import os
from pathlib import Path
import socket
import stat
import time

from .config import socket_path

MAX_WIRE = 65536
WORKER_ERRORS = frozenset({
    "invalid_request", "rate_limited", "timeout", "unavailable", "generation_failed",
})


class CoordinatorError(Exception):
    def __init__(self, code="unavailable"):
        self.code = code if type(code) is str and code in WORKER_ERRORS else "unavailable"
        super().__init__(self.code)


def bounded_text(value, chars, utf8):
    if not isinstance(value, str) or not 1 <= len(value) <= chars or "\x00" in value:
        return False
    try:
        return len(value.encode("utf-8")) <= utf8
    except UnicodeEncodeError:
        return False


def validate_request(text, history):
    if not bounded_text(text, 4096, 16384) or not isinstance(history, list) or len(history) > 6:
        raise CoordinatorError("invalid_request")
    if len(history) % 2:
        raise CoordinatorError("invalid_request")
    chars = size = 0
    for index, message in enumerate(history):
        if (not isinstance(message, dict) or set(message) != {"role", "content"}
                or message["role"] != ("user" if index % 2 == 0 else "assistant")
                or not bounded_text(message["content"], 6000, 24000)):
            raise CoordinatorError("invalid_request")
        chars += len(message["content"])
        size += len(message["content"].encode("utf-8"))
    if chars > 6000 or size > 24000:
        raise CoordinatorError("invalid_request")
    return {"version": 1, "text": text, "history": history}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise CoordinatorError()
        result[key] = value
    return result


class Coordinator:
    def __init__(self, path):
        self.path = path

    def check(self):
        """Stat only: never connect, activate a worker, or invoke a model."""
        try:
            if not socket_path(self.path):
                raise CoordinatorError()
            path = Path(self.path)
            for parent in reversed(path.parents):
                info = parent.lstat()
                if (not stat.S_ISDIR(info.st_mode) or info.st_uid != 0
                        or stat.S_IMODE(info.st_mode) & 0o022):
                    raise CoordinatorError()
            info = path.lstat()
            if (not stat.S_ISSOCK(info.st_mode) or info.st_uid != 0
                    or info.st_gid != os.getegid() or stat.S_IMODE(info.st_mode) != 0o660):
                raise CoordinatorError()
        except Exception:
            raise CoordinatorError() from None

    def query(self, text, history):
        try:
            request = validate_request(text, history)
            wire = (json.dumps(request, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
            if len(wire) > MAX_WIRE:
                raise CoordinatorError("invalid_request")
            self.check()
            deadline = time.monotonic() + 120
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as transport:
                transport.settimeout(120)
                transport.connect(self.path)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise CoordinatorError("timeout")
                transport.settimeout(remaining)
                transport.sendall(wire)
                data = bytearray()
                while b"\n" not in data:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise CoordinatorError("timeout")
                    transport.settimeout(remaining)
                    chunk = transport.recv(min(4096, MAX_WIRE + 1 - len(data)))
                    if not chunk:
                        raise CoordinatorError()
                    data.extend(chunk)
                    if len(data) > MAX_WIRE:
                        raise CoordinatorError()
                line, trailing = bytes(data).split(b"\n", 1)
                if trailing:
                    raise CoordinatorError()
            response = json.loads(line.decode("utf-8"), object_pairs_hook=unique_object)
            if (not isinstance(response, dict) or type(response.get("version")) is not int
                    or response["version"] != 1 or type(response.get("ok")) is not bool):
                raise CoordinatorError()
            if response["ok"] is False:
                if set(response) != {"version", "ok", "error"}:
                    raise CoordinatorError()
                raise CoordinatorError(response["error"])
            if (set(response) != {"version", "ok", "text"}
                    or not bounded_text(response["text"], 3000, 12000)):
                raise CoordinatorError()
            return response["text"]
        except CoordinatorError:
            raise
        except (TimeoutError, socket.timeout):
            raise CoordinatorError("timeout") from None
        except Exception:
            raise CoordinatorError() from None

#!/usr/bin/env python3
"""Read-only diagnostic observer for the modern Hermes /v1/runs API.

Does not start/stop runs, approve tools, access model content, or modify
Hermes state. Derived JSONL is NOT authoritative; canonical status belongs
to Hermes. The script runs only while its process is running.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import uuid

_RUN_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_TERMINAL = frozenset({"completed", "failed", "cancelled", "interrupted"})
_ACTIVE = frozenset({"running", "queued", "stopping"})
_ALLOWED_STATUS = _TERMINAL | _ACTIVE | frozenset({
    "waiting_for_approval", "unknown",
})
_SAFE_EVENT = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")
_MAX_RESPONSE_BYTES = 256 * 1024


class UnsupportedContract(RuntimeError):
    """Target gateway does not expose the modern run observation contract."""


def validate_origin(base_url: str, allow_remote: bool = False) -> str:
    """Enforce an explicit opt-in for remote HTTPS, never remote plaintext."""
    u = urlsplit(base_url)
    if (u.scheme not in ("http", "https") or not u.hostname
            or u.username is not None or u.password is not None
            or u.query or u.fragment or u.path not in ("", "/")):
        raise ValueError("Expected scheme://host[:port] without credentials or path")
    local = u.hostname in ("localhost", "127.0.0.1", "::1")
    if not local and (not allow_remote or u.scheme != "https"):
        raise ValueError("Remote observer requires --allow-remote and HTTPS")
    return base_url.rstrip("/")


def validate_run_id(run_id: str) -> str:
    if not _RUN_ID.fullmatch(run_id):
        raise ValueError("Invalid run ID; only ASCII letters, digits, _ and -")
    return run_id


def get_json(base_url: str, path: str, api_key: str, timeout: float = 8) -> dict:
    """Bounded GET, fail without returning body or credentials on transport errors."""
    headers = {"Accept": "application/json", "User-Agent": "HermesReadOnlyRunObserver/0.1"}
    if api_key:
        headers["Authorization"] = "Bearer " + api_key
    with urlopen(Request(base_url + path, headers=headers, method="GET"),
                 timeout=timeout) as response:
        raw = response.read(_MAX_RESPONSE_BYTES + 1)
    if len(raw) > _MAX_RESPONSE_BYTES:
        raise ValueError("Response exceeds safe size limit")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("Expected JSON object")
    return parsed


def safe_projection(value: dict) -> dict:
    """Never retain prompts, tool payloads, errors or arbitrary provider fields."""
    state = value.get("status")
    if not isinstance(state, str) or state not in _ALLOWED_STATUS:
        state = "unrecognized"
    last = value.get("last_event")
    if not isinstance(last, str) or not _SAFE_EVENT.fullmatch(last):
        last = None
    return {
        "status": state,
        "last_event": last,
        "has_error": bool(value.get("error")),
        "has_pending_controls": bool(value.get("pending_controls")),
    }


def extract_features(capabilities: dict) -> tuple[bool, bool]:
    """Return (run_status_supported, durable_idempotency_available)."""
    features = capabilities.get("features")
    if not isinstance(features, dict):
        return False, False
    idem = features.get("runs_idempotency")
    durable = isinstance(idem, dict) and idem.get("durable") is True
    return features.get("run_status") is True, durable


def make_event(kind: str, run_id: str, **metadata) -> dict:
    # All metadata below must originate only from local constants or safe_projection.
    return {
        "schema": "hermes.gpt.observer.v1",
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "event_id": uuid.uuid4().hex,
        "run_id": run_id,
        "kind": kind,
        **metadata,
    }


class JsonlRunLog:
    """Private, unique-per-observer file. One write and fsync per event.

    A separate unique file per instance avoids competing process writers.
    This is an observational log, not a transactional operations ledger.
    """

    def __init__(self, log_dir: Path, run_id: str):
        validate_run_id(run_id)
        log_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        name = f"run-{run_id}-{uuid.uuid4().hex[:12]}.jsonl"
        self.path = log_dir / name
        self._fd = os.open(str(self.path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)

    def append(self, event: dict) -> None:
        encoded = (json.dumps(event, ensure_ascii=False, separators=(",", ":"))
                   + "\n").encode("utf-8")
        if len(encoded) > 4096:
            raise ValueError("Observer event too large")
        offset = 0
        while offset < len(encoded):
            n = os.write(self._fd, encoded[offset:])
            if n <= 0:
                raise OSError("Unable to write observer event")
            offset += n
        os.fsync(self._fd)

    def close(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class RunObserver:
    """Poll run state without altering the provider, and explain suspected stalls."""

    def __init__(self, run_id: str, emit, *, stale_seconds: float = 120):
        self.run_id = validate_run_id(run_id)
        self.emit = emit
        self.stale_seconds = float(stale_seconds)
        self.last_projection = None
        self.last_change_at = time.monotonic()
        self.last_heartbeat_at = None
        self.stale_reported = False
        if self.stale_seconds < 1:
            raise ValueError("stale_seconds must be >= 1")

    def observe(self, raw: dict, *, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        value = safe_projection(raw)
        if self.last_heartbeat_at is None:
            self.last_heartbeat_at = now
        elif now - self.last_heartbeat_at >= 30:
            # Distinguish a live observer from a stalled or dead observer.
            # This heartbeat says NOTHING about Hermes worker health.
            self.emit(make_event(
                "observer_heartbeat", self.run_id,
                status=value["status"],
                progress_age_seconds=round(max(0, now - self.last_change_at), 1),
            ))
            self.last_heartbeat_at = now
        if self.last_projection != value:
            prev = self.last_projection
            self.emit(make_event(
                "state_observed", self.run_id,
                previous_status=prev["status"] if prev else None,
                **value,
            ))
            self.last_projection = value
            self.last_change_at = now
            self.stale_reported = False
        elif (value["status"] == "running" and not self.stale_reported
              and now - self.last_change_at >= self.stale_seconds):
            self.emit(make_event(
                "progress_stale_suspected", self.run_id,
                status=value["status"], reason_code="NO_OBSERVED_PROGRESS",
                uncertainty="may be long-running tool or LLM call",
            ))
            self.stale_reported = True
        return value["status"] in _TERMINAL


def default_log_dir() -> Path:
    try:
        from hermes_cli.config import get_hermes_home
        home = Path(get_hermes_home())
    except ImportError:
        home = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes")))
    return home / "logs" / "gpt_run_observer"


def monitor(
    base_url: str, run_id: str, *,
    api_key: str = "", poll_seconds: float = 2.0,
    stale_seconds: float = 120.0, max_seconds: float | None = None,
    log_dir: Path | None = None, fetch=get_json, sleep=time.sleep,
) -> tuple[int, Path]:
    """Return (exit code, unique log path); exit 0 only on observed terminal state.

    Exit 2: incompatible capabilities; 3: stopped or transport unavailable
    through a configured deadline. Never infer run failure from observer exit.
    """
    if poll_seconds < .2 or (max_seconds is not None and max_seconds <= 0):
        raise ValueError("Invalid polling interval or duration")
    with JsonlRunLog(log_dir or default_log_dir(), run_id) as journal:
        observer = RunObserver(run_id, journal.append, stale_seconds=stale_seconds)
        journal.append(make_event("observer_started", run_id))
        try:
            caps = fetch(base_url, "/v1/capabilities", api_key)
            supported, durable = extract_features(caps)
            if not supported:
                journal.append(make_event(
                    "unsupported_capabilities", run_id,
                    reason_code="RUN_STATUS_NOT_ADVERTISED",
                ))
                return 2, journal.path
            if not durable:
                journal.append(make_event(
                    "durability_warning", run_id,
                    reason_code="RUN_IDEMPOTENCY_NOT_DURABLE",
                ))
            started = time.monotonic()
            failures = 0
            while True:
                try:
                    raw = fetch(base_url, "/v1/runs/" + run_id, api_key)
                    failures = 0
                    if observer.observe(raw):
                        journal.append(make_event("terminal_observed", run_id))
                        return 0, journal.path
                except HTTPError as exc:
                    # Status code only; never record request/response body.
                    failures += 1
                    journal.append(make_event(
                        "transport_error", run_id,
                        reason_code="HTTP_ERROR", http_status=int(exc.code),
                        consecutive_failures=failures,
                    ))
                except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
                    failures += 1
                    journal.append(make_event(
                        "transport_error", run_id,
                        reason_code="NETWORK_OR_CONTRACT_ERROR",
                        consecutive_failures=failures,
                    ))
                if max_seconds is not None and time.monotonic() - started >= max_seconds:
                    journal.append(make_event(
                        "observer_deadline_reached", run_id,
                        reason_code="OBSERVER_DEADLINE_NOT_RUN_FAILURE",
                    ))
                    return 3, journal.path
                sleep(min(poll_seconds * (2 ** min(failures, 3)), 30.0))
        except HTTPError as exc:
            journal.append(make_event("capability_probe_failed", run_id,
                                      http_status=int(exc.code)))
            return 2, journal.path
        except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
            journal.append(make_event("capability_probe_failed", run_id,
                                      reason_code="UNAVAILABLE_OR_INVALID"))
            return 2, journal.path
        except KeyboardInterrupt:
            journal.append(make_event("observer_interrupted", run_id,
                                      reason_code="LOCAL_OBSERVER_STOPPED"))
            return 3, journal.path


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-id", required=True)
    p.add_argument("--base-url", default="http://127.0.0.1:8642")
    p.add_argument("--poll-seconds", type=float, default=2.0)
    p.add_argument("--stale-seconds", type=float, default=120.0)
    p.add_argument("--max-seconds", type=float)
    p.add_argument("--log-dir", type=Path)
    p.add_argument("--allow-remote", action="store_true")
    args = p.parse_args(argv)
    try:
        url = validate_origin(args.base_url, args.allow_remote)
        rid = validate_run_id(args.run_id)
        code, path = monitor(
            url, rid, api_key=os.environ.get("HERMES_OBSERVER_API_KEY", ""),
            poll_seconds=args.poll_seconds, stale_seconds=args.stale_seconds,
            max_seconds=args.max_seconds, log_dir=args.log_dir,
        )
    except (ValueError, OSError) as exc:
        print("Observer configuration/storage error: " + type(exc).__name__, file=sys.stderr)
        return 4
    print(f"Observer exit={code}; derived metadata log={path}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Read-only Hermes native Runs capability probe for an explicitly selected LOOPBACK listener.

No POST, tool execution, user prompts, cookies, redirects, proxy, or remote hosts.
A passing feature negotiation is NOT proof that the installed Hermes is safe to run.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

MAX_BYTES = 512 * 1024
MIN_CONTROL_RETENTION_SECONDS = 24 * 60 * 60
PROFILE = re.compile(r"^/p/[A-Za-z0-9_-]{1,64}$")
ROUTES = {
    "runs": ("POST", "/v1/runs"),
    "run_status": ("GET", "/v1/runs/{run_id}"),
    "run_events": ("GET", "/v1/runs/{run_id}/events"),
    "run_stop": ("POST", "/v1/runs/{run_id}/stop"),
    "run_unknown_resolution": ("POST", "/v1/runs/{run_id}/resolve-unknown"),
}

class ProbeError(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None

def normalize_base_url(raw):
    """Permit only numeric loopback IPv4/IPv6 and explicit port, with optional safe profile."""
    if not isinstance(raw, str):
        raise ProbeError("INVALID_LOCAL_URL")
    try:
        p = urllib.parse.urlsplit(raw)
        port = p.port
    except ValueError:
        raise ProbeError("INVALID_LOCAL_URL") from None
    if (p.scheme not in ("http", "https") or p.hostname not in ("127.0.0.1", "::1")
            or port is None or not 1 <= port <= 65535 or p.username is not None
            or p.password is not None or p.query or p.fragment
            or p.path not in ("", "/") and not PROFILE.fullmatch(p.path)):
        raise ProbeError("NON_LOOPBACK_OR_UNSAFE_URL")
    if p.netloc.startswith("["):
        authority = "[" + p.hostname + "]:" + str(port)
    else:
        authority = p.hostname + ":" + str(port)
    return p.scheme + "://" + authority + (p.path if p.path not in ("", "/") else "")

def evaluate_capabilities(raw):
    """Assess only a strict, source-matched API shape; never authorize execution."""
    if (not isinstance(raw, dict)
            or raw.get("object") != "hermes.api_server.capabilities"
            or raw.get("platform") != "hermes-agent"
            or not isinstance(raw.get("features"), dict)
            or not isinstance(raw.get("endpoints"), dict)
            or not isinstance(raw.get("auth"), dict)):
        raise ProbeError("UNSUPPORTED_CAPABILITIES_SCHEMA")
    flags, endpoints, auth = raw["features"], raw["endpoints"], raw["auth"]
    if type(auth.get("required")) is not bool or auth.get("type") != "bearer":
        raise ProbeError("INVALID_AUTH_CAPABILITY")
    idem = flags.get("runs_idempotency")
    if idem is not None and not isinstance(idem, dict):
        raise ProbeError("INVALID_IDEMPOTENCY_CAPABILITY")
    idem = idem or {}
    advertised = {
        "run_submission": flags.get("run_submission") is True,
        "run_status": flags.get("run_status") is True,
        "run_events_sse": flags.get("run_events_sse") is True,
        "run_stop": flags.get("run_stop") is True,
        "run_unknown_resolution": flags.get("run_unknown_resolution") is True,
        "idempotency_supported": idem.get("supported") is True,
        "idempotency_durable": idem.get("durable") is True,
    }
    # Verification is endpoint+feature, never flag alone.
    route_ok = {
        name: (isinstance(endpoints.get(name), dict)
               and endpoints[name].get("method") == method
               and endpoints[name].get("path") == path)
        for name, (method, path) in ROUTES.items()
    }
    missing = sorted({
        name for name, good in advertised.items() if not good
    } | {
        "route:" + name for name, good in route_ok.items() if not good
    } | ({
        "auth_required"
    } if not auth["required"] else set()))
    try:
        retention = int(idem.get("retention_seconds", 0))
    except (ValueError, TypeError, OverflowError):
        retention = 0
    if type(idem.get("retention_seconds")) is not int:
        missing.append("idempotency_retention")
    elif retention < MIN_CONTROL_RETENTION_SECONDS:
        missing.append("idempotency_retention_below_24h")
    missing = sorted(set(missing))
    # Monitoring existing runs needs fewer privileges than controlling/retrying them.
    monitor_missing = sorted({
        name for name in ("run_status", "run_events_sse") if not advertised[name]
    } | {
        "route:" + name for name in ("run_status", "run_events") if not route_ok[name]
    } | ({"auth_required"} if not auth["required"] else set()))
    monitor_ok = not monitor_missing
    control_ok = not missing
    return {
        "schema_version": 1,
        "status": "CAPABILITIES_PRESENT" if control_ok else
                  "MONITOR_ONLY" if monitor_ok else "MIGRATION_OR_AUTH_GAP",
        "target_is_loopback": True,
        "auth_required": auth["required"],
        "advertised": advertised,
        "route_matches": route_ok,
        "idempotency_retention_seconds": retention if retention > 0 else None,
        "missing": missing,
        "monitor_missing": monitor_missing,
        "eligible_for_readonly_monitoring": monitor_ok,
        "eligible_for_isolated_integration_test": control_ok,
        "production_ready": False,
        "next_action": ("VERIFY_ACTUAL_AUTH_AND_E2E_BEFORE_ANY_WRITE" if control_ok
                        else "READONLY_OBSERVATION_ONLY" if monitor_ok
                        else "UPGRADE_OR_AUTHORIZE_BEFORE_OBSERVATION"),
    }

def read_capabilities(base_url, token="", timeout=5):
    """GET metadata only. Proxy and redirects disabled to protect bearer credentials."""
    url = normalize_base_url(base_url) + "/v1/capabilities"
    headers = {"Accept": "application/json", "User-Agent": "hermes-gpt-readonly-probe/1"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(url, headers=headers, method="GET")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:
            body = response.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise ProbeError("AUTH_REQUIRED_OR_DENIED") from None
        if 300 <= e.code <= 399:
            raise ProbeError("REDIRECT_FORBIDDEN") from None
        raise ProbeError("HTTP_ERROR_" + str(e.code)) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ProbeError("LOCAL_TRANSPORT_UNAVAILABLE") from None
    if len(body) > MAX_BYTES:
        raise ProbeError("CAPABILITIES_TOO_LARGE")
    try:
        return json.loads(body)
    except (ValueError, UnicodeError):
        raise ProbeError("INVALID_CAPABILITIES_JSON") from None

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--base-url", help="Local loopback listener, e.g. http://127.0.0.1:8642")
    group.add_argument("--snapshot", type=Path, help="Offline capabilities JSON; no network")
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--timeout", type=int, default=5)
    args = parser.parse_args(argv)
    try:
        if not 1 <= args.timeout <= 20:
            raise ProbeError("INVALID_TIMEOUT")
        if args.snapshot is not None:
            # Untrusted fixture data is bounded like the network response.
            raw = args.snapshot.read_bytes()
            if len(raw) > MAX_BYTES:
                raise ProbeError("SNAPSHOT_TOO_LARGE")
            data = json.loads(raw)
        else:
            data = read_capabilities(
                args.base_url, os.getenv("API_SERVER_KEY") or os.getenv("HERMES_API_KEY") or "",
                timeout=args.timeout,
            )
        report = evaluate_capabilities(data)
        code = 0 if report["eligible_for_isolated_integration_test"] else 2
    except ProbeError as exc:
        report, code = {
            "schema_version": 1, "status": "EVIDENCE_UNAVAILABLE",
            "reason_code": exc.code, "target_is_loopback": True,
            "eligible_for_isolated_integration_test": False,
            "production_ready": False,
        }, 3
    except (OSError, ValueError, TypeError, KeyError):
        report, code = {
            "schema_version": 1, "status": "EVIDENCE_UNAVAILABLE",
            "reason_code": "INPUT_OR_SCHEMA_ERROR",
            "eligible_for_isolated_integration_test": False,
            "production_ready": False,
        }, 3
    report["observed_at"] = datetime.now(timezone.utc).isoformat()
    payload = json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False)
    if args.output_json:
        try:
            args.output_json.parent.mkdir(parents=True, exist_ok=True)
            args.output_json.write_text(payload + "\n", encoding="utf-8")
        except OSError:
            print("EVIDENCE_OUTPUT_FAILED", file=sys.stderr)
            return 3
    else:
        print(payload)
    return code

if __name__ == "__main__":
    raise SystemExit(main())

"""Strict, *untrusted* response envelope for a consented Hermes/CDP bridge.

This pure parser has no CDP connection, ChatGPT session, tool execution or
authorization authority. The transport must enforce target ownership and fence.
Tool calls remain PROPOSALS to be processed by an independent Hermes policy
gateway; a syntactically valid response is never evidence of a completed task.

Proposed v1 wire envelope:
  {"request_id":"...","content":"...","tool_calls":[...]}
Supported call encodings are canonical {id,name,arguments} and OpenAI-compatible
{id,type:"function",function:{name,arguments}}. Do not assume a remote extension
supports both until version negotiation and a real interoperability canary.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Iterable

_REQUEST = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_TOOL_NAME = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_.:-]{0,127}$")
MAX_ENVELOPE_BYTES = 262_144
MAX_CONTENT_BYTES = 65_536
MAX_ARGUMENT_BYTES = 16_384
MAX_CALLS = 16
MAX_ARGUMENT_DEPTH = 16


class CDPProtocolError(ValueError):
    """Safe, enumerated error code; never includes a raw model/browser payload."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ToolProposal:
    call_id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class CDPReply:
    request_id: str
    content: str
    tool_calls: tuple[ToolProposal, ...]


def _byte_length(value: str, code: str) -> int:
    try:
        return len(value.encode("utf-8"))
    except UnicodeError:
        raise CDPProtocolError(code) from None


def _json_pairs(pairs):
    output = {}
    for k, v in pairs:
        if k in output:
            raise CDPProtocolError("DUPLICATE_JSON_KEY")
        output[k] = v
    return output


def _parse_json(data: str) -> Any:
    try:
        return json.loads(
            data, object_pairs_hook=_json_pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(
                CDPProtocolError("NONFINITE_JSON_NUMBER")
            ),
        )
    except CDPProtocolError:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise CDPProtocolError("JSON_SCHEMA_INVALID") from None


def _canonical_size(value: Any, *, code: str) -> int:
    try:
        data = json.dumps(value, sort_keys=True, separators=(",", ":"),
                          allow_nan=False, ensure_ascii=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise CDPProtocolError(code) from None
    return len(data)


def _check_argument_depth(value: Any, max_depth: int = MAX_ARGUMENT_DEPTH) -> None:
    """Enforce bounded nested JSON without allowing Python object extensions."""
    stack = [(value, 0)]
    visits = 0
    while stack:
        item, depth = stack.pop()
        visits += 1
        if visits > 10_000 or depth > max_depth:
            raise CDPProtocolError("TOOL_ARGUMENT_LIMIT")
        if isinstance(item, dict):
            if any(not isinstance(k, str) for k in item):
                raise CDPProtocolError("TOOL_ARGUMENT_SCHEMA_INVALID")
            stack.extend((v, depth + 1) for v in item.values())
        elif isinstance(item, list):
            stack.extend((v, depth + 1) for v in item)
        elif item is None or type(item) in (bool, int, float, str):
            if type(item) is float and not (-float("inf") < item < float("inf")):
                raise CDPProtocolError("NONFINITE_JSON_NUMBER")
        else:
            raise CDPProtocolError("TOOL_ARGUMENT_SCHEMA_INVALID")


def _tool_proposal(raw: Any, allowed: frozenset[str]) -> ToolProposal:
    if not isinstance(raw, dict):
        raise CDPProtocolError("TOOL_SCHEMA_INVALID")
    if set(raw) == {"id", "name", "arguments"}:
        call_id, name, args = raw["id"], raw["name"], raw["arguments"]
    elif set(raw) == {"id", "type", "function"} and raw["type"] == "function":
        fn = raw["function"]
        if not isinstance(fn, dict) or set(fn) != {"name", "arguments"}:
            raise CDPProtocolError("TOOL_SCHEMA_INVALID")
        call_id, name, args = raw["id"], fn["name"], fn["arguments"]
    else:
        raise CDPProtocolError("TOOL_SCHEMA_INVALID")
    if not isinstance(call_id, str) or not _REQUEST.fullmatch(call_id):
        raise CDPProtocolError("TOOL_CALL_ID_INVALID")
    if not isinstance(name, str) or not _TOOL_NAME.fullmatch(name):
        raise CDPProtocolError("TOOL_NAME_INVALID")
    if name not in allowed:
        raise CDPProtocolError("TOOL_NOT_DECLARED")
    if isinstance(args, str):
        if _byte_length(args, "TOOL_ARGUMENT_SCHEMA_INVALID") > MAX_ARGUMENT_BYTES:
            raise CDPProtocolError("TOOL_ARGUMENT_LIMIT")
        args = _parse_json(args)
    if not isinstance(args, dict):
        raise CDPProtocolError("TOOL_ARGUMENT_SCHEMA_INVALID")
    _check_argument_depth(args)
    if _canonical_size(args, code="TOOL_ARGUMENT_SCHEMA_INVALID") > MAX_ARGUMENT_BYTES:
        raise CDPProtocolError("TOOL_ARGUMENT_LIMIT")
    # Parse/copy source data; never expose the transport's mutable dictionary.
    args = _parse_json(json.dumps(args, sort_keys=True, ensure_ascii=False))
    return ToolProposal(call_id=call_id, name=name, arguments=args)


def parse_cdp_reply(
    raw: str | bytes | dict[str, Any],
    *,
    expected_request_id: str,
    declared_tools: Iterable[str] = (),
) -> CDPReply:
    """Fail-closed validation only. Does NOT accept/replay a browser action.

    A new request_id is mandatory for each new attempt; stale responses are
    rejected. The caller must separately compare session/target/fence and
    evidence before attributing task completion.
    """
    if not isinstance(expected_request_id, str) or not _REQUEST.fullmatch(expected_request_id):
        raise CDPProtocolError("EXPECTED_REQUEST_ID_INVALID")
    if isinstance(raw, bytes):
        if len(raw) > MAX_ENVELOPE_BYTES:
            raise CDPProtocolError("ENVELOPE_LIMIT")
        try:
            raw = raw.decode("utf-8", errors="strict")
        except UnicodeError:
            raise CDPProtocolError("JSON_SCHEMA_INVALID") from None
    if isinstance(raw, str):
        if _byte_length(raw, "JSON_SCHEMA_INVALID") > MAX_ENVELOPE_BYTES:
            raise CDPProtocolError("ENVELOPE_LIMIT")
        parsed = _parse_json(raw)
    elif isinstance(raw, dict):
        if _canonical_size(raw, code="JSON_SCHEMA_INVALID") > MAX_ENVELOPE_BYTES:
            raise CDPProtocolError("ENVELOPE_LIMIT")
        # Copy through strict JSON to avoid accepting custom Python objects.
        parsed = _parse_json(json.dumps(raw, allow_nan=False, ensure_ascii=False))
    else:
        raise CDPProtocolError("JSON_SCHEMA_INVALID")
    if not isinstance(parsed, dict) or set(parsed) != {"request_id", "content", "tool_calls"}:
        raise CDPProtocolError("ENVELOPE_KEYS_INVALID")
    actual = parsed["request_id"]
    if not isinstance(actual, str) or not _REQUEST.fullmatch(actual) or actual != expected_request_id:
        raise CDPProtocolError("REQUEST_ID_MISMATCH")
    content = parsed["content"]
    if not isinstance(content, str):
        raise CDPProtocolError("CONTENT_TYPE_INVALID")
    if _byte_length(content, "CONTENT_TYPE_INVALID") > MAX_CONTENT_BYTES:
        raise CDPProtocolError("CONTENT_LIMIT")
    calls = parsed["tool_calls"]
    if not isinstance(calls, list) or len(calls) > MAX_CALLS:
        raise CDPProtocolError("TOOL_CALLS_INVALID")
    try:
        declared = tuple(declared_tools)
    except TypeError:
        raise CDPProtocolError("TOOL_DECLARATION_INVALID") from None
    if any(not isinstance(x, str) or not _TOOL_NAME.fullmatch(x) for x in declared):
        raise CDPProtocolError("TOOL_DECLARATION_INVALID")
    allowed = frozenset(declared)
    normalized = tuple(_tool_proposal(call, allowed) for call in calls)
    ids = [call.call_id for call in normalized]
    if len(ids) != len(set(ids)):
        raise CDPProtocolError("DUPLICATE_TOOL_CALL_ID")
    if not content.strip() and not normalized:
        raise CDPProtocolError("EMPTY_REPLY")
    return CDPReply(request_id=actual, content=content, tool_calls=normalized)

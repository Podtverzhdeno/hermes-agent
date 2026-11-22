"""Offline, side-effect-free tests of the Hermes/CDP JSON response contract."""
import json

import pytest

from autopilot.cdp_contract import CDPProtocolError, parse_cdp_reply


def valid(content="hello", calls=None):
    return {"request_id": "r_001", "content": content, "tool_calls": calls or []}


def reject(data, reason, **kwargs):
    expected = kwargs.pop("expected_request_id", "r_001")
    with pytest.raises(CDPProtocolError) as err:
        parse_cdp_reply(data, expected_request_id=expected, **kwargs)
    assert err.value.code == reason
    # Failures are safe codes, never raw input that may include user secrets.
    assert "SENSITIVE_SECRET" not in str(err.value)


def test_accept_valid_json_string_bytes_and_dict():
    sample = valid("привет")
    for raw in (sample, json.dumps(sample), json.dumps(sample).encode("utf-8")):
        result = parse_cdp_reply(raw, expected_request_id="r_001")
        assert result.content == "привет"
        assert result.request_id == "r_001"
        assert not result.tool_calls


def test_accept_normalized_and_openai_tool_proposals_but_never_execute():
    calls = [
        {"id": "c1", "name": "search", "arguments": {"q": "hello"}},
        {"id": "c2", "type": "function",
         "function": {"name": "search", "arguments": '{"q":"bye"}'}},
    ]
    x = parse_cdp_reply(valid("", calls), expected_request_id="r_001",
                        declared_tools={"search"})
    assert [tool.call_id for tool in x.tool_calls] == ["c1", "c2"]
    assert [tool.arguments for tool in x.tool_calls] == [{"q": "hello"}, {"q": "bye"}]
    assert x.content == ""


def test_wrong_or_old_request_is_rejected_not_matched_by_content():
    reject({**valid(), "request_id": "old_request"}, "REQUEST_ID_MISMATCH")
    reject({**valid(), "request_id": "r_001 "}, "REQUEST_ID_MISMATCH")


def test_exact_top_level_keys_required():
    reject({"request_id": "r_001", "content": "hi"}, "ENVELOPE_KEYS_INVALID")
    reject({**valid(), "secret_extra": "SENSITIVE_SECRET"}, "ENVELOPE_KEYS_INVALID")
    reject([], "JSON_SCHEMA_INVALID")


def test_duplicate_json_keys_are_rejected():
    raw = '{"request_id":"r_001","request_id":"r_001","content":"ok","tool_calls":[]}'
    reject(raw, "DUPLICATE_JSON_KEY")
    nested = '{"request_id":"r_001","content":"","tool_calls":[{"id":"c1","name":"f","arguments":"{\\"x\\":1,\\"x\\":2}"}]}'
    reject(nested, "DUPLICATE_JSON_KEY", declared_tools={"f"})


def test_invalid_json_and_nonfinite_numbers_fail_closed():
    reject("{this is invalid JSON}", "JSON_SCHEMA_INVALID")
    reject('{"request_id":"r_001","content":"a","tool_calls":[], "x": NaN}',
           "NONFINITE_JSON_NUMBER")
    reject(b"\xff", "JSON_SCHEMA_INVALID")


def test_content_size_empty_and_unicode_boundary():
    reject(valid(""), "EMPTY_REPLY")
    reject(valid("x" * 65537), "CONTENT_LIMIT")
    reject({"request_id": "r_001", "content": 9, "tool_calls": []},
           "CONTENT_TYPE_INVALID")
    reject(valid("\ud800"), "JSON_SCHEMA_INVALID")


def test_unknown_tools_and_bad_call_schema_do_not_gain_permissions():
    reject(valid("", [{"id": "c1", "name": "shell", "arguments": {}}]),
           "TOOL_NOT_DECLARED", declared_tools={"search"})
    reject(valid("", [{"id": "c1", "name": "shell", "arguments": {}}]),
           "TOOL_NOT_DECLARED")
    reject(valid("", [{"name": "search", "arguments": {}}]),
           "TOOL_SCHEMA_INVALID", declared_tools={"search"})
    reject(valid("", [{"id": "c1", "name": "search", "arguments": {}, "admin": True}]),
           "TOOL_SCHEMA_INVALID", declared_tools={"search"})


def test_duplicate_tool_call_id_rejected_even_across_encodings():
    calls = [
        {"id": "dup", "name": "search", "arguments": {}},
        {"id": "dup", "type": "function",
         "function": {"name": "search", "arguments": "{}"}},
    ]
    reject(valid("", calls), "DUPLICATE_TOOL_CALL_ID", declared_tools={"search"})


def test_nested_argument_depth_and_non_object_rejected():
    nested = {}
    for _ in range(18):
        nested = {"nested": nested}
    reject(valid("", [{"id": "c1", "name": "search", "arguments": nested}]),
           "TOOL_ARGUMENT_LIMIT", declared_tools={"search"})
    reject(valid("", [{"id": "c1", "name": "search", "arguments": ["list"]}]),
           "TOOL_ARGUMENT_SCHEMA_INVALID", declared_tools={"search"})


def test_limits_reject_unbounded_calls_and_oversized_data():
    calls = [{"id": "call" + str(i), "name": "f", "arguments": {}} for i in range(17)]
    reject(valid("", calls), "TOOL_CALLS_INVALID", declared_tools={"f"})
    reject(valid("", [{"id": "c1", "name": "f",
                       "arguments": {"x": "a" * 20000}}]),
           "TOOL_ARGUMENT_LIMIT", declared_tools={"f"})
    reject("x" * 270000, "ENVELOPE_LIMIT")


def test_invalid_declarations_and_request_ids():
    reject(valid(), "EXPECTED_REQUEST_ID_INVALID", expected_request_id="BAD SPACE")
    reject(valid("", [{"id": "c1", "name": "f", "arguments": {}}]),
           "TOOL_DECLARATION_INVALID", declared_tools=[9])


def test_declarations_must_be_iterable_of_names_not_string_or_mapping():
    reject(valid(), "TOOL_DECLARATION_INVALID", declared_tools="search")
    reject(valid(), "TOOL_DECLARATION_INVALID", declared_tools={"search": True})


def test_utf8_surrogates_in_nested_tool_args_never_escape_as_raw_exception():
    # A genuine unpaired surrogate is legal to represent as an ASCII escape
    # in JSON text but must be rejected during argument UTF-8 validation.
    malformed = json.dumps(valid("", [
        {"id": "c1", "name": "search",
         "arguments": {"text": chr(0xD800)}},
    ]))
    reject(malformed, "TOOL_ARGUMENT_SCHEMA_INVALID", declared_tools={"search"})


def test_nonfinite_tool_argument_is_rejected_not_authorized():
    reject(valid("", [{"id": "c1", "name": "search",
                       "arguments": '{"value": NaN}'}]),
           "NONFINITE_JSON_NUMBER", declared_tools={"search"})

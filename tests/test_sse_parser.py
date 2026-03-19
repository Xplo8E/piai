"""
Tests for _parse_sse — the SSE event parser.

Tests the SSE parsing logic with various event formats, edge cases,
and line ending variations without any HTTP I/O.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from piai.providers.openai_codex import _parse_sse


# ------------------------------------------------------------------ #
# Helpers                                                             #
# ------------------------------------------------------------------ #


def _make_mock_response(chunks: list[str]):
    """Build a mock httpx.Response that streams the given text chunks."""
    response = MagicMock()

    async def _aiter():
        for chunk in chunks:
            yield chunk

    response.aiter_text = _aiter
    return response


async def _collect_events(chunks: list[str]) -> list[dict]:
    response = _make_mock_response(chunks)
    events = []
    async for event in _parse_sse(response):
        events.append(event)
    return events


def _sse_event(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


# ------------------------------------------------------------------ #
# Basic parsing                                                       #
# ------------------------------------------------------------------ #


async def test_single_event():
    payload = {"type": "response.completed", "x": 1}
    events = await _collect_events([_sse_event(payload)])
    assert len(events) == 1
    assert events[0]["type"] == "response.completed"


async def test_multiple_events_in_one_chunk():
    chunk = _sse_event({"id": 1}) + _sse_event({"id": 2}) + _sse_event({"id": 3})
    events = await _collect_events([chunk])
    assert len(events) == 3
    assert [e["id"] for e in events] == [1, 2, 3]


async def test_events_split_across_chunks():
    """Event boundary split across two network chunks."""
    full = _sse_event({"id": 1})
    mid = len(full) // 2
    events = await _collect_events([full[:mid], full[mid:]])
    assert len(events) == 1
    assert events[0]["id"] == 1


async def test_done_sentinel_skipped():
    """[DONE] terminator should be silently dropped."""
    events = await _collect_events(["data: [DONE]\n\n"])
    assert events == []


async def test_empty_data_lines_skipped():
    events = await _collect_events(["event: ping\n\n"])
    assert events == []


async def test_invalid_json_skipped():
    events = await _collect_events(["data: not-json-at-all\n\n"])
    assert events == []


async def test_valid_followed_by_invalid():
    chunk = _sse_event({"ok": True}) + "data: BAD\n\n"
    events = await _collect_events([chunk])
    assert len(events) == 1
    assert events[0]["ok"] is True


# ------------------------------------------------------------------ #
# Line ending normalization                                           #
# ------------------------------------------------------------------ #


async def test_crlf_line_endings():
    """CRLF (\\r\\n) line endings should be normalized."""
    payload = {"type": "test"}
    sse = f"data: {json.dumps(payload)}\r\n\r\n"
    events = await _collect_events([sse])
    assert len(events) == 1
    assert events[0]["type"] == "test"


async def test_cr_only_line_endings():
    """CR-only (\\r) line endings should be normalized."""
    payload = {"type": "cr_test"}
    sse = f"data: {json.dumps(payload)}\r\r"
    events = await _collect_events([sse])
    assert len(events) == 1
    assert events[0]["type"] == "cr_test"


async def test_mixed_line_endings():
    """Mix of CRLF and LF in same stream."""
    e1 = f"data: {json.dumps({'n': 1})}\r\n\r\n"
    e2 = f"data: {json.dumps({'n': 2})}\n\n"
    events = await _collect_events([e1 + e2])
    assert len(events) == 2
    assert events[0]["n"] == 1
    assert events[1]["n"] == 2


# ------------------------------------------------------------------ #
# Data format variants                                                #
# ------------------------------------------------------------------ #


async def test_data_with_space_after_colon():
    """Both 'data:foo' and 'data: foo' should be parsed."""
    e1 = f"data: {json.dumps({'spaced': True})}\n\n"
    e2 = f"data:{json.dumps({'nospace': True})}\n\n"
    events = await _collect_events([e1, e2])
    assert len(events) == 2
    assert events[0]["spaced"] is True
    assert events[1]["nospace"] is True


async def test_event_with_comment_lines_ignored():
    """Lines starting with ':' are SSE comments — no data, event skipped."""
    chunk = ": keep-alive\n\n" + _sse_event({"real": True})
    events = await _collect_events([chunk])
    assert len(events) == 1
    assert events[0]["real"] is True


async def test_event_type_field_ignored():
    """'event: ...' fields don't affect data parsing."""
    chunk = f"event: message\ndata: {json.dumps({'x': 42})}\n\n"
    events = await _collect_events([chunk])
    assert len(events) == 1
    assert events[0]["x"] == 42


async def test_empty_stream():
    events = await _collect_events([])
    assert events == []


async def test_only_whitespace_chunks():
    events = await _collect_events(["   ", "\n", "  \n  "])
    assert events == []


async def test_many_small_chunks():
    """Event data arriving one character at a time."""
    payload = {"type": "tiny"}
    full = _sse_event(payload)
    chunks = list(full)  # one char per chunk
    events = await _collect_events(chunks)
    assert len(events) == 1
    assert events[0]["type"] == "tiny"


async def test_large_event():
    """Large JSON payload doesn't get truncated."""
    payload = {"data": "x" * 10_000}
    events = await _collect_events([_sse_event(payload)])
    assert len(events) == 1
    assert len(events[0]["data"]) == 10_000

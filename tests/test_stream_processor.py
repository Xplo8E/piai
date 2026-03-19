"""
Tests for _StreamProcessor — the core SSE event state machine.

Tests the processing of raw Codex SSE events into typed StreamEvents
without any network I/O. Feeds synthetic event dicts to verify correct
state transitions and output.
"""

from __future__ import annotations

import json

import pytest

from piai.providers.openai_codex import _StreamProcessor
from piai.types import (
    AssistantMessage,
    TextContent,
    TextDeltaEvent,
    TextEndEvent,
    TextStartEvent,
    ThinkingContent,
    ThinkingDeltaEvent,
    ToolCall,
    ToolCallContent,
    ToolCallDeltaEvent,
    ToolCallEndEvent,
    ToolCallStartEvent,
    DoneEvent,
)


# ------------------------------------------------------------------ #
# Helpers                                                             #
# ------------------------------------------------------------------ #


async def _process(events: list[dict]) -> tuple[list, AssistantMessage]:
    """Run _StreamProcessor on a list of event dicts. Returns (stream_events, output)."""

    async def _gen():
        for e in events:
            yield e

    output = AssistantMessage()
    processor = _StreamProcessor(output)
    stream_events = []
    async for event in processor.process(_gen()):
        stream_events.append(event)
    return stream_events, output


def _text_stream(text: str, item_id: str = "item_001") -> list[dict]:
    """Build minimal SSE events for a text response."""
    return [
        {"type": "response.output_item.added", "item": {"type": "message", "id": item_id}},
        {"type": "response.content_part.added", "part": {"type": "output_text"}},
        {"type": "response.output_text.delta", "delta": text},
        {
            "type": "response.output_item.done",
            "item": {"type": "message", "id": item_id, "content": [{"type": "output_text", "text": text}]},
        },
        {
            "type": "response.completed",
            "response": {
                "status": "completed",
                "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15,
                          "input_tokens_details": {"cached_tokens": 0}},
            },
        },
    ]


# ------------------------------------------------------------------ #
# Text streaming                                                      #
# ------------------------------------------------------------------ #


async def test_text_stream_emits_start_delta_end():
    events, output = await _process(_text_stream("Hello world"))
    types = [type(e).__name__ for e in events]
    assert "TextStartEvent" in types
    assert "TextDeltaEvent" in types
    assert "TextEndEvent" in types


async def test_text_delta_content():
    events, output = await _process(_text_stream("Hello"))
    deltas = [e.text for e in events if isinstance(e, TextDeltaEvent)]
    assert deltas == ["Hello"]


async def test_text_end_contains_full_text():
    events, output = await _process(_text_stream("Hello"))
    end_events = [e for e in events if isinstance(e, TextEndEvent)]
    assert len(end_events) == 1
    assert end_events[0].text == "Hello"


async def test_output_content_contains_text_block():
    _, output = await _process(_text_stream("Hi there"))
    assert len(output.content) == 1
    assert isinstance(output.content[0], TextContent)
    assert output.content[0].text == "Hi there"


async def test_usage_extracted():
    events, output = await _process(_text_stream("Hi"))
    assert output.usage["output"] == 5
    assert output.usage["input"] == 10  # no cached


async def test_cached_tokens_subtracted_from_input():
    raw_events = _text_stream("Hi")
    # Override usage with cached tokens
    raw_events[-1]["response"]["usage"] = {
        "input_tokens": 20,
        "output_tokens": 5,
        "total_tokens": 25,
        "input_tokens_details": {"cached_tokens": 8},
    }
    _, output = await _process(raw_events)
    assert output.usage["input"] == 12  # 20 - 8
    assert output.usage["cache_read"] == 8


async def test_stop_reason_stop_on_complete():
    _, output = await _process(_text_stream("Hi"))
    assert output.stop_reason == "stop"


async def test_stop_reason_length_on_incomplete():
    raw_events = _text_stream("Hi")
    raw_events[-1]["response"]["status"] = "incomplete"
    _, output = await _process(raw_events)
    assert output.stop_reason == "length"


async def test_stop_reason_error_on_failed_status():
    raw_events = _text_stream("Hi")
    raw_events[-1]["response"]["status"] = "failed"
    _, output = await _process(raw_events)
    assert output.stop_reason == "error"


# ------------------------------------------------------------------ #
# Tool call streaming                                                 #
# ------------------------------------------------------------------ #


def _tool_call_stream(name: str, args: dict, call_id: str = "call_001", item_id: str = "fc_001") -> list[dict]:
    args_str = json.dumps(args)
    return [
        {
            "type": "response.output_item.added",
            "item": {"type": "function_call", "id": item_id, "call_id": call_id, "name": name, "arguments": ""},
        },
        {"type": "response.function_call_arguments.delta", "delta": args_str},
        {"type": "response.function_call_arguments.done", "arguments": args_str},
        {
            "type": "response.output_item.done",
            "item": {"type": "function_call", "id": item_id, "call_id": call_id, "name": name, "arguments": args_str},
        },
        {
            "type": "response.completed",
            "response": {
                "status": "completed",
                "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15,
                          "input_tokens_details": {"cached_tokens": 0}},
            },
        },
    ]


async def test_tool_call_emits_start_delta_end():
    events, _ = await _process(_tool_call_stream("search", {"q": "python"}))
    types = [type(e).__name__ for e in events]
    assert "ToolCallStartEvent" in types
    assert "ToolCallDeltaEvent" in types
    assert "ToolCallEndEvent" in types


async def test_tool_call_start_has_name():
    events, _ = await _process(_tool_call_stream("get_weather", {"city": "London"}))
    start = next(e for e in events if isinstance(e, ToolCallStartEvent))
    assert start.tool_call.name == "get_weather"


async def test_tool_call_end_has_parsed_input():
    events, _ = await _process(_tool_call_stream("search", {"q": "python"}))
    end = next(e for e in events if isinstance(e, ToolCallEndEvent))
    assert end.tool_call.name == "search"
    assert end.tool_call.input == {"q": "python"}


async def test_tool_call_id_in_events():
    events, _ = await _process(_tool_call_stream("search", {}, call_id="call_xyz", item_id="fc_abc"))
    start = next(e for e in events if isinstance(e, ToolCallStartEvent))
    end = next(e for e in events if isinstance(e, ToolCallEndEvent))
    # IDs should match and be truncated to 64 chars
    assert start.tool_call.id == end.tool_call.id
    assert len(start.tool_call.id) <= 64


async def test_tool_call_in_output_content():
    _, output = await _process(_tool_call_stream("search", {"q": "py"}))
    assert any(isinstance(b, ToolCallContent) for b in output.content)
    tc_block = next(b for b in output.content if isinstance(b, ToolCallContent))
    assert tc_block.tool_calls[0].name == "search"


async def test_stop_reason_tool_use_when_tool_called():
    _, output = await _process(_tool_call_stream("search", {}))
    assert output.stop_reason == "tool_use"


async def test_tool_call_invalid_json_args_becomes_empty_dict():
    """If final args can't be parsed, input should be empty dict (not raise)."""
    raw_events = [
        {
            "type": "response.output_item.added",
            "item": {"type": "function_call", "id": "fc_1", "call_id": "c_1", "name": "tool", "arguments": ""},
        },
        {
            "type": "response.output_item.done",
            "item": {"type": "function_call", "id": "fc_1", "call_id": "c_1", "name": "tool", "arguments": "INVALID JSON"},
        },
        {
            "type": "response.completed",
            "response": {"status": "completed", "usage": {"input_tokens": 0, "output_tokens": 0,
                         "total_tokens": 0, "input_tokens_details": {"cached_tokens": 0}}},
        },
    ]
    events, output = await _process(raw_events)
    end = next((e for e in events if isinstance(e, ToolCallEndEvent)), None)
    assert end is not None
    assert end.tool_call.input == {}


# ------------------------------------------------------------------ #
# Reasoning/thinking streaming                                        #
# ------------------------------------------------------------------ #


def _thinking_stream(thinking_text: str) -> list[dict]:
    return [
        {"type": "response.output_item.added", "item": {"type": "reasoning", "id": "rs_001"}},
        {"type": "response.reasoning_summary_part.added", "part": {"type": "summary_text"}},
        {"type": "response.reasoning_summary_text.delta", "delta": thinking_text},
        {"type": "response.reasoning_summary_part.done"},
        {"type": "response.output_item.done", "item": {"type": "reasoning"}},
        {
            "type": "response.completed",
            "response": {"status": "completed", "usage": {"input_tokens": 5, "output_tokens": 3,
                         "total_tokens": 8, "input_tokens_details": {"cached_tokens": 0}}},
        },
    ]


async def test_thinking_emits_delta():
    events, _ = await _process(_thinking_stream("I need to reason..."))
    deltas = [e for e in events if isinstance(e, ThinkingDeltaEvent)]
    assert len(deltas) >= 1
    all_thinking = "".join(e.thinking for e in deltas if e.thinking)
    assert "I need to reason" in all_thinking


async def test_thinking_in_output_content():
    _, output = await _process(_thinking_stream("Hmm let me think"))
    thinking_blocks = [b for b in output.content if isinstance(b, ThinkingContent)]
    assert len(thinking_blocks) == 1
    assert "Hmm let me think" in thinking_blocks[0].thinking


async def test_reasoning_plus_text_response():
    """Thinking followed by text produces both blocks."""
    events_seq = _thinking_stream("Let me think") + _text_stream("The answer is 42", item_id="item_002")
    # Remove the first response.completed (keep only last)
    events_seq = [e for e in events_seq if not (e["type"] == "response.completed")]
    events_seq.append({
        "type": "response.completed",
        "response": {"status": "completed", "usage": {"input_tokens": 15, "output_tokens": 10,
                     "total_tokens": 25, "input_tokens_details": {"cached_tokens": 0}}},
    })

    _, output = await _process(events_seq)
    types = [type(b).__name__ for b in output.content]
    assert "ThinkingContent" in types
    assert "TextContent" in types


# ------------------------------------------------------------------ #
# Error handling                                                      #
# ------------------------------------------------------------------ #


async def test_error_event_raises():
    raw_events = [{"type": "error", "code": "auth_error", "message": "Unauthorized"}]
    with pytest.raises(RuntimeError, match="Codex error: Unauthorized"):
        await _process(raw_events)


async def test_response_failed_raises():
    raw_events = [{
        "type": "response.failed",
        "response": {
            "error": {"code": "rate_limited", "message": "Too many requests"}
        },
    }]
    with pytest.raises(RuntimeError, match="rate_limited"):
        await _process(raw_events)


async def test_response_failed_incomplete_details_fallback():
    raw_events = [{
        "type": "response.failed",
        "response": {
            "incomplete_details": {"reason": "max_tokens"}
        },
    }]
    with pytest.raises(RuntimeError, match="incomplete: max_tokens"):
        await _process(raw_events)


async def test_response_failed_no_details():
    raw_events = [{"type": "response.failed", "response": {}}]
    with pytest.raises(RuntimeError, match="Unknown error"):
        await _process(raw_events)


# ------------------------------------------------------------------ #
# Edge cases                                                          #
# ------------------------------------------------------------------ #


async def test_unknown_event_types_ignored():
    """Unknown SSE event types should be silently skipped."""
    raw_events = [
        {"type": "some.unknown.event", "data": "foo"},
        {"type": "response.rate_limits.updated", "rate_limits": []},
    ] + _text_stream("Hi")
    events, output = await _process(raw_events)
    assert any(isinstance(e, TextDeltaEvent) for e in events)


async def test_delta_without_item_is_ignored():
    """Deltas that arrive before output_item.added are silently ignored."""
    raw_events = [
        {"type": "response.output_text.delta", "delta": "orphaned"},
    ] + _text_stream("Normal")
    events, output = await _process(raw_events)
    deltas = [e.text for e in events if isinstance(e, TextDeltaEvent)]
    assert "orphaned" not in deltas
    assert "Normal" in deltas


async def test_refusal_delta_surfaces_as_text():
    """Refusal deltas should emit TextDeltaEvents (same as text)."""
    raw_events = [
        {"type": "response.output_item.added", "item": {"type": "message", "id": "item_r"}},
        {"type": "response.content_part.added", "part": {"type": "refusal"}},
        {"type": "response.refusal.delta", "delta": "I cannot help with that"},
        {
            "type": "response.output_item.done",
            "item": {"type": "message", "id": "item_r", "content": [{"type": "refusal", "text": "I cannot help with that"}]},
        },
        {
            "type": "response.completed",
            "response": {"status": "completed", "usage": {"input_tokens": 5, "output_tokens": 3,
                         "total_tokens": 8, "input_tokens_details": {"cached_tokens": 0}}},
        },
    ]
    events, _ = await _process(raw_events)
    deltas = [e for e in events if isinstance(e, TextDeltaEvent)]
    assert any("cannot help" in d.text for d in deltas)


async def test_empty_stream_no_events():
    events, output = await _process([])
    assert events == []

"""
Tests for Context → OpenAI Responses API message transformation.
"""

import json

from piai.providers.message_transform import (
    _clamp_reasoning_effort,
    build_request_body,
    convert_messages,
    convert_tools,
)
from piai.providers.openai_codex import _make_tc_id, MAX_TOOL_CALL_ID_LEN
from piai.types import (
    AssistantMessage,
    Context,
    TextContent,
    ThinkingContent,
    Tool,
    ToolCall,
    ToolCallContent,
    ToolResultMessage,
    UserMessage,
)


def test_simple_user_message():
    ctx = Context(messages=[UserMessage(content="Hello")])
    msgs = convert_messages(ctx)
    assert len(msgs) == 1
    assert msgs[0]["type"] == "message"
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"][0]["text"] == "Hello"
    assert msgs[0]["content"][0]["type"] == "input_text"


def test_assistant_text_message():
    msg = AssistantMessage(content=[TextContent(text="Hi there")])
    ctx = Context(messages=[msg])
    msgs = convert_messages(ctx)
    assert len(msgs) == 1
    assert msgs[0]["role"] == "assistant"
    assert msgs[0]["content"][0]["type"] == "output_text"
    assert msgs[0]["content"][0]["text"] == "Hi there"


def test_tool_call_becomes_function_call():
    tc = ToolCall(id="call_abc", name="get_weather", input={"city": "London"})
    msg = AssistantMessage(content=[ToolCallContent(tool_calls=[tc])])
    ctx = Context(messages=[msg])
    msgs = convert_messages(ctx)
    assert len(msgs) == 1
    assert msgs[0]["type"] == "function_call"
    assert msgs[0]["name"] == "get_weather"
    assert msgs[0]["call_id"] == "call_abc"
    args = json.loads(msgs[0]["arguments"])
    assert args["city"] == "London"


def test_tool_result_becomes_function_call_output():
    result = ToolResultMessage(tool_call_id="call_abc", content='{"temp": 20}')
    ctx = Context(messages=[result])
    msgs = convert_messages(ctx)
    assert len(msgs) == 1
    assert msgs[0]["type"] == "function_call_output"
    assert msgs[0]["call_id"] == "call_abc"
    assert msgs[0]["output"] == '{"temp": 20}'


def test_thinking_block_wrapped_in_tags():
    msg = AssistantMessage(content=[ThinkingContent(thinking="Let me think...")])
    ctx = Context(messages=[msg])
    msgs = convert_messages(ctx)
    assert "<thinking>Let me think...</thinking>" in msgs[0]["content"][0]["text"]


def test_system_prompt_in_request_body():
    ctx = Context(
        system_prompt="You are helpful.",
        messages=[UserMessage(content="Hi")],
    )
    body = build_request_body("gpt-5.1-codex-mini", ctx)
    assert body["instructions"] == "You are helpful."
    assert body["model"] == "gpt-5.1-codex-mini"
    assert body["stream"] is True
    assert body["store"] is False


def test_tools_converted():
    tool = Tool(
        name="search",
        description="Search the web",
        parameters={"type": "object", "properties": {"query": {"type": "string"}}},
    )
    ctx = Context(messages=[UserMessage(content="Search for X")], tools=[tool])
    body = build_request_body("gpt-5.1-codex-mini", ctx)
    assert "tools" in body
    assert body["tools"][0]["name"] == "search"
    assert body["tools"][0]["type"] == "function"


def test_session_id_becomes_prompt_cache_key():
    ctx = Context(messages=[UserMessage(content="Hi")])
    body = build_request_body("gpt-5.1-codex-mini", ctx, options={"session_id": "sess_abc"})
    assert body["prompt_cache_key"] == "sess_abc"


def test_reasoning_effort_in_body():
    ctx = Context(messages=[UserMessage(content="Hi")])
    body = build_request_body("gpt-5.1-codex-mini", ctx, options={"reasoning_effort": "high"})
    assert body["reasoning"]["effort"] == "high"
    assert body["reasoning"]["summary"] == "auto"


# ------------------------------------------------------------------ #
# _clamp_reasoning_effort                                             #
# ------------------------------------------------------------------ #

def test_clamp_mini_xhigh_becomes_high():
    assert _clamp_reasoning_effort("gpt-5.1-codex-mini", "xhigh") == "high"

def test_clamp_mini_high_stays_high():
    assert _clamp_reasoning_effort("gpt-5.1-codex-mini", "high") == "high"

def test_clamp_mini_low_becomes_medium():
    assert _clamp_reasoning_effort("gpt-5.1-codex-mini", "low") == "medium"

def test_clamp_mini_medium_stays_medium():
    assert _clamp_reasoning_effort("gpt-5.1-codex-mini", "medium") == "medium"

def test_clamp_gpt51_xhigh_becomes_high():
    assert _clamp_reasoning_effort("gpt-5.1", "xhigh") == "high"

def test_clamp_gpt51_high_unchanged():
    assert _clamp_reasoning_effort("gpt-5.1", "high") == "high"

def test_clamp_gpt52_minimal_becomes_low():
    assert _clamp_reasoning_effort("gpt-5.2", "minimal") == "low"

def test_clamp_gpt53_minimal_becomes_low():
    assert _clamp_reasoning_effort("gpt-5.3-codex", "minimal") == "low"

def test_clamp_gpt54_minimal_becomes_low():
    assert _clamp_reasoning_effort("gpt-5.4", "minimal") == "low"

def test_clamp_gpt52_high_unchanged():
    assert _clamp_reasoning_effort("gpt-5.2", "high") == "high"

def test_clamp_strips_provider_prefix():
    # "openai-codex/gpt-5.1-codex-mini" → strip prefix, apply mini clamping
    assert _clamp_reasoning_effort("openai-codex/gpt-5.1-codex-mini", "xhigh") == "high"

def test_clamp_unknown_model_passthrough():
    assert _clamp_reasoning_effort("gpt-6", "xhigh") == "xhigh"


# ------------------------------------------------------------------ #
# _make_tc_id                                                         #
# ------------------------------------------------------------------ #

def test_make_tc_id_short_ids():
    result = _make_tc_id("call_abc", "item_xyz")
    assert result == "call_abc|item_xyz"
    assert len(result) <= MAX_TOOL_CALL_ID_LEN

def test_make_tc_id_truncates_to_64():
    long_call = "c" * 50
    long_item = "i" * 50
    result = _make_tc_id(long_call, long_item)
    assert len(result) == MAX_TOOL_CALL_ID_LEN

def test_make_tc_id_exactly_64_chars():
    # Should not truncate if exactly 64
    call_id = "c" * 30
    item_id = "i" * 33  # 30 + 1 (pipe) + 33 = 64
    result = _make_tc_id(call_id, item_id)
    assert len(result) == MAX_TOOL_CALL_ID_LEN

def test_make_tc_id_empty_inputs():
    result = _make_tc_id("", "")
    assert result == "|"


# ------------------------------------------------------------------ #
# Multi-turn message round-trips                                      #
# ------------------------------------------------------------------ #

def test_multi_turn_conversation():
    """Full conversation with user → assistant → tool → user round-trip."""
    tc = ToolCall(id="call_1", name="search", input={"q": "python"})
    msgs = [
        UserMessage(content="Search for python"),
        AssistantMessage(content=[ToolCallContent(tool_calls=[tc])]),
        ToolResultMessage(tool_call_id="call_1", content="Python is a language"),
        UserMessage(content="Thanks"),
    ]
    ctx = Context(messages=msgs)
    result = convert_messages(ctx)
    assert len(result) == 4
    assert result[0]["role"] == "user"
    assert result[1]["type"] == "function_call"
    assert result[2]["type"] == "function_call_output"
    assert result[3]["role"] == "user"


def test_assistant_message_with_text_and_tool_call():
    """Assistant message with both text and tool call produces two items."""
    tc = ToolCall(id="call_1", name="search", input={})
    msg = AssistantMessage(content=[
        TextContent(text="Let me search"),
        ToolCallContent(tool_calls=[tc]),
    ])
    ctx = Context(messages=[msg])
    result = convert_messages(ctx)
    assert len(result) == 2
    assert result[0]["role"] == "assistant"
    assert result[1]["type"] == "function_call"


def test_user_message_with_list_content():
    """UserMessage with list content is converted block-by-block."""
    msg = UserMessage(content=["Hello", {"type": "input_image", "url": "http://x/img.png"}])
    ctx = Context(messages=[msg])
    result = convert_messages(ctx)
    assert result[0]["content"][0] == {"type": "input_text", "text": "Hello"}
    assert result[0]["content"][1] == {"type": "input_image", "url": "http://x/img.png"}


def test_empty_assistant_text_not_emitted():
    """Empty TextContent blocks are not emitted."""
    msg = AssistantMessage(content=[TextContent(text="")])
    ctx = Context(messages=[msg])
    result = convert_messages(ctx)
    assert result == []


def test_temperature_not_passed_to_backend():
    """temperature is unsupported by the ChatGPT backend — must never be sent."""
    ctx = Context(messages=[UserMessage(content="Hi")])
    body = build_request_body("gpt-5.1-codex-mini", ctx, options={"temperature": 0.7})
    assert "temperature" not in body


def test_default_instructions_when_no_system_prompt():
    ctx = Context(messages=[UserMessage(content="Hi")])
    body = build_request_body("gpt-5.1-codex-mini", ctx)
    assert body["instructions"] == "You are a helpful assistant."


def test_no_tools_key_when_no_tools():
    ctx = Context(messages=[UserMessage(content="Hi")])
    body = build_request_body("gpt-5.1-codex-mini", ctx)
    assert "tools" not in body


def test_multiple_tool_calls_in_assistant():
    """Multiple tool calls produce multiple function_call items."""
    tcs = [
        ToolCall(id="call_1", name="search", input={}),
        ToolCall(id="call_2", name="weather", input={"city": "NYC"}),
    ]
    msg = AssistantMessage(content=[ToolCallContent(tool_calls=tcs)])
    ctx = Context(messages=[msg])
    result = convert_messages(ctx)
    assert len(result) == 2
    assert result[0]["name"] == "search"
    assert result[1]["name"] == "weather"

"""Tests for AI provider style resolution and config persistence."""

from __future__ import annotations

from pathlib import Path

from ai import client as ai_client


def test_resolve_api_style_respects_explicit_style():
    """Explicit style should override URL inference."""

    assert (
        ai_client._resolve_api_style(
            base_url="https://api.openai.com/v1",
            api_style="anthropic",
        )
        == "anthropic"
    )


def test_resolve_api_style_infers_gemini_from_url():
    """Gemini hostnames should still auto-route for backward compatibility."""

    assert (
        ai_client._resolve_api_style(
            base_url="https://generativelanguage.googleapis.com/v1beta",
            api_style="",
        )
        == "gemini"
    )


def test_write_ai_config_persists_api_style(tmp_path, monkeypatch):
    """Custom config writes should persist the explicit API style."""

    config_path = tmp_path / "config.py"
    config_path.write_text(
        'AI_API_KEY = ""\nAI_BASE_URL = ""\nAI_MODEL = ""\nAI_API_STYLE = ""\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(ai_client, "_CONFIG_PATH", config_path)

    assert ai_client._write_ai_config(
        "sk-test",
        "https://api.anthropic.com/v1",
        "claude-3-7-sonnet-latest",
        "anthropic",
    )

    assert ai_client._read_ai_config() == (
        "sk-test",
        "https://api.anthropic.com/v1",
        "claude-3-7-sonnet-latest",
        "anthropic",
    )


def test_messages_to_anthropic_payload_groups_tool_results():
    """Consecutive tool replies should be merged into one Anthropic user message."""

    _, converted = ai_client._messages_to_anthropic_payload(
        [
            {"role": "system", "content": "sys"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "foo", "arguments": '{"x":1}'},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": '{"success": true, "x": 1}'},
            {"role": "tool", "tool_call_id": "call_2", "content": "plain text"},
        ]
    )

    assert len(converted) == 2
    assert converted[0]["role"] == "assistant"
    assert converted[1]["role"] == "user"
    assert len(converted[1]["content"]) == 2
    assert all(block["type"] == "tool_result" for block in converted[1]["content"])


def test_messages_to_anthropic_payload_preserves_thinking_blocks():
    """Anthropic thinking blocks should round-trip through history conversion."""

    _, converted = ai_client._messages_to_anthropic_payload(
        [
            {
                "role": "assistant",
                "content": "final",
                "reasoning_content": "hidden",
                "anthropic_thinking_blocks": [
                    {"type": "thinking", "thinking": "hidden", "signature": "sig-1"}
                ],
            }
        ]
    )

    assert converted[0]["content"][0] == {
        "type": "thinking",
        "thinking": "hidden",
        "signature": "sig-1",
    }
    assert converted[0]["content"][1] == {"type": "text", "text": "final"}


def test_stream_chat_anthropic_emits_streaming_thinking_and_tools(monkeypatch):
    """Anthropic SSE events should become normalized thinking/text/tool deltas."""

    class DummyResponse:
        status_code = 200
        text = ""

        def iter_lines(self, decode_unicode=True):
            events = [
                "event: content_block_start\n"
                'data: {"type":"content_block_start","index":0,"content_block":{"type":"thinking"}}\n\n',
                "event: content_block_delta\n"
                'data: {"type":"content_block_delta","index":0,"delta":{"type":"thinking_delta","thinking":"plan "}}\n\n',
                "event: content_block_delta\n"
                'data: {"type":"content_block_delta","index":0,"delta":{"type":"signature_delta","signature":"sig-1"}}\n\n',
                "event: content_block_stop\n" 'data: {"type":"content_block_stop","index":0}\n\n',
                "event: content_block_start\n"
                'data: {"type":"content_block_start","index":1,"content_block":{"type":"text","text":"hello "}}\n\n',
                "event: content_block_delta\n"
                'data: {"type":"content_block_delta","index":1,"delta":{"type":"text_delta","text":"world"}}\n\n',
                "event: content_block_start\n"
                'data: {"type":"content_block_start","index":2,"content_block":{"type":"tool_use","id":"call_1","name":"foo","input":{}}}\n\n',
                "event: content_block_delta\n"
                'data: {"type":"content_block_delta","index":2,"delta":{"type":"input_json_delta","partial_json":"{\\"x\\":1}"}}\n\n',
                "event: message_stop\n" 'data: {"type":"message_stop"}\n\n',
            ]
            for item in events:
                for line in item.splitlines():
                    yield line

        def close(self):
            return None

    old_style = ai_client.AI_API_STYLE
    old_url = ai_client.AI_BASE_URL
    old_key = ai_client.AI_API_KEY
    old_model = ai_client.AI_MODEL
    monkeypatch.setattr(ai_client.requests, "post", lambda *args, **kwargs: DummyResponse())
    ai_client.AI_API_STYLE = "anthropic"
    ai_client.AI_BASE_URL = "https://api.anthropic.com/v1"
    ai_client.AI_API_KEY = "sk-test"
    ai_client.AI_MODEL = "claude-3-7-sonnet-latest"

    try:
        chunks = list(
            ai_client.stream_chat(
                messages=[{"role": "user", "content": "hi"}],
                tools=[
                    {
                        "type": "function",
                        "function": {
                            "name": "foo",
                            "description": "",
                            "parameters": {"type": "object", "properties": {}, "required": []},
                        },
                    }
                ],
            )
        )
    finally:
        ai_client.AI_API_STYLE = old_style
        ai_client.AI_BASE_URL = old_url
        ai_client.AI_API_KEY = old_key
        ai_client.AI_MODEL = old_model

    reasoning = "".join(chunk.choices[0].delta.reasoning_content or "" for chunk in chunks)
    content = "".join(chunk.choices[0].delta.content or "" for chunk in chunks)
    tool_names = [
        chunk.choices[0].delta.tool_calls[0].function.name
        for chunk in chunks
        if chunk.choices[0].delta.tool_calls
    ]
    tool_args = "".join(
        chunk.choices[0].delta.tool_calls[0].function.arguments
        for chunk in chunks
        if chunk.choices[0].delta.tool_calls
    )
    thinking_blocks = [
        chunk.anthropic_thinking_blocks for chunk in chunks if chunk.anthropic_thinking_blocks
    ]

    assert reasoning == "plan "
    assert content == "hello world"
    assert tool_names[0] == "foo"
    assert '{"x":1}' in tool_args
    assert thinking_blocks[-1] == [{"type": "thinking", "thinking": "plan ", "signature": "sig-1"}]


def test_stream_chat_anthropic_retries_without_thinking(monkeypatch):
    """If Anthropic rejects thinking, the client should retry without it."""

    class ErrorResponse:
        status_code = 400
        text = '{"error":{"message":"extended thinking is not supported for this model"}}'

        def json(self):
            return {"error": {"message": "extended thinking is not supported for this model"}}

        def close(self):
            return None

    class StreamResponse:
        status_code = 200
        text = ""

        def iter_lines(self, decode_unicode=True):
            events = [
                "event: content_block_start\n"
                'data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":"ok"}}\n\n',
                "event: message_stop\n" 'data: {"type":"message_stop"}\n\n',
            ]
            for item in events:
                for line in item.splitlines():
                    yield line

        def close(self):
            return None

    calls = []

    def fake_post(*args, **kwargs):
        calls.append(kwargs["json"])
        if len(calls) == 1:
            return ErrorResponse()
        return StreamResponse()

    old_style = ai_client.AI_API_STYLE
    old_url = ai_client.AI_BASE_URL
    old_key = ai_client.AI_API_KEY
    old_model = ai_client.AI_MODEL
    monkeypatch.setattr(ai_client.requests, "post", fake_post)
    ai_client.AI_API_STYLE = "anthropic"
    ai_client.AI_BASE_URL = "https://api.anthropic.com/v1"
    ai_client.AI_API_KEY = "sk-test"
    ai_client.AI_MODEL = "claude-unknown"

    try:
        chunks = list(ai_client.stream_chat(messages=[{"role": "user", "content": "hi"}]))
    finally:
        ai_client.AI_API_STYLE = old_style
        ai_client.AI_BASE_URL = old_url
        ai_client.AI_API_KEY = old_key
        ai_client.AI_MODEL = old_model

    assert len(calls) == 2
    assert "thinking" in calls[0]
    assert "thinking" not in calls[1]
    assert "".join(chunk.choices[0].delta.content or "" for chunk in chunks) == "ok"

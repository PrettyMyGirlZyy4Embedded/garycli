"""Tests for AI provider style resolution and config persistence."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

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


def test_estimate_request_tokens_counts_tools_and_messages(monkeypatch):
    """Token estimate should include both message history and tool schemas."""

    monkeypatch.setattr(ai_client, "AI_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setattr(ai_client, "AI_API_STYLE", "openai")
    monkeypatch.setattr(ai_client, "AI_MODEL", "gpt-4o")

    messages = [
        {"role": "system", "content": "你是 Gary"},
        {"role": "user", "content": "帮我搜索 K230 文档"},
    ]
    tools = [
        {
            "type": "function",
            "function": {
                "name": "browser_search",
                "description": "搜索网页",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            },
        }
    ]

    estimate = ai_client.estimate_request_tokens(messages=messages, tools=tools, tool_choice="auto")

    assert estimate["provider"] == "openai"
    assert estimate["message_tokens"] > 0
    assert estimate["tools_tokens"] > 0
    assert estimate["total_tokens"] > estimate["message_tokens"]


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
                enable_thinking=True,
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
        chunks = list(
            ai_client.stream_chat(
                messages=[{"role": "user", "content": "hi"}], enable_thinking=True
            )
        )
    finally:
        ai_client.AI_API_STYLE = old_style
        ai_client.AI_BASE_URL = old_url
        ai_client.AI_API_KEY = old_key
        ai_client.AI_MODEL = old_model

    assert len(calls) == 2
    assert "thinking" in calls[0]
    assert "thinking" not in calls[1]
    assert "".join(chunk.choices[0].delta.content or "" for chunk in chunks) == "ok"


def test_stream_chat_anthropic_disables_thinking_by_default(monkeypatch):
    """Anthropic requests should not send thinking unless explicitly enabled."""

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
        return StreamResponse()

    old_style = ai_client.AI_API_STYLE
    old_url = ai_client.AI_BASE_URL
    old_key = ai_client.AI_API_KEY
    old_model = ai_client.AI_MODEL
    monkeypatch.setattr(ai_client.requests, "post", fake_post)
    ai_client.AI_API_STYLE = "anthropic"
    ai_client.AI_BASE_URL = "https://api.anthropic.com/v1"
    ai_client.AI_API_KEY = "sk-test"
    ai_client.AI_MODEL = "claude-3-7-sonnet-latest"

    try:
        chunks = list(ai_client.stream_chat(messages=[{"role": "user", "content": "hi"}]))
    finally:
        ai_client.AI_API_STYLE = old_style
        ai_client.AI_BASE_URL = old_url
        ai_client.AI_API_KEY = old_key
        ai_client.AI_MODEL = old_model

    assert len(calls) == 1
    assert "thinking" not in calls[0]
    assert "".join(chunk.choices[0].delta.content or "" for chunk in chunks) == "ok"


def test_stream_chat_gemini_disables_include_thoughts_by_default(monkeypatch):
    """Gemini should not request thought parts unless explicitly enabled."""

    captured = {}

    class DummyThinkingConfig:
        def __init__(self, include_thoughts):
            self.include_thoughts = include_thoughts

    class DummyAutomaticFunctionCallingConfig:
        def __init__(self, disable):
            self.disable = disable

    class DummyGenerateContentConfig:
        def __init__(self, **kwargs):
            self.system_instruction = kwargs.get("system_instruction")
            self.temperature = kwargs.get("temperature")
            self.tools = kwargs.get("tools")
            self.automatic_function_calling = kwargs.get("automatic_function_calling")
            self.thinking_config = kwargs.get("thinking_config")

    class DummyPart:
        def __init__(
            self,
            text=None,
            thought=False,
            function_call=None,
            thought_signature=None,
            function_response=None,
        ):
            self.text = text
            self.thought = thought
            self.function_call = function_call
            self.thought_signature = thought_signature
            self.function_response = function_response

        @classmethod
        def from_text(cls, text):
            return cls(text=text)

    class DummyContent:
        def __init__(self, role, parts):
            self.role = role
            self.parts = parts

    class DummyModels:
        def generate_content_stream(self, *, model, contents, config):
            captured["model"] = model
            captured["contents"] = contents
            captured["config"] = config
            return iter([])

    class DummyClient:
        def __init__(self):
            self.models = DummyModels()

    dummy_types = SimpleNamespace(
        ThinkingConfig=DummyThinkingConfig,
        AutomaticFunctionCallingConfig=DummyAutomaticFunctionCallingConfig,
        GenerateContentConfig=DummyGenerateContentConfig,
        Part=DummyPart,
        Content=DummyContent,
        FunctionDeclaration=lambda **kwargs: kwargs,
        Tool=lambda **kwargs: kwargs,
        FunctionCall=lambda **kwargs: kwargs,
        FunctionResponse=lambda **kwargs: kwargs,
    )

    monkeypatch.setattr(ai_client, "_load_gemini_sdk", lambda: (object(), dummy_types))
    monkeypatch.setattr(ai_client, "get_ai_client", lambda timeout=180.0: DummyClient())
    monkeypatch.setattr(ai_client, "AI_API_STYLE", "gemini")
    monkeypatch.setattr(
        ai_client, "AI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta"
    )
    monkeypatch.setattr(ai_client, "AI_MODEL", "gemini-2.5-flash")

    list(ai_client.stream_chat(messages=[{"role": "user", "content": "hi"}]))

    assert captured["config"].thinking_config.include_thoughts is False

"""Tests for API message normalization in the agent."""

from __future__ import annotations

from types import SimpleNamespace

from ai.client import estimate_request_tokens
from core.agent import (
    MAX_CONTEXT_TOKENS,
    MAX_TOOL_RESULT_LEN,
    TRUNCATED_TOOL_RESULT_NOTICE,
    STM32Agent,
)


def test_messages_for_api_merges_multiple_system_messages():
    """Only one system message should be sent to providers that reject later system roles."""

    agent = object.__new__(STM32Agent)
    agent._pending_system_hint = ""
    agent.messages = [
        {"role": "system", "content": "base prompt"},
        {"role": "user", "content": "hello"},
        {"role": "system", "content": "legacy hint"},
        {"role": "assistant", "content": "hi"},
    ]

    result = agent._messages_for_api()

    assert [item["role"] for item in result].count("system") == 1
    assert result[0]["role"] == "system"
    assert "base prompt" in result[0]["content"]
    assert "legacy hint" in result[0]["content"]


def test_messages_for_api_appends_pending_web_hint_into_first_system_message():
    """The one-turn browse hint should be folded into the first system prompt."""

    agent = object.__new__(STM32Agent)
    agent._pending_system_hint = "web hint"
    agent.messages = [
        {"role": "system", "content": "base prompt"},
        {"role": "user", "content": "search docs"},
    ]

    result = agent._messages_for_api()

    assert result[0]["role"] == "system"
    assert "base prompt" in result[0]["content"]
    assert "web hint" in result[0]["content"]
    assert [item["role"] for item in result] == ["system", "user"]


def test_messages_for_api_strips_reasoning_and_provider_thinking_blocks():
    """Thinking content should not be fed back into later model turns."""

    agent = object.__new__(STM32Agent)
    agent._pending_system_hint = ""
    agent.messages = [
        {"role": "system", "content": "base prompt"},
        {
            "role": "assistant",
            "content": "final",
            "reasoning_content": "hidden plan",
            "anthropic_thinking_blocks": [{"type": "thinking", "thinking": "hidden plan"}],
        },
    ]

    result = agent._messages_for_api()

    assert result == [
        {"role": "system", "content": "base prompt"},
        {"role": "assistant", "content": "final"},
    ]


def test_tokens_estimate_uses_request_payload_and_tools(monkeypatch):
    """Status-bar token estimate should exclude the fixed first-turn overhead."""

    tool_schemas = [
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

    monkeypatch.setattr("core.agent.TOOL_SCHEMAS", tool_schemas)
    monkeypatch.setattr("core.agent.select_tool_schemas", lambda chip, user_input="": tool_schemas)
    monkeypatch.setattr("core.agent.AI_MODEL", "gpt-4o")
    monkeypatch.setattr("core.agent.AI_TEMPERATURE", 1)

    agent = object.__new__(STM32Agent)
    agent._pending_system_hint = "web hint"
    agent.messages = [
        {"role": "system", "content": "base prompt"},
        {"role": "user", "content": "search docs"},
    ]

    request_total = estimate_request_tokens(
        messages=agent._messages_for_api(),
        tools=tool_schemas,
        tool_choice="auto",
        model="gpt-4o",
        temperature=1,
    )["total_tokens"]
    base_total = estimate_request_tokens(
        messages=[{"role": "system", "content": "base prompt"}],
        tools=tool_schemas,
        tool_choice="auto",
        model="gpt-4o",
        temperature=1,
    )["total_tokens"]

    assert agent._tokens() == request_total - base_total


def test_context_usage_reports_remaining_percent(monkeypatch):
    """Context usage should expose remaining-window percentage for the status bar."""

    def fake_estimate_request_tokens(**kwargs):
        messages = kwargs.get("messages") or []
        if len(messages) == 1 and messages[0].get("role") == "system":
            return {"total_tokens": 12000}
        return {"total_tokens": 99720}

    monkeypatch.setattr(
        "core.agent.estimate_request_tokens",
        fake_estimate_request_tokens,
    )
    monkeypatch.setattr("core.agent.get_context", lambda: SimpleNamespace(thinking_enabled=False))
    monkeypatch.setattr("core.agent.TOOL_SCHEMAS", [])
    monkeypatch.setattr("core.agent.AI_MODEL", "gpt-4o")
    monkeypatch.setattr("core.agent.AI_TEMPERATURE", 1)

    agent = object.__new__(STM32Agent)
    agent._pending_system_hint = ""
    agent.messages = [
        {"role": "system", "content": "base prompt"},
        {"role": "user", "content": "search docs"},
    ]

    usage = agent._context_usage()

    assert usage["base_tokens"] == 12000
    assert usage["request_tokens"] == 99720
    assert usage["used_tokens"] == 87720
    assert usage["limit_tokens"] == MAX_CONTEXT_TOKENS - 12000
    assert usage["left_percent"] == int(
        round(((usage["limit_tokens"] - 87720) / usage["limit_tokens"]) * 100)
    )


def test_context_usage_starts_full_before_first_user_turn(monkeypatch):
    """The initial status should show a full remaining budget before any chat turns."""

    monkeypatch.setattr(
        "core.agent.estimate_request_tokens", lambda **kwargs: {"total_tokens": 12000}
    )
    monkeypatch.setattr("core.agent.get_context", lambda: SimpleNamespace(thinking_enabled=False))
    monkeypatch.setattr("core.agent.TOOL_SCHEMAS", [])
    monkeypatch.setattr("core.agent.AI_MODEL", "gpt-4o")
    monkeypatch.setattr("core.agent.AI_TEMPERATURE", 1)

    agent = object.__new__(STM32Agent)
    agent._pending_system_hint = ""
    agent.messages = [{"role": "system", "content": "base prompt"}]

    usage = agent._context_usage()

    assert usage["used_tokens"] == 0
    assert usage["left_percent"] == 100


def test_context_usage_uses_selected_tool_subset(monkeypatch):
    """Token estimation should use the dynamically selected tool subset."""

    captured = {}
    selected_tools = [
        {
            "type": "function",
            "function": {
                "name": "browser_search",
                "description": "搜索网页",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        }
    ]

    monkeypatch.setattr(
        "core.agent.select_tool_schemas",
        lambda chip, user_input="": selected_tools,
    )

    def fake_estimate_request_tokens(**kwargs):
        captured["tools"] = kwargs.get("tools")
        return {"total_tokens": 123}

    monkeypatch.setattr("core.agent.estimate_request_tokens", fake_estimate_request_tokens)
    monkeypatch.setattr(
        "core.agent.get_context",
        lambda: SimpleNamespace(chip="STM32F103C8T6", thinking_enabled=False),
    )
    monkeypatch.setattr("core.agent.AI_MODEL", "gpt-4o")
    monkeypatch.setattr("core.agent.AI_TEMPERATURE", 1)

    agent = object.__new__(STM32Agent)
    agent._tool_schema_cache = []
    agent._tool_schema_signature = None
    agent._current_tool_task_hint = "搜索文档"
    agent._pending_system_hint = ""
    agent.messages = [
        {"role": "system", "content": "base prompt"},
        {"role": "user", "content": "search docs"},
    ]

    agent._context_usage()

    assert captured["tools"] == selected_tools


def test_compose_system_prompt_caches_static_and_dynamic_parts(monkeypatch):
    """Static prompt fragments should be reused while member content only updates on hash changes."""

    agent = object.__new__(STM32Agent)
    agent._static_prompt_cache = ""
    agent._static_prompt_signature = None
    agent._dynamic_prompt_cache = ""
    agent._dynamic_prompt_signature = None
    agent._system_prompt_cache = ""
    agent._system_prompt_signature = None

    ctx = SimpleNamespace(chip="STM32F103C8T6", cli_language="zh", hw_connected=False)
    build_calls = {"system": 0, "debug": 0, "member": 0}
    member_states = [("member-v1", "hash-1"), ("member-v1", "hash-1"), ("member-v2", "hash-2")]

    monkeypatch.setattr("core.agent.get_context", lambda: ctx)
    monkeypatch.setattr(
        "core.agent.build_system_prompt",
        lambda chip, language, hw_connected: build_calls.__setitem__(
            "system", build_calls["system"] + 1
        )
        or "static-base",
    )
    monkeypatch.setattr(
        "core.agent.get_debug_prompt",
        lambda error_type, context: build_calls.__setitem__("debug", build_calls["debug"] + 1)
        or f"debug-{error_type}",
    )
    monkeypatch.setattr(
        "core.agent.get_member_prompt_section_state",
        lambda chip: member_states[min(build_calls["member"], len(member_states) - 1)],
    )
    monkeypatch.setattr(
        "core.agent._get_manager",
        lambda: SimpleNamespace(get_all_prompt_additions=lambda: ""),
    )

    def _member_state(chip):
        index = min(build_calls["member"], len(member_states) - 1)
        build_calls["member"] += 1
        return member_states[index]

    monkeypatch.setattr("core.agent.get_member_prompt_section_state", _member_state)

    prompt1 = agent._compose_system_prompt()
    prompt2 = agent._compose_system_prompt()
    prompt3 = agent._compose_system_prompt()

    assert build_calls["system"] == 1
    assert build_calls["debug"] == 3
    assert build_calls["member"] == 3
    assert prompt1 == prompt2
    assert prompt3 != prompt2
    assert "member-v1" in prompt1
    assert "member-v2" in prompt3


def test_truncate_result_uses_shorter_limit_and_notice():
    """Tool results should be capped at 4000 chars and include the truncation notice."""

    agent = object.__new__(STM32Agent)

    result = agent._truncate_result("a" * (MAX_TOOL_RESULT_LEN + 500), "browser_open")

    assert len(result) <= MAX_TOOL_RESULT_LEN
    assert TRUNCATED_TOOL_RESULT_NOTICE in result


def test_truncate_history_is_idempotent():
    """Repeated history compaction should be safe after the first pass."""

    agent = object.__new__(STM32Agent)
    agent.interactive = False
    agent.messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "a" * 70000},
        {"role": "assistant", "content": "b" * 70000},
        {"role": "tool", "content": "c" * 70000},
    ]
    agent._context_usage = lambda: {
        "request_tokens": 0,
        "base_tokens": 12000,
        "used_tokens": 300000 if len(agent.messages) > 3 else 200000,
        "left_tokens": 0,
        "left_percent": 0,
        "limit_tokens": MAX_CONTEXT_TOKENS - 12000,
    }

    agent._truncate_history()
    first_pass = [dict(item) for item in agent.messages]
    agent._truncate_history()

    assert agent.messages == first_pass


def test_chat_truncates_history_again_after_tool_results(monkeypatch):
    """The agent should compact history again after tool results are written back."""

    class DummyChunk:
        def __init__(self, *, content="", tool_calls=None):
            self.choices = [
                SimpleNamespace(
                    delta=SimpleNamespace(
                        content=content,
                        tool_calls=tool_calls or [],
                        reasoning_content=None,
                    )
                )
            ]
            self.anthropic_thinking_blocks = None

    agent = object.__new__(STM32Agent)
    agent.client = None
    agent.interactive = False
    agent.messages = [{"role": "system", "content": "sys"}]
    agent._pending_system_hint = ""
    agent.thinking_log = []
    agent.refresh_system_prompt = lambda: None
    agent._prepare_web_research_hint = lambda user_input: None

    truncate_calls: list[list[str]] = []

    def _record_truncate():
        truncate_calls.append([message.get("role") for message in agent.messages])

    agent._truncate_history = _record_truncate

    call_index = {"value": 0}

    def fake_stream_chat(**kwargs):
        call_index["value"] += 1
        if call_index["value"] == 1:
            return iter(
                [
                    DummyChunk(
                        tool_calls=[
                            SimpleNamespace(
                                index=0,
                                id="call_1",
                                function=SimpleNamespace(
                                    name="browser_open",
                                    arguments='{"url":"https://example.com"}',
                                    thought_signature=None,
                                ),
                                thought_signature=None,
                            )
                        ]
                    )
                ]
            )
        return iter([DummyChunk(content="done")])

    monkeypatch.setattr("core.agent.stream_chat", fake_stream_chat)
    monkeypatch.setattr(
        "core.agent.dispatch_tool_call",
        lambda func_name, args, get_context_fn=None: {"content": "x" * 6000},
    )
    monkeypatch.setattr("core.agent.get_context", lambda: SimpleNamespace(thinking_enabled=False))

    reply = agent.chat("search docs", stream_to_console=False)

    assert reply == "done"
    assert len(truncate_calls) >= 2
    assert any("tool" in roles for roles in truncate_calls[1:])


def test_chat_truncates_history_after_current_user_input(monkeypatch):
    """The first compaction pass should happen after the current user turn is appended."""

    class DummyChunk:
        def __init__(self, *, content="", tool_calls=None):
            self.choices = [
                SimpleNamespace(
                    delta=SimpleNamespace(
                        content=content,
                        tool_calls=tool_calls or [],
                        reasoning_content=None,
                    )
                )
            ]
            self.anthropic_thinking_blocks = None

    agent = object.__new__(STM32Agent)
    agent.client = None
    agent.interactive = False
    agent.messages = [{"role": "system", "content": "sys"}]
    agent._pending_system_hint = ""
    agent.thinking_log = []
    agent.refresh_system_prompt = lambda: None
    agent._prepare_web_research_hint = lambda user_input: None

    truncate_snapshots: list[list[str]] = []
    agent._truncate_history = lambda: truncate_snapshots.append(
        [message.get("role") for message in agent.messages]
    )

    monkeypatch.setattr(
        "core.agent.stream_chat",
        lambda **kwargs: iter([DummyChunk(content="ok")]),
    )
    monkeypatch.setattr("core.agent.get_context", lambda: SimpleNamespace(thinking_enabled=False))

    reply = agent.chat("hello", stream_to_console=False)

    assert reply == "ok"
    assert truncate_snapshots[0] == ["system", "user"]

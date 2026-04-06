"""Tests for system prompt web-research guidance."""

from __future__ import annotations

from prompts.system import build_system_prompt, build_web_research_hint, should_force_web_research


def test_build_system_prompt_includes_web_workflow_in_chinese():
    """Chinese prompt should instruct the model to use the structured browser flow."""

    prompt = build_system_prompt("STM32F103C8T6", "zh", hw_connected=False)

    assert "browser_search -> browser_open_result -> browser_extract_links" in prompt
    assert "python setup.py --searxng" in prompt
    assert "不要擅自切换到公共搜索后端" in prompt
    assert "必须先联网查证" in prompt
    assert "不要靠记忆硬猜" in prompt
    assert "你的名字是 `Gary`" in prompt
    assert "产品全名是 `GaryCLI`" in prompt
    assert "你是 `Gary`，也就是 `GaryCLI` 的助手" in prompt
    assert "Gary Dev Agent" not in prompt


def test_build_system_prompt_includes_web_workflow_in_english():
    """English prompt should also describe the preferred browser workflow."""

    prompt = build_system_prompt("STM32F103C8T6", "en", hw_connected=False)

    assert "browser_search -> browser_open_result -> browser_extract_links" in prompt
    assert "python setup.py --searxng" in prompt
    assert "Do not silently switch to public search backends" in prompt
    assert "You must search first" in prompt
    assert "default to web verification instead of guessing from memory" in prompt
    assert "Your name is `Gary`." in prompt
    assert "The product name is `GaryCLI`." in prompt
    assert "you are `Gary`, the assistant for `GaryCLI`" in prompt
    assert "Gary Dev Agent" not in prompt


def test_should_force_web_research_matches_latest_and_docs_queries():
    """Explicit latest/docs style requests should trigger the one-turn web directive."""

    assert should_force_web_research("帮我搜索一下 K230 官方 API 文档")
    assert should_force_web_research("latest CanMV K230 docs")
    assert not should_force_web_research("把 LED 闪烁改成 200ms")


def test_build_web_research_hint_contains_browse_first_directive():
    """The transient web hint should explicitly require searching before answering."""

    zh_hint = build_web_research_hint("zh")
    en_hint = build_web_research_hint("en")

    assert "回答前先用 `browser_search`" in zh_hint
    assert "Before answering, use `browser_search`" in en_hint

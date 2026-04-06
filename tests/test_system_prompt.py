"""Tests for system prompt web-research guidance."""

from __future__ import annotations

from prompts.system import build_system_prompt


def test_build_system_prompt_includes_web_workflow_in_chinese():
    """Chinese prompt should instruct the model to use the structured browser flow."""

    prompt = build_system_prompt("STM32F103C8T6", "zh", hw_connected=False)

    assert "browser_search -> browser_open_result -> browser_extract_links" in prompt
    assert "python setup.py --searxng" in prompt
    assert "不要擅自切换到公共搜索后端" in prompt


def test_build_system_prompt_includes_web_workflow_in_english():
    """English prompt should also describe the preferred browser workflow."""

    prompt = build_system_prompt("STM32F103C8T6", "en", hw_connected=False)

    assert "browser_search -> browser_open_result -> browser_extract_links" in prompt
    assert "python setup.py --searxng" in prompt
    assert "Do not silently switch to public search backends" in prompt

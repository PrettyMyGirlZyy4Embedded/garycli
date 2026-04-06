"""Interactive AI backend configuration helpers."""

from __future__ import annotations

from typing import Any, Callable

from ai.client import (
    _API_STYLE_OPTIONS,
    _AI_PRESETS,
    _api_key_is_placeholder,
    _mask_key,
    _normalize_api_style,
    _read_ai_config,
    _write_ai_config,
    get_ai_client,
    provider_name,
    reload_ai_config,
)
from tui.ui import console as CONSOLE


def configure_ai_cli(
    *,
    sync_ai_runtime_settings: Callable[[dict[str, Any] | None], dict[str, Any]],
    agent: Any = None,
) -> None:
    """交互式配置 AI 接口。"""

    import getpass as _getpass

    CONSOLE.print()
    CONSOLE.rule("[bold cyan]  配置 AI 后端接口[/]")
    CONSOLE.print()

    cur_key, cur_url, cur_model, cur_style = _read_ai_config()
    is_configured = bool(cur_key and not _api_key_is_placeholder(cur_key))

    if is_configured:
        CONSOLE.print(f"  [dim]当前 API Key :[/] {_mask_key(cur_key)}")
        CONSOLE.print(f"  [dim]当前接口类型:[/] {provider_name(cur_url, cur_model, cur_style)}")
        CONSOLE.print(f"  [dim]当前 Base URL:[/] {cur_url}")
        CONSOLE.print(f"  [dim]当前 Model   :[/] {cur_model}")
        CONSOLE.print()

    CONSOLE.print("[bold cyan]  请选择 AI 服务提供商：[/]")
    for index, (name, url, _, style) in enumerate(_AI_PRESETS, 1):
        url_hint = f"  [dim]{url[:55]}[/]" if url else ""
        style_hint = f"  [dim]{provider_name(url, None, style)}[/]"
        CONSOLE.print(f"    [yellow]{index}[/].  {name:<24}{style_hint}{url_hint}")
    CONSOLE.print()

    valid = [str(index) for index in range(1, len(_AI_PRESETS) + 1)]
    choice = ""
    while choice not in valid:
        try:
            choice = input(f"  输入序号 [1-{len(_AI_PRESETS)}] (回车取消): ").strip()
        except (EOFError, KeyboardInterrupt):
            CONSOLE.print("\n[dim]已取消[/]")
            return
        if choice == "":
            CONSOLE.print("[dim]已取消[/]")
            return

    preset_name, preset_url, preset_model, preset_style = _AI_PRESETS[int(choice) - 1]

    api_style = _normalize_api_style(preset_style, default="openai") or "openai"
    if not preset_url:
        CONSOLE.print("  [bold cyan]请选择接口协议类型：[/]")
        for index, (_, label, desc) in enumerate(_API_STYLE_OPTIONS, 1):
            CONSOLE.print(f"    [yellow]{index}[/].  {label:<24}  [dim]{desc}[/]")
        style_valid = [str(index) for index in range(1, len(_API_STYLE_OPTIONS) + 1)]
        style_choice = ""
        while style_choice not in style_valid:
            try:
                style_choice = input(
                    f"  输入协议类型 [1-{len(_API_STYLE_OPTIONS)}] (回车取消): "
                ).strip()
            except (EOFError, KeyboardInterrupt):
                CONSOLE.print("\n[dim]已取消[/]")
                return
            if style_choice == "":
                CONSOLE.print("[dim]已取消[/]")
                return
        api_style = _API_STYLE_OPTIONS[int(style_choice) - 1][0]
        CONSOLE.print(f"  [dim]接口类型: {provider_name(api_style=api_style)}[/]")

    if preset_url:
        base_url = preset_url
        CONSOLE.print(f"  [dim]Base URL: {base_url}[/]")
    else:
        default_base_urls = {
            "openai": cur_url if cur_style == "openai" and cur_url else "https://api.openai.com/v1",
            "anthropic": (
                cur_url if cur_style == "anthropic" and cur_url else "https://api.anthropic.com/v1"
            ),
            "gemini": (
                cur_url
                if cur_style == "gemini" and cur_url
                else "https://generativelanguage.googleapis.com/v1beta"
            ),
        }
        try:
            base_hint = default_base_urls.get(api_style, cur_url or "https://api.openai.com/v1")
            entered = input(f"  Base URL (默认 {base_hint}): ").strip()
            base_url = entered if entered else base_hint
        except (EOFError, KeyboardInterrupt):
            base_url = cur_url

    default_models = {
        "openai": "gpt-4o",
        "anthropic": "claude-3-7-sonnet-latest",
        "gemini": "gemini-2.5-flash",
    }
    current_model_for_style = cur_model if cur_style == api_style else ""
    default_model = preset_model or current_model_for_style or default_models.get(api_style, "")
    try:
        hint = f" (默认 {default_model})" if default_model else ""
        entered = input(f"  Model 名称{hint}: ").strip()
        model = entered if entered else default_model
    except (EOFError, KeyboardInterrupt):
        model = default_model

    CONSOLE.print()
    if preset_name == "Ollama (本地)":
        api_key = "ollama"
        CONSOLE.print("  [dim]Ollama 本地模式，API Key 自动设为 ollama[/]")
    else:
        CONSOLE.print(f"  [dim]请输入 {preset_name} API Key（不显示输入内容）[/]")
        try:
            api_key = _getpass.getpass("  API Key: ")
        except Exception:
            try:
                api_key = input("  API Key: ").strip()
            except (EOFError, KeyboardInterrupt):
                api_key = ""
        if not api_key:
            if is_configured:
                CONSOLE.print("  [dim]未输入，保留原有 Key[/]")
                api_key = cur_key
            else:
                CONSOLE.print("[yellow]  未输入 API Key，配置取消[/]")
                return

    if _write_ai_config(api_key, base_url, model, api_style):
        sync_ai_runtime_settings(reload_ai_config())
        CONSOLE.print()
        CONSOLE.print("[green]  ✓ 配置已保存到 config.py[/]")
        CONSOLE.print(f"  [green]✓[/] 服务商  {preset_name}")
        CONSOLE.print(f"  [green]✓[/] 接口类型 {provider_name(base_url, model, api_style)}")
        CONSOLE.print(f"  [green]✓[/] API Key {_mask_key(api_key)}")
        CONSOLE.print(f"  [green]✓[/] Base URL {base_url}")
        CONSOLE.print(f"  [green]✓[/] Model   {model}")
        if agent is not None:
            agent.client = get_ai_client(timeout=180.0, force_reload=True)
            CONSOLE.print("  [green]✓[/] AI 客户端已热重载，无需重启")
    else:
        CONSOLE.print("[red]  ✗ 写入 config.py 失败[/]")
    CONSOLE.print()


__all__ = ["configure_ai_cli"]

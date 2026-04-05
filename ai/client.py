"""AI client management and provider-specific streaming helpers."""

from __future__ import annotations

import base64
import copy
import importlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Optional
from urllib.parse import urlparse

import config as _cfg
import requests

_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _ROOT / "config.py"

_AI_PRESETS = [
    ("OpenAI", "https://api.openai.com/v1", "gpt-4o", "openai"),
    ("DeepSeek", "https://api.deepseek.com/v1", "deepseek-chat", "openai"),
    ("Kimi / Moonshot", "https://api.moonshot.cn/v1", "kimi-k2.5", "openai"),
    (
        "Google Gemini (官方 SDK)",
        "https://generativelanguage.googleapis.com/v1beta",
        "gemini-2.5-flash",
        "gemini",
    ),
    (
        "通义千问 (阿里云)",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "qwen-plus",
        "openai",
    ),
    ("智谱 GLM", "https://open.bigmodel.cn/api/paas/v4/", "glm-4-flash", "openai"),
    ("Ollama (本地)", "http://127.0.0.1:11434/v1", "qwen2.5-coder:14b", "openai"),
    ("自定义 / Other", "", "", ""),
]
_API_STYLE_OPTIONS = (
    ("openai", "OpenAI Compatible", "兼容 /v1/chat/completions 等 OpenAI 风格接口"),
    ("anthropic", "Anthropic Messages", "兼容 /v1/messages 的 Anthropic / Claude 风格接口"),
    ("gemini", "Gemini Official SDK", "Google Gemini 官方 SDK / generativelanguage.googleapis.com"),
)

_CONFIG_KEYS_TO_RELOAD = (
    "AI_API_KEY",
    "AI_BASE_URL",
    "AI_MODEL",
    "AI_API_STYLE",
    "AI_TEMPERATURE",
    "DEFAULT_CHIP",
    "DEFAULT_CLOCK",
    "CLI_LANGUAGE",
    "SERIAL_PORT",
    "SERIAL_BAUD",
    "POST_FLASH_DELAY",
    "REGISTER_READ_DELAY",
)

AI_API_KEY = getattr(_cfg, "AI_API_KEY", "")
AI_BASE_URL = getattr(_cfg, "AI_BASE_URL", "https://api.openai.com/v1")
AI_MODEL = getattr(_cfg, "AI_MODEL", "gpt-4o")
AI_API_STYLE = getattr(_cfg, "AI_API_STYLE", "")
AI_TEMPERATURE = getattr(_cfg, "AI_TEMPERATURE", 1)
DEFAULT_CHIP = getattr(_cfg, "DEFAULT_CHIP", "")
DEFAULT_CLOCK = getattr(_cfg, "DEFAULT_CLOCK", "HSI_internal")
CLI_LANGUAGE = getattr(_cfg, "CLI_LANGUAGE", "zh")
SERIAL_PORT = getattr(_cfg, "SERIAL_PORT", "")
SERIAL_BAUD = getattr(_cfg, "SERIAL_BAUD", 115200)
POST_FLASH_DELAY = getattr(_cfg, "POST_FLASH_DELAY", 1.5)
REGISTER_READ_DELAY = getattr(_cfg, "REGISTER_READ_DELAY", 0.3)

_AI_CLIENT: Any | None = None
_AI_CLIENT_SIGNATURE: tuple[str, str, str, float] | None = None


@dataclass
class _NormalizedFunctionDelta:
    name: str = ""
    arguments: str = ""
    thought_signature: str | None = None


@dataclass
class _NormalizedToolCallDelta:
    index: int
    id: str = ""
    function: _NormalizedFunctionDelta = field(default_factory=_NormalizedFunctionDelta)
    thought_signature: str | None = None


@dataclass
class _NormalizedDelta:
    content: str | None = None
    reasoning_content: str | None = None
    tool_calls: list[_NormalizedToolCallDelta] | None = None


@dataclass
class _NormalizedChoice:
    delta: _NormalizedDelta


@dataclass
class _NormalizedChunk:
    choices: list[_NormalizedChoice]
    _raw_tool_calls: list[dict[str, Any]] = field(default_factory=list)
    anthropic_thinking_blocks: list[dict[str, Any]] | None = None

    def model_dump(self) -> dict[str, Any]:
        return {
            "choices": [
                {
                    "delta": {
                        "tool_calls": self._raw_tool_calls,
                    }
                }
            ]
        }


def _load_openai_class() -> Any | None:
    """Import and return the OpenAI client class when available."""

    try:
        from openai import OpenAI  # type: ignore
    except ImportError:
        return None
    return OpenAI


def _load_gemini_sdk() -> tuple[Any | None, Any | None]:
    """Import and return `(genai, types)` from the official Gemini SDK."""

    try:
        from google import genai  # type: ignore
        from google.genai import types  # type: ignore
    except ImportError:
        return None, None
    return genai, types


def _parse_cli_language(value: Any, default: Optional[str] = None) -> Optional[str]:
    """Normalize CLI language aliases to `en` or `zh`."""

    raw = str(value or "").strip().lower()
    if not raw:
        return default
    if raw in {"en", "eng", "english", "英文"}:
        return "en"
    if raw in {"zh", "cn", "zh-cn", "zh_cn", "chinese", "中文"}:
        return "zh"
    return None


def _normalize_cli_language(value: Any) -> str:
    """Return a safe CLI language code."""

    return _parse_cli_language(value, default="zh") or "zh"


CLI_LANGUAGE = _normalize_cli_language(CLI_LANGUAGE)


def _current_settings() -> dict[str, Any]:
    """Return the current runtime configuration snapshot."""

    return {
        "AI_API_KEY": AI_API_KEY,
        "AI_BASE_URL": AI_BASE_URL,
        "AI_MODEL": AI_MODEL,
        "AI_API_STYLE": AI_API_STYLE,
        "AI_TEMPERATURE": AI_TEMPERATURE,
        "DEFAULT_CHIP": DEFAULT_CHIP,
        "DEFAULT_CLOCK": DEFAULT_CLOCK,
        "CLI_LANGUAGE": CLI_LANGUAGE,
        "SERIAL_PORT": SERIAL_PORT,
        "SERIAL_BAUD": SERIAL_BAUD,
        "POST_FLASH_DELAY": POST_FLASH_DELAY,
        "REGISTER_READ_DELAY": REGISTER_READ_DELAY,
    }


def _upsert_config_assignment(text: str, key: str, value: Any) -> str:
    """Insert or replace a single assignment in `config.py` text."""

    line = f"{key} = {json.dumps(value, ensure_ascii=False)}"
    pattern = rf"^{key}\s*=.*$"
    if re.search(pattern, text, re.MULTILINE):
        return re.sub(pattern, line, text, flags=re.MULTILINE)
    if text and not text.endswith("\n"):
        text += "\n"
    return text + line + "\n"


def _normalize_api_style(value: Any, default: Optional[str] = None) -> Optional[str]:
    """Normalize API style aliases to `openai`, `anthropic`, or `gemini`."""

    raw = str(value or "").strip().lower()
    if not raw:
        return default
    aliases = {
        "openai": "openai",
        "openai-compatible": "openai",
        "compatible": "openai",
        "chat-completions": "openai",
        "anthropic": "anthropic",
        "claude": "anthropic",
        "messages": "anthropic",
        "anthropic-messages": "anthropic",
        "gemini": "gemini",
        "google": "gemini",
        "google-gemini": "gemini",
        "gemini-sdk": "gemini",
    }
    return aliases.get(raw, default)


def _read_ai_config() -> tuple[str, str, str, str]:
    """Read `(api_key, base_url, model, api_style)` from `config.py`."""

    if not _CONFIG_PATH.exists():
        return (
            AI_API_KEY,
            AI_BASE_URL,
            AI_MODEL,
            _normalize_api_style(AI_API_STYLE, default="") or "",
        )
    text = _CONFIG_PATH.read_text(encoding="utf-8")

    def _get(pattern: str) -> str:
        match = re.search(pattern, text, re.MULTILINE)
        return match.group(1).strip() if match else ""

    return (
        _get(r'^AI_API_KEY\s*=\s*["\']([^"\']*)["\']') or AI_API_KEY,
        _get(r'^AI_BASE_URL\s*=\s*["\']([^"\']*)["\']') or AI_BASE_URL,
        _get(r'^AI_MODEL\s*=\s*["\']([^"\']*)["\']') or AI_MODEL,
        _normalize_api_style(
            _get(r'^AI_API_STYLE\s*=\s*["\']([^"\']*)["\']') or AI_API_STYLE,
            default="",
        )
        or "",
    )


def _write_config_assignments(updates: dict[str, Any]) -> bool:
    """Update multiple assignments in `config.py` in place."""

    if not _CONFIG_PATH.exists():
        return False
    text = _CONFIG_PATH.read_text(encoding="utf-8")
    for key, value in updates.items():
        text = _upsert_config_assignment(text, key, value)
    _CONFIG_PATH.write_text(text, encoding="utf-8")
    return True


def _write_ai_config(api_key: str, base_url: str, model: str, api_style: str = "") -> bool:
    """Persist the core AI settings to `config.py`."""

    return _write_config_assignments(
        {
            "AI_API_KEY": api_key,
            "AI_BASE_URL": base_url,
            "AI_MODEL": model,
            "AI_API_STYLE": _normalize_api_style(api_style, default="") or "",
        }
    )


def _write_cli_language_config(language: str) -> bool:
    """Persist the CLI language to `config.py`."""

    return _write_config_assignments({"CLI_LANGUAGE": _normalize_cli_language(language)})


def _reload_ai_globals() -> dict[str, Any]:
    """Reload runtime settings from `config.py` and invalidate the cached client if needed."""

    global AI_API_KEY
    global AI_BASE_URL
    global AI_MODEL
    global AI_API_STYLE
    global AI_TEMPERATURE
    global DEFAULT_CHIP
    global DEFAULT_CLOCK
    global CLI_LANGUAGE
    global SERIAL_PORT
    global SERIAL_BAUD
    global POST_FLASH_DELAY
    global REGISTER_READ_DELAY
    global _AI_CLIENT
    global _AI_CLIENT_SIGNATURE

    previous_signature = (AI_API_KEY, AI_BASE_URL, AI_MODEL, AI_API_STYLE)
    importlib.reload(_cfg)
    defaults = {
        "AI_API_KEY": "",
        "AI_BASE_URL": "https://api.openai.com/v1",
        "AI_MODEL": "gpt-4o",
        "AI_API_STYLE": "",
        "AI_TEMPERATURE": 1,
        "DEFAULT_CHIP": "",
        "DEFAULT_CLOCK": "HSI_internal",
        "CLI_LANGUAGE": "zh",
        "SERIAL_PORT": "",
        "SERIAL_BAUD": 115200,
        "POST_FLASH_DELAY": 1.5,
        "REGISTER_READ_DELAY": 0.3,
    }
    for name in _CONFIG_KEYS_TO_RELOAD:
        globals()[name] = getattr(_cfg, name, defaults[name])
    AI_API_STYLE = _normalize_api_style(AI_API_STYLE, default="") or ""
    CLI_LANGUAGE = _normalize_cli_language(CLI_LANGUAGE)
    if (AI_API_KEY, AI_BASE_URL, AI_MODEL, AI_API_STYLE) != previous_signature:
        _AI_CLIENT = None
        _AI_CLIENT_SIGNATURE = None
    return _current_settings()


def reload_ai_config() -> dict[str, Any]:
    """Public wrapper for reloading AI/runtime settings."""

    return _reload_ai_globals()


def _mask_key(key: str) -> str:
    """Mask a secret for CLI display."""

    if not key:
        return "(未设置)"
    return key[:6] + "..." + key[-4:] if len(key) > 12 else "***"


def _api_key_is_placeholder(api_key: str) -> bool:
    """Return whether the API key is empty or still using a template value."""

    key = (api_key or "").strip()
    if not key:
        return True
    placeholder_prefixes = ("YOUR_API_KEY", "sk-YOUR")
    return any(key.startswith(prefix) for prefix in placeholder_prefixes)


def _ai_is_configured() -> bool:
    """Return whether the runtime has a usable AI configuration."""

    api_key, base_url, model, _ = _read_ai_config()
    return bool(api_key and base_url and model and not _api_key_is_placeholder(api_key))


def _extract_api_version_from_url(base_url: str) -> str | None:
    """Extract Gemini API version from a configured URL when present."""

    path = urlparse(base_url or "").path.strip("/")
    if not path:
        return None
    for segment in path.split("/"):
        if re.fullmatch(r"v\d+(?:alpha|beta)?\d*", segment):
            return segment
    return None


def _is_gemini_provider(base_url: str | None = None, model: str | None = None) -> bool:
    """Return whether the current config should use the official Gemini SDK."""

    target_url = (base_url or AI_BASE_URL or "").strip().lower()
    parsed = urlparse(target_url)
    host = parsed.netloc.lower()
    if host == "generativelanguage.googleapis.com" or host.endswith(
        ".generativelanguage.googleapis.com"
    ):
        return True
    return target_url in {"gemini", "gemini://official", "google-gemini"}


def _resolve_api_style(
    *,
    base_url: str | None = None,
    model: str | None = None,
    api_style: str | None = None,
) -> str:
    """Resolve the effective runtime API style with backward-compatible inference."""

    explicit = _normalize_api_style(api_style if api_style is not None else AI_API_STYLE)
    if explicit:
        return explicit
    if _is_gemini_provider(base_url=base_url, model=model):
        return "gemini"
    return "openai"


def _provider_kind(
    base_url: str | None = None,
    model: str | None = None,
    api_style: str | None = None,
) -> str:
    """Return the active provider kind."""

    return _resolve_api_style(base_url=base_url, model=model, api_style=api_style)


def provider_name(
    base_url: str | None = None,
    model: str | None = None,
    api_style: str | None = None,
) -> str:
    """Return a human-readable provider label."""

    kind = _provider_kind(base_url, model, api_style)
    if kind == "gemini":
        return "Google Gemini (official SDK)"
    if kind == "anthropic":
        return "Anthropic Messages API"
    return "OpenAI-compatible"


def _build_gemini_http_options(timeout: float) -> dict[str, Any]:
    """Build HTTP options for the Gemini SDK from current runtime config."""

    http_options: dict[str, Any] = {"timeout": int(max(timeout, 1.0) * 1000)}
    if _provider_kind(AI_BASE_URL, AI_MODEL, AI_API_STYLE) == "gemini":
        parsed = urlparse(AI_BASE_URL)
        if parsed.scheme and parsed.netloc:
            http_options["base_url"] = f"{parsed.scheme}://{parsed.netloc}/"
        api_version = _extract_api_version_from_url(AI_BASE_URL)
        if api_version:
            http_options["api_version"] = api_version
    return http_options


def _encode_thought_signature(value: Any) -> str:
    """Serialize Gemini thought signatures for message history."""

    if value is None:
        return ""
    if isinstance(value, bytes):
        return base64.b64encode(value).decode("ascii")
    if isinstance(value, str):
        return value
    return ""


def _decode_thought_signature(value: Any) -> bytes | None:
    """Decode a persisted Gemini thought signature back to bytes."""

    if not value:
        return None
    if isinstance(value, bytes):
        return value
    if not isinstance(value, str):
        return None
    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except Exception:
        return value.encode("utf-8")


def get_ai_client(timeout: float = 180.0, force_reload: bool = False) -> Any | None:
    """Return a lazily-created client for the current provider config."""

    global _AI_CLIENT
    global _AI_CLIENT_SIGNATURE

    kind = _provider_kind(AI_BASE_URL, AI_MODEL, AI_API_STYLE)
    signature = (kind, AI_API_KEY, AI_BASE_URL, f"{AI_MODEL}|{AI_API_STYLE}", float(timeout))
    if force_reload:
        _AI_CLIENT = None
        _AI_CLIENT_SIGNATURE = None
    if _AI_CLIENT is not None and _AI_CLIENT_SIGNATURE == signature:
        return _AI_CLIENT

    if kind == "gemini":
        genai, _ = _load_gemini_sdk()
        if genai is None:
            return None
        kwargs: dict[str, Any] = {"api_key": AI_API_KEY}
        http_options = _build_gemini_http_options(timeout)
        if http_options:
            kwargs["http_options"] = http_options
        _AI_CLIENT = genai.Client(**kwargs)
        _AI_CLIENT_SIGNATURE = signature
        return _AI_CLIENT

    if kind == "anthropic":
        _AI_CLIENT = {
            "provider": "anthropic",
            "base_url": AI_BASE_URL,
            "model": AI_MODEL,
            "api_style": AI_API_STYLE,
        }
        _AI_CLIENT_SIGNATURE = signature
        return _AI_CLIENT

    openai_class = _load_openai_class()
    if openai_class is None:
        return None
    _AI_CLIENT = openai_class(api_key=AI_API_KEY, base_url=AI_BASE_URL, timeout=timeout)
    _AI_CLIENT_SIGNATURE = signature
    return _AI_CLIENT


def probe_ai_connection(client: Any | None = None, timeout: float = 8.0) -> None:
    """Perform a minimal provider-specific connectivity probe."""

    kind = _provider_kind(AI_BASE_URL, AI_MODEL, AI_API_STYLE)
    active_client = client or get_ai_client(timeout=timeout)
    if active_client is None and kind != "anthropic":
        if kind == "gemini":
            raise RuntimeError("google-genai 未安装: pip install google-genai")
        raise RuntimeError("openai 未安装: pip install openai")

    if kind == "gemini":
        pager = active_client.models.list(config={"page_size": 1})
        next(iter(pager), None)
        return

    if kind == "anthropic":
        base = (AI_BASE_URL or "https://api.anthropic.com/v1").rstrip("/")
        if base.endswith("/messages"):
            base = base[: -len("/messages")]
        if base.endswith("/models"):
            base = base[: -len("/models")]
        headers = {
            "x-api-key": AI_API_KEY,
            "anthropic-version": "2023-06-01",
        }
        response = requests.get(f"{base}/models?limit=1", headers=headers, timeout=timeout)
        if response.status_code >= 400:
            try:
                payload = response.json()
                message = (payload.get("error") or {}).get("message") or response.text
            except Exception:
                message = response.text
            raise RuntimeError(
                f"Anthropic probe failed: HTTP {response.status_code}: {message[:200]}"
            )
        return

    active_client.models.list()


def _assistant_message_to_anthropic_blocks(message: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert an assistant history message into Anthropic content blocks."""

    blocks: list[dict[str, Any]] = []
    for block in message.get("anthropic_thinking_blocks") or []:
        if isinstance(block, dict):
            blocks.append(copy.deepcopy(block))
    content = str(message.get("content") or "")
    if content:
        blocks.append({"type": "text", "text": content})

    for tool_call in message.get("tool_calls") or []:
        func = tool_call.get("function") or {}
        args_text = str(func.get("arguments") or "").strip()
        try:
            tool_input = json.loads(args_text) if args_text else {}
        except Exception:
            tool_input = {"raw_arguments": args_text}
        blocks.append(
            {
                "type": "tool_use",
                "id": tool_call.get("id") or func.get("name") or "tool_use",
                "name": func.get("name") or "",
                "input": tool_input if isinstance(tool_input, dict) else {"input": tool_input},
            }
        )
    return blocks


def _tool_message_to_anthropic_result_block(message: dict[str, Any]) -> dict[str, Any]:
    """Convert one tool response message into an Anthropic `tool_result` block."""

    payload = _coerce_tool_payload(message.get("content"))
    if isinstance(payload, (dict, list)):
        content = json.dumps(payload, ensure_ascii=False)
    else:
        content = str(payload)
    result = {
        "type": "tool_result",
        "tool_use_id": message.get("tool_call_id") or "",
        "content": content,
    }
    if isinstance(payload, dict) and payload.get("success") is False:
        result["is_error"] = True
    return result


def _messages_to_anthropic_payload(
    messages: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """Convert Gary's OpenAI-style history into Anthropic `system` + `messages`."""

    system_parts: list[str] = []
    converted: list[dict[str, Any]] = []
    idx = 0

    while idx < len(messages):
        message = messages[idx]
        role = str(message.get("role") or "").strip().lower()
        if role in {"system", "developer"}:
            text = str(message.get("content") or "").strip()
            if text:
                system_parts.append(text)
            idx += 1
            continue

        if role == "assistant":
            blocks = _assistant_message_to_anthropic_blocks(message)
            if blocks:
                converted.append({"role": "assistant", "content": blocks})
            idx += 1
            continue

        if role == "tool":
            blocks: list[dict[str, Any]] = []
            while (
                idx < len(messages)
                and str(messages[idx].get("role") or "").strip().lower() == "tool"
            ):
                blocks.append(_tool_message_to_anthropic_result_block(messages[idx]))
                idx += 1
            if blocks:
                converted.append({"role": "user", "content": blocks})
            continue

        text = str(message.get("content") or "")
        if text:
            converted.append({"role": "user", "content": [{"type": "text", "text": text}]})
        idx += 1

    return "\n\n".join(system_parts).strip(), converted


def _openai_tools_to_anthropic_tools(tools: Optional[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Convert OpenAI function schemas into Anthropic tool definitions."""

    if not tools:
        return []

    converted: list[dict[str, Any]] = []
    for tool in tools:
        if tool.get("type") != "function":
            continue
        func = tool.get("function") or {}
        converted.append(
            {
                "name": func.get("name") or "",
                "description": func.get("description") or "",
                "input_schema": func.get("parameters")
                or {"type": "object", "properties": {}, "required": []},
            }
        )
    return converted


def _normalize_anthropic_response(data: dict[str, Any]) -> _NormalizedChunk:
    """Project one Anthropic Messages response into an OpenAI-like delta shape."""

    content_parts: list[str] = []
    reasoning_parts: list[str] = []
    tool_calls: list[_NormalizedToolCallDelta] = []
    raw_tool_calls: list[dict[str, Any]] = []
    thinking_blocks: list[dict[str, Any]] = []

    for index, block in enumerate(data.get("content") or []):
        block_type = block.get("type")
        if block_type == "thinking":
            thinking_text = str(block.get("thinking") or "")
            signature = str(block.get("signature") or "")
            reasoning_parts.append(thinking_text)
            thinking_block = {"type": "thinking", "thinking": thinking_text}
            if signature:
                thinking_block["signature"] = signature
            thinking_blocks.append(thinking_block)
            continue
        if block_type == "text":
            text = str(block.get("text") or "")
            if text:
                content_parts.append(text)
            continue
        if block_type != "tool_use":
            continue
        arguments = json.dumps(block.get("input") or {}, ensure_ascii=False)
        func = _NormalizedFunctionDelta(
            name=block.get("name") or "",
            arguments=arguments,
        )
        tool_call = _NormalizedToolCallDelta(
            index=index,
            id=block.get("id") or f"anthropic-tool-{index}",
            function=func,
        )
        tool_calls.append(tool_call)
        raw_tool_calls.append(
            {
                "id": tool_call.id,
                "function": {
                    "name": func.name,
                    "arguments": func.arguments,
                },
            }
        )

    delta = _NormalizedDelta(
        content="".join(content_parts) or None,
        reasoning_content="".join(reasoning_parts) or None,
        tool_calls=tool_calls or None,
    )
    return _NormalizedChunk(
        choices=[_NormalizedChoice(delta=delta)],
        _raw_tool_calls=raw_tool_calls,
        anthropic_thinking_blocks=thinking_blocks or None,
    )


def _anthropic_request_headers(api_key: str) -> dict[str, str]:
    """Build the standard Anthropic request headers."""

    return {
        "content-type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }


def _anthropic_messages_endpoint(base_url: str) -> str:
    """Return the Anthropic Messages endpoint for the configured base URL."""

    normalized = (base_url or "https://api.anthropic.com/v1").rstrip("/")
    if normalized.endswith("/messages"):
        return normalized
    return f"{normalized}/messages"


def _anthropic_error_message(response: requests.Response) -> str:
    """Extract a readable Anthropic error message from a failed response."""

    try:
        data = response.json()
        return str((data.get("error") or {}).get("message") or response.text or "")
    except Exception:
        return str(response.text or "")


def _anthropic_should_retry_without_thinking(response: requests.Response) -> bool:
    """Return whether a failed request should transparently retry without thinking."""

    message = _anthropic_error_message(response).lower()
    if response.status_code not in {400, 404, 422}:
        return False
    thinking_markers = (
        "thinking",
        "budget_tokens",
        "extended thinking",
        "not supported",
        "unsupported",
    )
    return any(marker in message for marker in thinking_markers)


def _anthropic_tool_choice_payload(tool_choice: str | dict[str, Any]) -> dict[str, Any] | None:
    """Translate OpenAI-style tool choice into Anthropic format."""

    if tool_choice == "none":
        return {"type": "none"}
    if tool_choice == "required":
        return {"type": "any"}
    if isinstance(tool_choice, dict):
        func = tool_choice.get("function") or {}
        name = func.get("name")
        if name:
            return {"type": "tool", "name": name}
    return None


def _iter_sse_events(response: requests.Response) -> Iterator[tuple[str, str]]:
    """Yield `(event, data)` pairs from a server-sent events response."""

    event_name = "message"
    data_lines: list[str] = []
    for raw_line in response.iter_lines(decode_unicode=True):
        line = raw_line if isinstance(raw_line, str) else raw_line.decode("utf-8", errors="replace")
        if line == "":
            if data_lines:
                yield event_name, "\n".join(data_lines)
            event_name = "message"
            data_lines = []
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event_name = line.split(":", 1)[1].strip() or "message"
            continue
        if line.startswith("data:"):
            data_lines.append(line.split(":", 1)[1].lstrip())
    if data_lines:
        yield event_name, "\n".join(data_lines)


def _anthropic_chunk_from_delta(
    *,
    content: str | None = None,
    reasoning_content: str | None = None,
    tool_call: _NormalizedToolCallDelta | None = None,
    thinking_blocks: list[dict[str, Any]] | None = None,
) -> _NormalizedChunk:
    """Create one normalized chunk from Anthropic delta fragments."""

    delta = _NormalizedDelta(
        content=content,
        reasoning_content=reasoning_content,
        tool_calls=[tool_call] if tool_call is not None else None,
    )
    raw_tool_calls: list[dict[str, Any]] = []
    if tool_call is not None:
        raw = {
            "id": tool_call.id,
            "function": {
                "name": tool_call.function.name,
                "arguments": tool_call.function.arguments,
            },
        }
        raw_tool_calls.append(raw)
    return _NormalizedChunk(
        choices=[_NormalizedChoice(delta=delta)],
        _raw_tool_calls=raw_tool_calls,
        anthropic_thinking_blocks=thinking_blocks or None,
    )


def _stream_chat_anthropic(
    *,
    messages: list[dict[str, Any]],
    tools: Optional[list[dict[str, Any]]] = None,
    tool_choice: str | dict[str, Any] = "auto",
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    client: Any | None = None,
    timeout: float = 180.0,
) -> Iterator[_NormalizedChunk]:
    """Call an Anthropic-style `/v1/messages` endpoint with SSE streaming."""

    del client
    system_prompt, anthropic_messages = _messages_to_anthropic_payload(messages)
    target_model = model or AI_MODEL
    converted_tools = _openai_tools_to_anthropic_tools(tools)

    def _build_payload(enable_thinking: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": target_model,
            "max_tokens": 8192,
            "messages": anthropic_messages,
            "stream": True,
        }
        if system_prompt:
            payload["system"] = system_prompt
        if enable_thinking:
            payload["thinking"] = {"type": "enabled", "budget_tokens": 2048}
        else:
            payload["temperature"] = min(
                1.0,
                max(0.0, AI_TEMPERATURE if temperature is None else temperature),
            )
        if converted_tools:
            payload["tools"] = converted_tools
            tool_choice_payload = _anthropic_tool_choice_payload(tool_choice)
            if tool_choice_payload is not None:
                payload["tool_choice"] = tool_choice_payload
        return payload

    response = requests.post(
        _anthropic_messages_endpoint(AI_BASE_URL),
        headers=_anthropic_request_headers(AI_API_KEY),
        json=_build_payload(True),
        timeout=timeout,
        stream=True,
    )
    if response.status_code >= 400 and _anthropic_should_retry_without_thinking(response):
        response.close()
        response = requests.post(
            _anthropic_messages_endpoint(AI_BASE_URL),
            headers=_anthropic_request_headers(AI_API_KEY),
            json=_build_payload(False),
            timeout=timeout,
            stream=True,
        )
    if response.status_code >= 400:
        message = _anthropic_error_message(response)
        raise RuntimeError(f"Anthropic API error {response.status_code}: {message[:400]}")
    block_state: dict[int, dict[str, Any]] = {}
    final_thinking_blocks: list[dict[str, Any]] = []
    try:
        for event_name, data_text in _iter_sse_events(response):
            if not data_text or data_text == "[DONE]":
                continue
            try:
                event = json.loads(data_text)
            except Exception:
                continue

            event_type = event.get("type") or event_name
            if event_type == "error":
                err_payload = event.get("error") or {}
                raise RuntimeError(
                    f"Anthropic streaming error: {err_payload.get('message') or data_text}"
                )

            if event_type == "content_block_start":
                index = int(event.get("index", 0))
                block = event.get("content_block") or {}
                block_type = block.get("type")
                if block_type == "tool_use":
                    block_state[index] = {
                        "type": "tool_use",
                        "id": block.get("id") or f"anthropic-tool-{index}",
                        "name": block.get("name") or "",
                        "input_json": "",
                    }
                    yield _anthropic_chunk_from_delta(
                        tool_call=_NormalizedToolCallDelta(
                            index=index,
                            id=block_state[index]["id"],
                            function=_NormalizedFunctionDelta(
                                name=block_state[index]["name"],
                                arguments="",
                            ),
                        )
                    )
                    continue
                if block_type == "thinking":
                    block_state[index] = {
                        "type": "thinking",
                        "thinking": str(block.get("thinking") or ""),
                        "signature": str(block.get("signature") or ""),
                    }
                    if block_state[index]["thinking"]:
                        yield _anthropic_chunk_from_delta(
                            reasoning_content=block_state[index]["thinking"]
                        )
                    continue
                if block_type == "text":
                    block_state[index] = {"type": "text"}
                    text = str(block.get("text") or "")
                    if text:
                        yield _anthropic_chunk_from_delta(content=text)
                    continue
                block_state[index] = {"type": block_type or "unknown"}
                continue

            if event_type == "content_block_delta":
                index = int(event.get("index", 0))
                delta = event.get("delta") or {}
                delta_type = delta.get("type")
                current = block_state.setdefault(index, {"type": "unknown"})
                if delta_type == "text_delta":
                    text = str(delta.get("text") or "")
                    if text:
                        yield _anthropic_chunk_from_delta(content=text)
                    continue
                if delta_type == "thinking_delta":
                    text = str(delta.get("thinking") or "")
                    current["thinking"] = str(current.get("thinking") or "") + text
                    if text:
                        yield _anthropic_chunk_from_delta(reasoning_content=text)
                    continue
                if delta_type == "signature_delta":
                    current["signature"] = str(current.get("signature") or "") + str(
                        delta.get("signature") or ""
                    )
                    continue
                if delta_type == "input_json_delta":
                    partial = str(delta.get("partial_json") or "")
                    current["input_json"] = str(current.get("input_json") or "") + partial
                    yield _anthropic_chunk_from_delta(
                        tool_call=_NormalizedToolCallDelta(
                            index=index,
                            id=current.get("id") or f"anthropic-tool-{index}",
                            function=_NormalizedFunctionDelta(
                                name=current.get("name") or "",
                                arguments=partial,
                            ),
                        )
                    )
                    continue
                continue

            if event_type == "content_block_stop":
                index = int(event.get("index", 0))
                current = block_state.get(index) or {}
                if current.get("type") == "thinking":
                    block = {
                        "type": "thinking",
                        "thinking": str(current.get("thinking") or ""),
                    }
                    if current.get("signature"):
                        block["signature"] = str(current.get("signature") or "")
                    final_thinking_blocks.append(block)
                continue

            if event_type == "message_stop":
                if final_thinking_blocks:
                    yield _anthropic_chunk_from_delta(thinking_blocks=final_thinking_blocks)
                break
    finally:
        response.close()


def _coerce_tool_payload(raw_content: Any) -> dict[str, Any]:
    """Convert a tool message body into Gemini function-response JSON."""

    if isinstance(raw_content, dict):
        return raw_content
    if isinstance(raw_content, list):
        return {"output": raw_content}
    text = str(raw_content or "").strip()
    if not text:
        return {"output": ""}
    try:
        parsed = json.loads(text)
    except Exception:
        return {"output": text}
    if isinstance(parsed, dict):
        return parsed
    return {"output": parsed}


def _assistant_message_to_gemini_parts(message: dict[str, Any], types_mod: Any) -> list[Any]:
    """Convert an assistant history message into Gemini parts."""

    parts: list[Any] = []
    reasoning = str(message.get("reasoning_content") or "")
    if reasoning:
        parts.append(types_mod.Part(text=reasoning, thought=True))

    content = str(message.get("content") or "")
    if content:
        parts.append(types_mod.Part.from_text(text=content))

    for tool_call in message.get("tool_calls") or []:
        func = tool_call.get("function") or {}
        args_text = str(func.get("arguments") or "").strip()
        try:
            args = json.loads(args_text) if args_text else {}
        except Exception:
            args = {"raw_arguments": args_text}
        part = types_mod.Part(
            function_call=types_mod.FunctionCall(
                id=tool_call.get("id") or None,
                name=func.get("name") or None,
                args=args,
            ),
            thought_signature=_decode_thought_signature(func.get("thought_signature")),
        )
        parts.append(part)
    return parts


def _tool_message_to_gemini_parts(message: dict[str, Any], types_mod: Any) -> list[Any]:
    """Convert a tool response history message into Gemini parts."""

    name = str(message.get("name") or "").strip()
    response = types_mod.FunctionResponse(
        id=message.get("tool_call_id") or None,
        name=name or None,
        response=_coerce_tool_payload(message.get("content")),
    )
    return [types_mod.Part(function_response=response)]


def _messages_to_gemini_payload(
    messages: list[dict[str, Any]], types_mod: Any
) -> tuple[str, list[Any]]:
    """Convert Gary's OpenAI-style history into Gemini `contents` + `system_instruction`."""

    system_parts: list[str] = []
    contents: list[Any] = []

    for message in messages:
        role = str(message.get("role") or "").strip().lower()
        if role == "system":
            text = str(message.get("content") or "").strip()
            if text:
                system_parts.append(text)
            continue

        if role == "assistant":
            parts = _assistant_message_to_gemini_parts(message, types_mod)
            target_role = "model"
        elif role == "tool":
            parts = _tool_message_to_gemini_parts(message, types_mod)
            target_role = "user"
        else:
            text = str(message.get("content") or "")
            parts = [types_mod.Part.from_text(text=text)] if text else []
            target_role = "user"

        if parts:
            contents.append(types_mod.Content(role=target_role, parts=parts))

    return "\n\n".join(system_parts).strip(), contents


def _openai_tools_to_gemini_tools(
    tools: Optional[list[dict[str, Any]]], types_mod: Any
) -> list[Any]:
    """Convert OpenAI function schemas into Gemini function declarations."""

    if not tools:
        return []

    declarations = []
    for tool in tools:
        if tool.get("type") != "function":
            continue
        func = tool.get("function") or {}
        declarations.append(
            types_mod.FunctionDeclaration(
                name=func.get("name") or "",
                description=func.get("description") or "",
                parameters_json_schema=func.get("parameters")
                or {"type": "object", "properties": {}, "required": []},
            )
        )

    if not declarations:
        return []
    return [types_mod.Tool(function_declarations=declarations)]


def _normalize_gemini_chunk(chunk: Any) -> _NormalizedChunk:
    """Project a Gemini SDK response chunk into an OpenAI-like delta shape."""

    try:
        parts = chunk.parts or []
    except Exception:
        try:
            parts = (chunk.candidates or [])[0].content.parts or []
        except Exception:
            parts = []

    text_parts: list[str] = []
    reasoning_parts: list[str] = []
    tool_calls: list[_NormalizedToolCallDelta] = []
    raw_tool_calls: list[dict[str, Any]] = []

    for index, part in enumerate(parts):
        function_call = getattr(part, "function_call", None)
        if function_call is not None:
            args_text = json.dumps(function_call.args or {}, ensure_ascii=False)
            thought_signature = _encode_thought_signature(getattr(part, "thought_signature", None))
            func = _NormalizedFunctionDelta(
                name=function_call.name or "",
                arguments=args_text,
                thought_signature=thought_signature or None,
            )
            tool_call = _NormalizedToolCallDelta(
                index=index,
                id=function_call.id or f"gemini-call-{index}",
                function=func,
                thought_signature=thought_signature or None,
            )
            tool_calls.append(tool_call)
            raw = {
                "id": tool_call.id,
                "function": {
                    "name": func.name,
                    "arguments": func.arguments,
                },
            }
            if thought_signature:
                raw["function"]["thought_signature"] = thought_signature
            raw_tool_calls.append(raw)
            continue

        text = getattr(part, "text", None)
        if not text:
            continue
        if getattr(part, "thought", False):
            reasoning_parts.append(text)
        else:
            text_parts.append(text)

    delta = _NormalizedDelta(
        content="".join(text_parts) or None,
        reasoning_content="".join(reasoning_parts) or None,
        tool_calls=tool_calls or None,
    )
    return _NormalizedChunk(
        choices=[_NormalizedChoice(delta=delta)], _raw_tool_calls=raw_tool_calls
    )


def _stream_chat_gemini(
    *,
    messages: list[dict[str, Any]],
    tools: Optional[list[dict[str, Any]]] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    client: Any | None = None,
    timeout: float = 180.0,
) -> Iterator[_NormalizedChunk]:
    """Create a Gemini official SDK streaming request and normalize its chunks."""

    _, types_mod = _load_gemini_sdk()
    active_client = client or get_ai_client(timeout=timeout)
    if active_client is None or types_mod is None:
        raise RuntimeError("google-genai 未安装: pip install google-genai")

    system_instruction, contents = _messages_to_gemini_payload(messages, types_mod)
    config = types_mod.GenerateContentConfig(
        system_instruction=system_instruction or None,
        temperature=AI_TEMPERATURE if temperature is None else temperature,
        tools=_openai_tools_to_gemini_tools(tools, types_mod) or None,
        automatic_function_calling=types_mod.AutomaticFunctionCallingConfig(disable=True),
        thinking_config=types_mod.ThinkingConfig(include_thoughts=True),
    )

    stream = active_client.models.generate_content_stream(
        model=model or AI_MODEL,
        contents=contents,
        config=config,
    )
    for chunk in stream:
        yield _normalize_gemini_chunk(chunk)


def stream_chat(
    *,
    messages: list[dict[str, Any]],
    tools: Optional[list[dict[str, Any]]] = None,
    tool_choice: str | dict[str, Any] = "auto",
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    client: Any | None = None,
    timeout: float = 180.0,
) -> Any:
    """Create a streaming chat request using the active provider runtime config."""

    kind = _provider_kind(AI_BASE_URL, AI_MODEL, AI_API_STYLE)
    if kind == "gemini":
        return _stream_chat_gemini(
            messages=messages,
            tools=tools,
            model=model,
            temperature=temperature,
            client=client,
            timeout=timeout,
        )
    if kind == "anthropic":
        return _stream_chat_anthropic(
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
            model=model,
            temperature=temperature,
            client=client,
            timeout=timeout,
        )

    active_client = client or get_ai_client(timeout=timeout)
    if active_client is None:
        raise RuntimeError("openai 未安装: pip install openai")
    request: dict[str, Any] = {
        "model": model or AI_MODEL,
        "messages": messages,
        "temperature": AI_TEMPERATURE if temperature is None else temperature,
        "stream": True,
    }
    if tools is not None:
        request["tools"] = tools
        request["tool_choice"] = tool_choice
    return active_client.chat.completions.create(**request)


__all__ = [
    "AI_API_KEY",
    "AI_BASE_URL",
    "AI_MODEL",
    "AI_API_STYLE",
    "AI_TEMPERATURE",
    "_API_STYLE_OPTIONS",
    "CLI_LANGUAGE",
    "DEFAULT_CHIP",
    "DEFAULT_CLOCK",
    "POST_FLASH_DELAY",
    "REGISTER_READ_DELAY",
    "SERIAL_BAUD",
    "SERIAL_PORT",
    "_AI_PRESETS",
    "_ai_is_configured",
    "_api_key_is_placeholder",
    "_is_gemini_provider",
    "_mask_key",
    "_normalize_api_style",
    "_provider_kind",
    "_resolve_api_style",
    "_read_ai_config",
    "_reload_ai_globals",
    "_write_ai_config",
    "_write_cli_language_config",
    "get_ai_client",
    "probe_ai_connection",
    "provider_name",
    "reload_ai_config",
    "stream_chat",
]

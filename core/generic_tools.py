"""Generic file, shell, and git tools used by Gary."""

from __future__ import annotations

import ast
import json
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import requests

from tui.ui import console as CONSOLE


def read_file(file_path: str) -> dict:
    try:
        path = Path(file_path).expanduser().resolve()
        if not path.exists():
            return {"error": f"文件不存在: {file_path}"}
        content = path.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()
        numbered = "\n".join(f"{index + 1:4d} | {line}" for index, line in enumerate(lines[:800]))
        return {
            "success": True,
            "numbered_view": numbered,
            "raw_content": content[:40000],
            "total_lines": len(lines),
        }
    except Exception as exc:
        return {"error": str(exc)}


def create_or_overwrite_file(file_path: str, content: str) -> dict:
    try:
        path = Path(file_path).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return {"success": True, "path": str(path), "lines": len(content.splitlines())}
    except Exception as exc:
        return {"error": str(exc)}


def str_replace_edit(file_path: str, old_str: str, new_str: str) -> dict:
    try:
        path = Path(file_path).expanduser().resolve()
        if not path.exists():
            note = ""
            path_text = str(path)
            if "latest_workspace" in path_text:
                sibling_main_py = path.parent / "main.py"
                sibling_main_c = path.parent / "main.c"
                if sibling_main_py.exists() or sibling_main_c.exists():
                    sibling = sibling_main_py if sibling_main_py.exists() else sibling_main_c
                    note = (
                        f"；当前 latest_workspace 中存在 {sibling.name}，"
                        "请确认目标平台和文件路径是否匹配"
                    )
                else:
                    note = (
                        "；latest_workspace 还没有缓存源码。"
                        "请先生成完整代码并调用对应的 compile / auto_sync_cycle，"
                        "或先读取历史项目，再进行 str_replace_edit"
                    )
            return {"error": f"文件不存在: {file_path}{note}"}
        content = path.read_text(encoding="utf-8", errors="ignore")
        count = content.count(old_str)
        if count == 0:
            return {"error": "未找到 old_str，请检查空格/换行是否完全一致"}
        if count > 1:
            return {"error": f"找到 {count} 个匹配，请增加上下文使其唯一"}
        path.write_text(content.replace(old_str, new_str, 1), encoding="utf-8")
        return {"success": True, "message": "替换成功", "path": str(path)}
    except Exception as exc:
        return {"error": str(exc)}


def list_directory(path: str = ".") -> dict:
    try:
        target = Path(path).expanduser().resolve()
        items = [
            {"name": item.name, "type": "dir" if item.is_dir() else "file"}
            for item in target.iterdir()
        ]
        return {
            "success": True,
            "path": str(target),
            "items": sorted(items, key=lambda item: (item["type"], item["name"])),
        }
    except Exception as exc:
        return {"error": str(exc)}


def execute_command(command: str) -> dict:
    if any(fragment in command for fragment in ["rm -rf /", ":(){ :|:& };:"]):
        return {"error": "命令被安全策略拒绝"}
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=60)
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout[:3000],
            "stderr": result.stderr[:1000],
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"error": "命令超时（60s）"}
    except Exception as exc:
        return {"error": str(exc)}


def search_files(query: str, path: str = ".", file_type: str = None) -> dict:
    try:
        results = []
        for file_path in Path(path).expanduser().resolve().rglob("*"):
            if not file_path.is_file():
                continue
            if query.lower() not in file_path.name.lower():
                continue
            if file_type and file_path.suffix != file_type:
                continue
            results.append(str(file_path))
            if len(results) >= 20:
                break
        return {"success": True, "files": results}
    except Exception as exc:
        return {"error": str(exc)}


def _browser_headers() -> dict[str, str]:
    return {"User-Agent": "Mozilla/5.0 (compatible; GaryCLI/1.0)"}


_DEFAULT_SEARXNG_URL = "http://127.0.0.1:8080"


def _searxng_base_url() -> str:
    value = (os.environ.get("GARY_SEARXNG_URL") or _DEFAULT_SEARXNG_URL).strip()
    if not value:
        value = _DEFAULT_SEARXNG_URL
    return value.rstrip("/")


def _load_bs4():
    try:
        from bs4 import BeautifulSoup  # type: ignore
    except ImportError:
        return None, {"error": "beautifulsoup4 未安装: pip install beautifulsoup4"}
    return BeautifulSoup, None


def _clean_browser_text(raw_text: str) -> str:
    lines = (line.strip() for line in raw_text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    return "\n".join(chunk for chunk in chunks if chunk)


def _clean_browser_snippet(raw_text: str, max_chars: int = 200) -> str:
    text = " ".join(_clean_browser_text(raw_text).split())
    return text[:max_chars]


def _extract_browser_links(soup, base_url: str, limit: int = 40) -> list[dict]:
    links = []
    seen: set[tuple[str, str]] = set()
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "").strip()
        text = " ".join(anchor.get_text(" ", strip=True).split())
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        absolute = urljoin(base_url, href)
        key = (absolute, text)
        if key in seen:
            continue
        seen.add(key)
        links.append(
            {
                "id": len(links) + 1,
                "text": text or absolute,
                "url": absolute,
            }
        )
        if len(links) >= limit:
            break
    return links


def _parse_browser_page(url: str) -> tuple[dict | None, dict | None]:
    BeautifulSoup, error = _load_bs4()
    if error is not None:
        return None, error
    try:
        response = requests.get(url, headers=_browser_headers(), timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        title = ""
        if soup.title and soup.title.string:
            title = soup.title.string.strip()

        main_root = soup.find("main") or soup.find("article") or soup.body or soup
        text = _clean_browser_text(main_root.get_text("\n"))
        final_url = str(response.url or url)
        links = _extract_browser_links(soup, final_url)
        page = {
            "success": True,
            "url": url,
            "final_url": final_url,
            "title": title,
            "status_code": response.status_code,
            "content": text,
            "links": links,
        }
        return page, None
    except Exception as exc:
        return None, {"error": f"获取失败: {exc}"}


def _search_via_searx_html(base_url: str, query: str, limit: int) -> dict:
    BeautifulSoup, error = _load_bs4()
    if error is not None:
        return error
    try:
        response = requests.get(
            f"{base_url}/search",
            params={"q": query},
            headers=_browser_headers(),
            timeout=12,
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")
        results = []
        for article in soup.select("article.result"):
            anchor = article.select_one("a[href]")
            if anchor is None:
                continue
            href = str(anchor.get("href") or "").strip()
            title = " ".join(anchor.get_text(" ", strip=True).split()) or href
            snippet_node = (
                article.select_one(".content")
                or article.select_one("p")
                or article.select_one(".detail")
            )
            snippet = ""
            if snippet_node is not None:
                snippet = _clean_browser_snippet(snippet_node.get_text(" ", strip=True))
            results.append(
                {
                    "id": len(results) + 1,
                    "title": title,
                    "url": urljoin(base_url + "/", href),
                    "snippet": snippet,
                }
            )
            if len(results) >= max(0, limit):
                break
        return {
            "success": True,
            "query": query,
            "backend": "searxng_html",
            "base_url": base_url,
            "results": results,
            "count": len(results),
        }
    except Exception as exc:
        return {
            "error": (
                f"搜索失败：无法使用本地 SearXNG（{base_url}）。"
                "请确认实例已启动且搜索页可访问。"
                f" 原始错误: {exc}"
            )
        }


def _search_via_searx(query: str, limit: int = 5) -> dict:
    base_url = _searxng_base_url()
    try:
        response = requests.get(
            f"{base_url}/search",
            params={"q": query, "format": "json"},
            headers=_browser_headers(),
            timeout=8,
        )
        response.raise_for_status()
        data = response.json()
        results = [
            {
                "id": index + 1,
                "title": item.get("title"),
                "url": item.get("url"),
                "snippet": item.get("content", "")[:200],
            }
            for index, item in enumerate(data.get("results", [])[: max(0, limit)])
        ]
        return {
            "success": True,
            "query": query,
            "backend": "searxng",
            "base_url": base_url,
            "results": results,
            "count": len(results),
        }
    except Exception as exc:
        fallback = _search_via_searx_html(base_url, query, limit)
        if fallback.get("success"):
            fallback["warning"] = f"SearXNG JSON 接口不可用，已回退到 HTML 解析。原始错误: {exc}"
            return fallback
        return {
            "error": (
                f"搜索失败：无法连接本地 SearXNG（{base_url}）。"
                "请先启动本地实例，或运行 `python setup.py --searxng`"
                " / `python setup.py --searxng-native` 完成一键安装。"
                f" 原始错误: {exc}"
            )
        }


def web_search(query: str) -> dict:
    return _search_via_searx(query, limit=5)


def browser_search(query: str, limit: int = 5) -> dict:
    try:
        safe_limit = max(1, min(int(limit), 10))
    except Exception:
        safe_limit = 5
    return _search_via_searx(query, limit=safe_limit)


def browser_open(url: str, max_chars: int = 8000) -> dict:
    page, error = _parse_browser_page(url)
    if error is not None:
        return error
    assert page is not None
    text = str(page.get("content") or "")
    try:
        safe_max_chars = max(500, min(int(max_chars), 40000))
    except Exception:
        safe_max_chars = 8000
    page["content"] = text[:safe_max_chars]
    page["truncated"] = len(text) > safe_max_chars
    page["content_chars"] = len(text)
    page["link_count"] = len(page.get("links") or [])
    return page


def browser_extract_links(url: str) -> dict:
    page, error = _parse_browser_page(url)
    if error is not None:
        return error
    assert page is not None
    return {
        "success": True,
        "url": page["url"],
        "final_url": page["final_url"],
        "title": page["title"],
        "status_code": page["status_code"],
        "links": page["links"],
        "link_count": len(page.get("links") or []),
    }


def browser_open_result(query: str, index: int = 0, max_chars: int = 8000) -> dict:
    try:
        safe_index = max(0, int(index))
    except Exception:
        safe_index = 0
    search_result = browser_search(query, limit=max(5, safe_index + 1))
    if not search_result.get("success"):
        return search_result
    results = search_result.get("results") or []
    if safe_index >= len(results):
        return {
            "error": f"索引超出范围: index={safe_index}, 可用结果数={len(results)}",
            "query": query,
            "results": results,
        }
    selected = results[safe_index]
    opened = browser_open(str(selected.get("url") or ""), max_chars=max_chars)
    if opened.get("success"):
        opened["query"] = query
        opened["search_index"] = safe_index
        opened["search_result"] = selected
    return opened


def append_file_content(file_path: str, content: str) -> dict:
    """向文件末尾追加内容。"""

    try:
        path = Path(file_path).expanduser().resolve()
        mode = "a" if path.exists() else "w"
        prefix = ""
        if mode == "a" and path.stat().st_size > 0:
            with open(path, "rb") as handle:
                handle.seek(-1, 2)
                if handle.read(1) != b"\n":
                    prefix = "\n"
        with open(path, mode, encoding="utf-8") as handle:
            handle.write(prefix + content)
        return {"success": True, "path": str(path), "message": "内容已追加"}
    except Exception as exc:
        return {"error": str(exc)}


def grep_search(
    pattern: str,
    path: str = ".",
    include_extension: str = None,
    recursive: bool = True,
) -> dict:
    """使用正则搜索文件内容。"""

    try:
        search_path = Path(path).expanduser().resolve()
        results = []
        count = 0
        max_results = 20
        glob_pattern = "**/*" if recursive else "*"
        for file_path in search_path.glob(glob_pattern):
            if not file_path.is_file():
                continue
            if include_extension and file_path.suffix != include_extension:
                continue
            if file_path.stat().st_size > 1024 * 1024:
                continue
            try:
                file_content = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            matches = list(re.finditer(pattern, file_content, re.MULTILINE))
            if not matches:
                continue
            file_matches = []
            for match in matches[:5]:
                line_num = file_content.count("\n", 0, match.start()) + 1
                line_start = file_content.rfind("\n", 0, match.start()) + 1
                line_end = file_content.find("\n", match.end())
                if line_end == -1:
                    line_end = len(file_content)
                line_content = file_content[line_start:line_end].strip()
                file_matches.append(f"Line {line_num}: {line_content[:100]}")
            results.append(
                f"File: {file_path.relative_to(search_path)}\n" + "\n".join(file_matches)
            )
            count += 1
            if count >= max_results:
                break
        return {
            "success": True,
            "matches_found": count,
            "results": "\n\n".join(results) if results else "No matches found",
        }
    except Exception as exc:
        return {"error": str(exc)}


def execute_batch_commands(commands: list, stop_on_error: bool = True) -> dict:
    """批量顺序执行多条 Shell 命令，默认遇错停止。"""

    results = []
    overall_success = True
    for command in commands:
        result = execute_command(command)
        results.append({"command": command, "result": result})
        if not result.get("success", False):
            overall_success = False
            if stop_on_error:
                break
    return {"success": overall_success, "executed_count": len(results), "results": results}


def fetch_url(url: str) -> dict:
    """抓取 URL 页面并返回纯文本内容。"""

    opened = browser_open(url, max_chars=5000)
    if not opened.get("success"):
        return opened
    return {
        "success": True,
        "url": opened.get("url"),
        "final_url": opened.get("final_url"),
        "title": opened.get("title"),
        "content": opened.get("content", ""),
        "truncated": opened.get("truncated", False),
        "links": opened.get("links", []),
    }


def get_current_time() -> dict:
    """获取当前系统时间、星期和时区。"""

    try:
        now = datetime.now()
        return {
            "success": True,
            "current_time": now.strftime("%Y-%m-%d %H:%M:%S"),
            "weekday": now.strftime("%A"),
            "timezone": str(now.astimezone().tzinfo),
        }
    except Exception as exc:
        return {"error": str(exc)}


def ask_human(question: str) -> dict:
    """向用户提问并等待输入。"""

    try:
        CONSOLE.print(f"\n[cyan][❓ AI Question]: {question}[/]")
        answer = input(" > ")
        return {"success": True, "answer": answer}
    except Exception as exc:
        return {"error": str(exc)}


def git_status() -> dict:
    return execute_command("git status")


def git_diff() -> dict:
    return execute_command("git diff")


def git_commit(message: str) -> dict:
    return execute_command(f"git commit -m {shlex.quote(message)}")


def edit_file_lines(
    file_path: str,
    operation: str,
    start_line: int,
    end_line: int = None,
    new_content: str = None,
) -> dict:
    """基于行号编辑文件（replace/insert/delete）。"""

    try:
        path = Path(file_path).expanduser().resolve()
        if not path.exists():
            return {"error": f"文件不存在: {file_path}"}
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines(keepends=True)
        total = len(lines)
        if start_line < 1 or start_line > total:
            return {"error": f"start_line {start_line} 超出范围 [1, {total}]"}
        if end_line is None:
            end_line = start_line
        if end_line < start_line or end_line > total:
            return {"error": f"end_line {end_line} 无效"}
        start_index, end_index = start_line - 1, end_line
        if operation == "replace":
            if new_content is None:
                return {"error": "replace 需要 new_content"}
            if not new_content.endswith("\n"):
                new_content += "\n"
            new_lines = (
                lines[:start_index] + new_content.splitlines(keepends=True) + lines[end_index:]
            )
        elif operation == "insert":
            if new_content is None:
                return {"error": "insert 需要 new_content"}
            if not new_content.endswith("\n"):
                new_content += "\n"
            new_lines = (
                lines[:start_index] + new_content.splitlines(keepends=True) + lines[start_index:]
            )
        elif operation == "delete":
            new_lines = lines[:start_index] + lines[end_index:]
        else:
            return {"error": f"未知操作: {operation}"}
        path.write_text("".join(new_lines), encoding="utf-8")
        return {
            "success": True,
            "path": str(path),
            "operation": operation,
            "new_total_lines": len(new_lines),
        }
    except Exception as exc:
        return {"error": str(exc)}


def insert_content_by_regex(file_path: str, regex_pattern: str, content: str) -> dict:
    """在文件第一个正则匹配位置之后插入内容。"""

    try:
        path = Path(file_path).expanduser().resolve()
        if not path.exists():
            return {"error": f"文件不存在: {file_path}"}
        file_content = path.read_text(encoding="utf-8", errors="ignore")
        match = re.search(regex_pattern, file_content, re.MULTILINE)
        if not match:
            return {"error": f"正则 '{regex_pattern}' 未匹配到内容"}
        new_content = file_content[: match.end()] + content + file_content[match.end() :]
        path.write_text(new_content, encoding="utf-8")
        return {
            "success": True,
            "path": str(path),
            "match_found": match.group(0)[:50],
            "message": "内容已插入",
        }
    except Exception as exc:
        return {"error": str(exc)}


def check_python_code(file_path: str) -> dict:
    """检查 Python 文件语法和风格（flake8 / ast）。"""

    try:
        path = Path(file_path).expanduser().resolve()
        if not path.exists():
            return {"error": f"文件不存在: {file_path}"}
        try:
            ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            return {
                "success": False,
                "error_type": "SyntaxError",
                "line": exc.lineno,
                "message": str(exc),
            }
        lint_result = ""
        try:
            result = subprocess.run(
                f"flake8 {shlex.quote(str(path))}",
                shell=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0 and result.stdout:
                lint_result = f"Flake8:\n{result.stdout}"
        except Exception:
            pass
        return {
            "success": True,
            "message": "语法检查通过",
            "linter_output": lint_result or "无问题",
        }
    except Exception as exc:
        return {"error": str(exc)}


def run_python_code(code: str) -> dict:
    """执行 Python 代码片段（临时文件沙箱）。"""

    import tempfile

    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as handle:
            handle.write(code)
            tmp_path = handle.name
        result = subprocess.run(
            [sys.executable, tmp_path], capture_output=True, text=True, timeout=30
        )
        try:
            Path(tmp_path).unlink()
        except Exception:
            pass
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout[:3000],
            "stderr": result.stderr[:1000],
            "returncode": result.returncode,
        }
    except Exception as exc:
        return {"error": str(exc)}


__all__ = [
    "append_file_content",
    "ask_human",
    "browser_extract_links",
    "browser_open",
    "browser_open_result",
    "browser_search",
    "check_python_code",
    "create_or_overwrite_file",
    "edit_file_lines",
    "execute_batch_commands",
    "execute_command",
    "fetch_url",
    "get_current_time",
    "git_commit",
    "git_diff",
    "git_status",
    "grep_search",
    "insert_content_by_regex",
    "list_directory",
    "read_file",
    "run_python_code",
    "search_files",
    "str_replace_edit",
    "web_search",
]

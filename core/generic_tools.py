"""Generic file, shell, and git tools used by Gary."""

from __future__ import annotations

import ast
import json
import re
import shlex
import subprocess
import sys
from datetime import datetime
from pathlib import Path

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
            return {"error": f"文件不存在: {file_path}"}
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
        items = [{"name": item.name, "type": "dir" if item.is_dir() else "file"} for item in target.iterdir()]
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


def web_search(query: str) -> dict:
    try:
        response = requests.get(
            "http://127.0.0.1:8080/search",
            params={"q": query, "format": "json"},
            timeout=8,
        )
        data = response.json()
        results = [
            {"title": item.get("title"), "url": item.get("url"), "snippet": item.get("content", "")[:200]}
            for item in data.get("results", [])[:5]
        ]
        return {"success": True, "results": results}
    except Exception as exc:
        return {"error": f"搜索失败（需要本地 SearXNG）: {exc}"}


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
            results.append(f"File: {file_path.relative_to(search_path)}\n" + "\n".join(file_matches))
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

    try:
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            return {"error": "beautifulsoup4 未安装: pip install beautifulsoup4"}
        headers = {"User-Agent": "Mozilla/5.0 (compatible; STM32Agent/1.0)"}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        text = soup.get_text()
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = "\n".join(chunk for chunk in chunks if chunk)
        return {"success": True, "url": url, "content": text[:5000], "truncated": len(text) > 5000}
    except Exception as exc:
        return {"error": f"获取失败: {exc}"}


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
            new_lines = lines[:start_index] + new_content.splitlines(keepends=True) + lines[end_index:]
        elif operation == "insert":
            if new_content is None:
                return {"error": "insert 需要 new_content"}
            if not new_content.endswith("\n"):
                new_content += "\n"
            new_lines = lines[:start_index] + new_content.splitlines(keepends=True) + lines[start_index:]
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
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as handle:
            handle.write(code)
            tmp_path = handle.name
        result = subprocess.run([sys.executable, tmp_path], capture_output=True, text=True, timeout=30)
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

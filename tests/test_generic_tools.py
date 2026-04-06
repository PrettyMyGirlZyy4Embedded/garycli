"""Tests for generic file-edit helpers."""

from __future__ import annotations

from core.generic_tools import str_replace_edit


def test_str_replace_edit_missing_latest_workspace_returns_actionable_hint(tmp_path):
    """Missing latest workspace files should return guidance instead of a bare path error."""

    missing = tmp_path / "workspace" / "projects" / "latest_workspace" / "main.py"
    result = str_replace_edit(str(missing), "old", "new")

    assert "文件不存在" in result["error"]
    assert "latest_workspace 还没有缓存源码" in result["error"]
    assert "compile / auto_sync_cycle" in result["error"]

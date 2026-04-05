"""Project persistence helpers for generated Gary source code."""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

from config import PROJECTS_DIR
from core.platforms import canonical_target_name, detect_target_platform, source_filename_for_target

LATEST_WORKSPACE_DIR = PROJECTS_DIR / "latest_workspace"


def latest_workspace_main_path(chip: str | None = None) -> Path:
    """Return the canonical latest-workspace source path for the selected target."""

    return LATEST_WORKSPACE_DIR / source_filename_for_target(chip)


def sync_latest_workspace(code: str, *, chip: str | None = None) -> dict[str, Any]:
    """Write the latest generated source into the compatibility workspace."""

    try:
        LATEST_WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
        source_path = latest_workspace_main_path(chip)
        source_path.write_text(code, encoding="utf-8")
        return {"success": True, "path": str(source_path), "source_file": source_path.name}
    except Exception as exc:
        return {"success": False, "message": str(exc)}


def save_project(
    code: str,
    comp: dict[str, Any],
    request: str,
    *,
    chip: str,
    console: Any = None,
) -> Path:
    """Persist one generated project under `workspace/projects`."""

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    safe = "".join(c if c.isalnum() or c in "_- " else "" for c in request[:30]).strip()
    project_dir = PROJECTS_DIR / f"{timestamp}_{safe}"
    project_dir.mkdir(parents=True, exist_ok=True)
    chip_name = canonical_target_name(chip)
    source_file = source_filename_for_target(chip_name)
    (project_dir / source_file).write_text(code, encoding="utf-8")
    if comp.get("bin_path") and Path(comp["bin_path"]).exists():
        shutil.copy2(comp["bin_path"], project_dir / "firmware.bin")
    (project_dir / "config.json").write_text(
        json.dumps(
            {
                "chip": chip_name,
                "platform": detect_target_platform(chip_name),
                "source_file": source_file,
                "request": request,
                "bin_size": comp.get("bin_size", 0),
                "timestamp": timestamp,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    sync_latest_workspace(code, chip=chip_name)
    if console is not None:
        try:
            console.print(f"[dim]  已保存: {project_dir}[/]")
        except Exception:
            pass
    return project_dir


def save_code(code: str, request: str, *, chip: str, console: Any = None) -> dict[str, Any]:
    """Persist source code only, without a compiled binary."""

    project_dir = save_project(
        code,
        {"bin_path": None, "bin_size": 0},
        request,
        chip=chip,
        console=console,
    )
    return {"success": True, "path": str(project_dir), "message": f"已保存: {project_dir}"}


def list_projects() -> dict[str, Any]:
    """List recent persisted projects."""

    if not PROJECTS_DIR.exists():
        return {"success": True, "projects": [], "message": "暂无项目"}

    projects = []
    for project_dir in sorted(PROJECTS_DIR.iterdir(), reverse=True)[:15]:
        config_file = project_dir / "config.json"
        if not config_file.exists():
            continue
        try:
            config = json.loads(config_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        projects.append(
            {
                "name": project_dir.name,
                "chip": config.get("chip", "?"),
                "platform": config.get("platform", detect_target_platform(config.get("chip"))),
                "source_file": config.get("source_file", source_filename_for_target(config.get("chip"))),
                "request": config.get("request", ""),
                "timestamp": config.get("timestamp", ""),
            }
        )
    return {"success": True, "projects": projects}


def read_project(project_name: str) -> dict[str, Any]:
    """Read one stored project's source file."""

    project_dir = PROJECTS_DIR / project_name
    if not project_dir.exists():
        return {"success": False, "message": f"项目不存在: {project_name}"}

    config = {}
    config_path = project_dir / "config.json"
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            config = {}

    source_file = config.get("source_file") or source_filename_for_target(config.get("chip"))
    source_path = project_dir / source_file
    if not source_path.exists():
        fallback = next(
            (project_dir / name for name in ("main.py", "main.c") if (project_dir / name).exists()),
            None,
        )
        if fallback is not None:
            source_path = fallback
    if not source_path.exists():
        return {"success": False, "message": f"项目不存在: {project_name}"}
    code = source_path.read_text(encoding="utf-8")
    return {
        "success": True,
        "code": code,
        "path": str(source_path),
        "source_file": source_path.name,
        "lines": len(code.splitlines()),
    }


__all__ = [
    "LATEST_WORKSPACE_DIR",
    "latest_workspace_main_path",
    "list_projects",
    "read_project",
    "save_code",
    "save_project",
    "sync_latest_workspace",
]

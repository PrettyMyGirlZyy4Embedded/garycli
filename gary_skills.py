#!/usr/bin/env python3
import sys, os, json, re, shutil, subprocess, importlib, importlib.util, zipfile, hashlib
import time, traceback
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime

# ─────────────────────────────────────────────────────────────
# 常量
# ─────────────────────────────────────────────────────────────

GARY_HOME = Path.home() / ".gary"
SKILLS_DIR = GARY_HOME / "skills"
DISABLED_DIR = SKILLS_DIR / "_disabled"
SKILLS_REGISTRY = GARY_HOME / "skills_registry.json"

# 技能包必须包含的文件
REQUIRED_FILES = ["skill.json", "tools.py", "schemas.json"]

# skill.json 的 schema 版本
SKILL_SCHEMA_VERSION = "1.0"

# 尝试导入 rich
try:
    from rich.console import Console
    from rich.table import Table
    from rich import box
    CONSOLE = Console()
except ImportError:
    class _FC:
        def print(self, *a, **kw):
            text = str(a[0]) if a else ""
            text = re.sub(r'\[.*?\]', '', text)
            print(text)
    CONSOLE = _FC()


# ─────────────────────────────────────────────────────────────
# Skill 元信息
# ─────────────────────────────────────────────────────────────

@dataclass
class SkillMeta:
    """skill.json 对应的数据结构"""
    name: str = ""                      # 唯一标识（英文，下划线分隔）
    display_name: str = ""              # 显示名称（可中文）
    version: str = "1.0.0"
    description: str = ""               # 一句话描述
    author: str = ""
    url: str = ""                       # 项目/仓库地址
    license: str = "MIT"
    tags: List[str] = field(default_factory=list)  # 标签: ["pid", "motor", "control"]
    chip_families: List[str] = field(default_factory=lambda: ["all"])  # 适用芯片系列
    dependencies: List[str] = field(default_factory=list)  # Python 包依赖
    skill_dependencies: List[str] = field(default_factory=list)  # 依赖的其他 skill
    min_gary_version: str = "1.0.0"
    schema_version: str = SKILL_SCHEMA_VERSION
    enabled: bool = True
    install_time: str = ""
    # 运行时
    tools_count: int = 0
    load_error: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "SkillMeta":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in d.items() if k in known}
        return cls(**filtered)

    def to_dict(self) -> dict:
        return asdict(self)


# ─────────────────────────────────────────────────────────────
# Skill 加载器
# ─────────────────────────────────────────────────────────────

@dataclass
class LoadedSkill:
    """一个已加载的 skill 实例"""
    meta: SkillMeta
    path: Path
    tools_map: Dict[str, Any] = field(default_factory=dict)
    tool_schemas: List[dict] = field(default_factory=list)
    prompt_addition: str = ""
    module: Any = None  # Python module 对象


def _load_skill_module(skill_dir: Path) -> Tuple[Optional[Any], str]:
    """动态加载 skill 的 tools.py 模块"""
    tools_py = skill_dir / "tools.py"
    if not tools_py.exists():
        return None, f"tools.py 不存在: {tools_py}"

    module_name = f"gary_skill_{skill_dir.name}"
    try:
        spec = importlib.util.spec_from_file_location(module_name, str(tools_py))
        if spec is None or spec.loader is None:
            return None, f"无法创建模块 spec: {tools_py}"
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module, ""
    except Exception as e:
        return None, f"加载 tools.py 失败: {e}\n{traceback.format_exc()}"


def _load_schemas(skill_dir: Path) -> Tuple[List[dict], str]:
    """加载 schemas.json"""
    schemas_file = skill_dir / "schemas.json"
    if not schemas_file.exists():
        return [], f"schemas.json 不存在"
    try:
        data = json.loads(schemas_file.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data, ""
        elif isinstance(data, dict) and "tools" in data:
            return data["tools"], ""
        return [], "schemas.json 格式错误：需要是列表或包含 'tools' 键"
    except Exception as e:
        return [], f"schemas.json 解析失败: {e}"


def _load_prompt(skill_dir: Path) -> str:
    """加载 prompt.md"""
    prompt_file = skill_dir / "prompt.md"
    if prompt_file.exists():
        return prompt_file.read_text(encoding="utf-8").strip()
    return ""


def load_skill(skill_dir: Path) -> LoadedSkill:
    """加载单个 skill 目录"""
    # 1. 读取元信息
    meta_file = skill_dir / "skill.json"
    if not meta_file.exists():
        meta = SkillMeta(name=skill_dir.name, load_error="skill.json 缺失")
        return LoadedSkill(meta=meta, path=skill_dir)

    try:
        meta_dict = json.loads(meta_file.read_text(encoding="utf-8"))
        meta = SkillMeta.from_dict(meta_dict)
        meta.name = meta.name or skill_dir.name
    except Exception as e:
        meta = SkillMeta(name=skill_dir.name, load_error=f"skill.json 解析失败: {e}")
        return LoadedSkill(meta=meta, path=skill_dir)

    skill = LoadedSkill(meta=meta, path=skill_dir)

    # 2. 加载 Python 模块
    module, err = _load_skill_module(skill_dir)
    if err:
        meta.load_error = err
        return skill
    skill.module = module

    # 3. 提取 tools_map
    # 优先从 module.TOOLS_MAP 获取，否则扫描所有 public 函数
    if hasattr(module, "TOOLS_MAP") and isinstance(module.TOOLS_MAP, dict):
        skill.tools_map = dict(module.TOOLS_MAP)
    elif hasattr(module, "EXTRA_TOOLS_MAP") and isinstance(module.EXTRA_TOOLS_MAP, dict):
        skill.tools_map = dict(module.EXTRA_TOOLS_MAP)
    else:
        # 自动发现：所有不以 _ 开头的可调用对象
        skill.tools_map = {
            name: getattr(module, name)
            for name in dir(module)
            if not name.startswith("_") and callable(getattr(module, name))
            and not isinstance(getattr(module, name), type)
        }

    # 4. 加载 Schemas
    schemas, err = _load_schemas(skill_dir)
    if err and not schemas:
        # schemas.json 失败时，尝试从 module 获取
        if hasattr(module, "TOOL_SCHEMAS"):
            skill.tool_schemas = list(module.TOOL_SCHEMAS)
        elif hasattr(module, "EXTRA_TOOL_SCHEMAS"):
            skill.tool_schemas = list(module.EXTRA_TOOL_SCHEMAS)
        else:
            meta.load_error = f"无法加载工具 Schema: {err}"
    else:
        skill.tool_schemas = schemas

    # 5. 加载 Prompt
    skill.prompt_addition = _load_prompt(skill_dir)

    meta.tools_count = len(skill.tools_map)
    return skill


# ─────────────────────────────────────────────────────────────
# Skills Manager
# ─────────────────────────────────────────────────────────────

class SkillsManager:
    """
    技能包管理器。
    负责安装、卸载、启用、禁用、加载技能，
    并将工具注册到 Gary 的 TOOLS_MAP / TOOL_SCHEMAS / SYSTEM_PROMPT。
    """

    def __init__(self):
        self._skills: Dict[str, LoadedSkill] = {}  # name → LoadedSkill
        self._ensure_dirs()

    def _ensure_dirs(self):
        SKILLS_DIR.mkdir(parents=True, exist_ok=True)
        DISABLED_DIR.mkdir(parents=True, exist_ok=True)

    # ── 注册表持久化 ────────────────────────────────────────

    def _save_registry(self):
        """保存技能注册信息到 JSON"""
        data = {}
        for name, skill in self._skills.items():
            data[name] = {
                "enabled": skill.meta.enabled,
                "install_time": skill.meta.install_time,
                "version": skill.meta.version,
            }
        # 也记录禁用的
        for d in DISABLED_DIR.iterdir():
            if d.is_dir() and d.name not in data:
                meta_file = d / "skill.json"
                if meta_file.exists():
                    try:
                        m = json.loads(meta_file.read_text(encoding="utf-8"))
                        data[d.name] = {"enabled": False,
                                         "install_time": m.get("install_time", ""),
                                         "version": m.get("version", "")}
                    except Exception:
                        pass
        SKILLS_REGISTRY.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def _load_registry(self) -> dict:
        if SKILLS_REGISTRY.exists():
            try:
                return json.loads(SKILLS_REGISTRY.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    # ── 加载所有技能 ────────────────────────────────────────

    def load_all(self) -> Dict[str, LoadedSkill]:
        """扫描 skills 目录，加载所有已启用的技能"""
        self._skills.clear()
        registry = self._load_registry()

        if not SKILLS_DIR.exists():
            return self._skills

        for skill_dir in sorted(SKILLS_DIR.iterdir()):
            if not skill_dir.is_dir():
                continue
            if skill_dir.name.startswith("_"):
                continue  # 跳过 _disabled 等

            skill = load_skill(skill_dir)

            # 从注册表恢复启用状态
            if skill.meta.name in registry:
                skill.meta.enabled = registry[skill.meta.name].get("enabled", True)

            if not skill.meta.enabled:
                continue

            self._skills[skill.meta.name] = skill

            if skill.meta.load_error:
                CONSOLE.print(f"[yellow]  ⚠ Skill [{skill.meta.name}] 加载有错: {skill.meta.load_error[:80]}[/]")
            else:
                CONSOLE.print(
                    f"[green]  ✓ Skill [{skill.meta.display_name or skill.meta.name}] "
                    f"v{skill.meta.version} — {skill.meta.tools_count} 个工具[/]"
                )

        self._save_registry()
        return self._skills

    # ── 获取合并后的工具和提示词 ─────────────────────────────

    def get_all_tools_map(self) -> Dict[str, Any]:
        """合并所有已启用 skill 的 tools_map"""
        merged = {}
        for skill in self._skills.values():
            if skill.meta.enabled and not skill.meta.load_error:
                merged.update(skill.tools_map)
        return merged

    def get_all_tool_schemas(self) -> List[dict]:
        """合并所有已启用 skill 的 tool_schemas"""
        merged = []
        for skill in self._skills.values():
            if skill.meta.enabled and not skill.meta.load_error:
                merged.extend(skill.tool_schemas)
        return merged

    def get_all_prompt_additions(self) -> str:
        """合并所有已启用 skill 的 prompt 追加内容"""
        parts = []
        for skill in self._skills.values():
            if skill.meta.enabled and skill.prompt_addition:
                parts.append(
                    f"\n## Skill: {skill.meta.display_name or skill.meta.name}\n"
                    f"{skill.prompt_addition}"
                )
        return "\n".join(parts)

    # ── 安装技能 ────────────────────────────────────────────

    def install(self, source: str) -> dict:
        """
        安装技能包。
        source 可以是：
          - 本地目录路径
          - .zip 文件路径
          - Git 仓库 URL（TODO）
        """
        source = source.strip()
        src_path = Path(source).expanduser().resolve()

        # ── 情况 1: 本地目录 ─────────────────────────────────
        if src_path.is_dir():
            return self._install_from_dir(src_path)

        # ── 情况 2: .zip 文件 ────────────────────────────────
        if src_path.is_file() and src_path.suffix == ".zip":
            return self._install_from_zip(src_path)

        # ── 情况 3: .py 单文件（自动包装成 skill）────────────
        if src_path.is_file() and src_path.suffix == ".py":
            return self._install_from_single_py(src_path)

        # ── 情况 4: Git URL ─────────────────────────────────
        if source.startswith("http") and (".git" in source or "github.com" in source):
            return self._install_from_git(source)

        return {"success": False, "message": f"不支持的来源: {source}\n支持: 目录、.zip、.py、Git URL"}

    def _validate_skill_dir(self, d: Path) -> Tuple[bool, str]:
        """验证 skill 目录完整性"""
        missing = [f for f in REQUIRED_FILES if not (d / f).exists()]
        if missing:
            # tools.py 是必须的，但 schemas.json 可以从 module 导出
            if "schemas.json" in missing and (d / "tools.py").exists():
                missing.remove("schemas.json")
            if missing:
                return False, f"缺少必要文件: {', '.join(missing)}"

        # 验证 skill.json 格式
        try:
            meta = json.loads((d / "skill.json").read_text(encoding="utf-8"))
            if "name" not in meta:
                return False, "skill.json 缺少 'name' 字段"
        except Exception as e:
            return False, f"skill.json 格式错误: {e}"

        return True, ""

    def _install_from_dir(self, src: Path) -> dict:
        """从本地目录安装"""
        ok, err = self._validate_skill_dir(src)
        if not ok:
            return {"success": False, "message": err}

        meta = json.loads((src / "skill.json").read_text(encoding="utf-8"))
        name = meta["name"]
        dest = SKILLS_DIR / name

        # 已存在？升级
        if dest.exists():
            # 备份旧版
            bak = SKILLS_DIR / f"_backup_{name}_{int(time.time())}"
            shutil.move(str(dest), str(bak))
            CONSOLE.print(f"[dim]  旧版已备份: {bak.name}[/]")

        shutil.copytree(str(src), str(dest))

        # 更新安装时间
        meta["install_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        (dest / "skill.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

        # 安装依赖
        self._install_deps(dest)

        # 加载
        skill = load_skill(dest)
        self._skills[name] = skill
        self._save_registry()

        return {
            "success": True,
            "name": name,
            "version": meta.get("version", "?"),
            "tools_count": skill.meta.tools_count,
            "message": f"已安装: {meta.get('display_name', name)} v{meta.get('version', '?')} ({skill.meta.tools_count} 个工具)",
        }

    def _install_from_zip(self, zip_path: Path) -> dict:
        """从 .zip 文件安装"""
        import tempfile
        tmp = Path(tempfile.mkdtemp(prefix="gary_skill_"))
        try:
            with zipfile.ZipFile(str(zip_path), 'r') as zf:
                zf.extractall(str(tmp))

            # zip 可能有顶层目录，也可能直接是文件
            contents = list(tmp.iterdir())
            if len(contents) == 1 and contents[0].is_dir():
                skill_dir = contents[0]
            else:
                skill_dir = tmp

            return self._install_from_dir(skill_dir)
        except Exception as e:
            return {"success": False, "message": f"解压失败: {e}"}
        finally:
            shutil.rmtree(str(tmp), ignore_errors=True)

    def _install_from_single_py(self, py_path: Path) -> dict:
        """
        从单个 .py 文件安装（自动生成 skill.json 和 schemas.json）。
        适合快速导入别人写的工具文件（如 stm32_extra_tools.py）。
        """
        import tempfile

        name = py_path.stem.replace("-", "_").replace(" ", "_")
        tmp = Path(tempfile.mkdtemp(prefix="gary_skill_"))
        skill_dir = tmp / name
        skill_dir.mkdir()

        # 复制 tools.py
        shutil.copy2(str(py_path), str(skill_dir / "tools.py"))

        # 尝试加载模块提取信息
        module, err = _load_skill_module(skill_dir)
        tools_count = 0
        schemas = []

        if module:
            # 提取 TOOLS_MAP
            tmap = None
            for attr in ("TOOLS_MAP", "EXTRA_TOOLS_MAP", "UART_FLASH_TOOLS_MAP"):
                if hasattr(module, attr):
                    tmap = getattr(module, attr)
                    break
            if tmap:
                tools_count = len(tmap)

            # 提取 TOOL_SCHEMAS
            for attr in ("TOOL_SCHEMAS", "EXTRA_TOOL_SCHEMAS", "UART_FLASH_TOOL_SCHEMAS"):
                if hasattr(module, attr):
                    schemas = list(getattr(module, attr))
                    break

        # 生成 skill.json
        meta = {
            "name": name,
            "display_name": name.replace("_", " ").title(),
            "version": "1.0.0",
            "description": f"从 {py_path.name} 自动导入",
            "author": "auto-import",
            "tags": ["imported"],
            "schema_version": SKILL_SCHEMA_VERSION,
        }
        (skill_dir / "skill.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

        # 生成 schemas.json
        if schemas:
            (skill_dir / "schemas.json").write_text(
                json.dumps(schemas, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        else:
            (skill_dir / "schemas.json").write_text("[]", encoding="utf-8")

        result = self._install_from_dir(skill_dir)
        shutil.rmtree(str(tmp), ignore_errors=True)
        return result

    def _install_from_git(self, url: str) -> dict:
        """从 Git 仓库安装"""
        import tempfile
        tmp = Path(tempfile.mkdtemp(prefix="gary_skill_git_"))
        try:
            result = subprocess.run(
                ["git", "clone", "--depth", "1", url, str(tmp / "repo")],
                capture_output=True, text=True, timeout=60
            )
            if result.returncode != 0:
                return {"success": False, "message": f"git clone 失败: {result.stderr[:200]}"}

            repo_dir = tmp / "repo"
            # 如果根目录就是 skill
            if (repo_dir / "skill.json").exists():
                return self._install_from_dir(repo_dir)
            # 否则搜索子目录
            for d in repo_dir.iterdir():
                if d.is_dir() and (d / "skill.json").exists():
                    return self._install_from_dir(d)

            return {"success": False, "message": "仓库中未找到 skill.json"}
        except Exception as e:
            return {"success": False, "message": f"Git 安装失败: {e}"}
        finally:
            shutil.rmtree(str(tmp), ignore_errors=True)

    def _install_deps(self, skill_dir: Path):
        """安装 skill 的 Python 依赖"""
        req_file = skill_dir / "requirements.txt"
        if not req_file.exists():
            return

        deps = [l.strip() for l in req_file.read_text().splitlines() if l.strip() and not l.startswith("#")]
        if not deps:
            return

        CONSOLE.print(f"[dim]  安装依赖: {', '.join(deps)}[/]")
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "--quiet"] + deps,
                capture_output=True, timeout=120
            )
        except Exception as e:
            CONSOLE.print(f"[yellow]  依赖安装失败: {e}[/]")

    # ── 卸载 ────────────────────────────────────────────────

    def uninstall(self, name: str) -> dict:
        """卸载技能（删除目录）"""
        skill_dir = SKILLS_DIR / name
        disabled_dir = DISABLED_DIR / name

        target = skill_dir if skill_dir.exists() else (disabled_dir if disabled_dir.exists() else None)
        if target is None:
            return {"success": False, "message": f"技能不存在: {name}"}

        shutil.rmtree(str(target))
        self._skills.pop(name, None)
        self._save_registry()

        return {"success": True, "message": f"已卸载: {name}"}

    # ── 启用/禁用 ───────────────────────────────────────────

    def enable(self, name: str) -> dict:
        """启用技能（从 _disabled 移回 skills/）"""
        disabled_path = DISABLED_DIR / name
        enabled_path = SKILLS_DIR / name

        if enabled_path.exists():
            # 已在 skills/ 中，只需标记启用
            skill = load_skill(enabled_path)
            skill.meta.enabled = True
            self._skills[name] = skill
            self._save_registry()
            return {"success": True, "message": f"已启用: {name} ({skill.meta.tools_count} 个工具)"}

        if disabled_path.exists():
            shutil.move(str(disabled_path), str(enabled_path))
            skill = load_skill(enabled_path)
            skill.meta.enabled = True
            self._skills[name] = skill
            self._save_registry()
            return {"success": True, "message": f"已启用: {name}"}

        return {"success": False, "message": f"技能不存在: {name}"}

    def disable(self, name: str) -> dict:
        """禁用技能（移到 _disabled/）"""
        enabled_path = SKILLS_DIR / name
        disabled_path = DISABLED_DIR / name

        if not enabled_path.exists():
            return {"success": False, "message": f"技能不存在或已禁用: {name}"}

        if disabled_path.exists():
            shutil.rmtree(str(disabled_path))
        shutil.move(str(enabled_path), str(disabled_path))
        self._skills.pop(name, None)
        self._save_registry()

        return {"success": True, "message": f"已禁用: {name}（/skill enable {name} 重新启用）"}

    # ── 列表/详情 ───────────────────────────────────────────

    def list_skills(self) -> dict:
        """列出所有技能（含已禁用）"""
        skills = []

        # 已启用
        for name, skill in self._skills.items():
            skills.append({
                "name": name,
                "display_name": skill.meta.display_name or name,
                "version": skill.meta.version,
                "description": skill.meta.description,
                "tools_count": skill.meta.tools_count,
                "enabled": True,
                "error": skill.meta.load_error[:60] if skill.meta.load_error else "",
                "author": skill.meta.author,
                "tags": skill.meta.tags,
            })

        # 已禁用
        for d in DISABLED_DIR.iterdir():
            if d.is_dir() and d.name not in self._skills:
                meta_file = d / "skill.json"
                if meta_file.exists():
                    try:
                        m = json.loads(meta_file.read_text(encoding="utf-8"))
                        skills.append({
                            "name": m.get("name", d.name),
                            "display_name": m.get("display_name", d.name),
                            "version": m.get("version", "?"),
                            "description": m.get("description", ""),
                            "tools_count": 0,
                            "enabled": False,
                            "error": "",
                            "author": m.get("author", ""),
                            "tags": m.get("tags", []),
                        })
                    except Exception:
                        pass

        return {"success": True, "skills": skills, "total": len(skills)}

    def info(self, name: str) -> dict:
        """查看技能详细信息"""
        skill = self._skills.get(name)
        if skill:
            return {
                "success": True,
                "meta": skill.meta.to_dict(),
                "tools": list(skill.tools_map.keys()),
                "has_prompt": bool(skill.prompt_addition),
                "prompt_preview": skill.prompt_addition[:300] if skill.prompt_addition else "",
                "path": str(skill.path),
            }

        # 检查禁用目录
        disabled_path = DISABLED_DIR / name
        if disabled_path.exists() and (disabled_path / "skill.json").exists():
            meta = json.loads((disabled_path / "skill.json").read_text(encoding="utf-8"))
            return {"success": True, "meta": meta, "enabled": False, "path": str(disabled_path)}

        return {"success": False, "message": f"技能不存在: {name}"}

    # ── 创建技能模板 ────────────────────────────────────────

    def create_template(self, name: str, description: str = "") -> dict:
        """在 skills/ 下创建技能模板目录"""
        name = re.sub(r'[^a-zA-Z0-9_]', '_', name.lower().strip())
        dest = SKILLS_DIR / name
        if dest.exists():
            return {"success": False, "message": f"已存在: {name}"}

        dest.mkdir(parents=True)

        # skill.json
        meta = {
            "name": name,
            "display_name": name.replace("_", " ").title(),
            "version": "1.0.0",
            "description": description or f"{name} skill for Gary Dev Agent",
            "author": "",
            "url": "",
            "license": "MIT",
            "tags": [],
            "chip_families": ["all"],
            "dependencies": [],
            "skill_dependencies": [],
            "min_gary_version": "1.0.0",
            "schema_version": SKILL_SCHEMA_VERSION,
        }
        (dest / "skill.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

        # tools.py 模板
        (dest / "tools.py").write_text(f'''#!/usr/bin/env python3
"""
{name} — Gary Skill
"""
from typing import Dict, Any, List


# ═══ 工具函数 ═══

def {name}_hello() -> dict:
    """示例工具函数"""
    return {{"success": True, "message": "Hello from {name} skill!"}}


# ═══ 工具注册表（必须导出）═══

TOOLS_MAP: Dict[str, Any] = {{
    "{name}_hello": {name}_hello,
}}
''', encoding="utf-8")

        # schemas.json 模板
        schemas = [{
            "type": "function",
            "function": {
                "name": f"{name}_hello",
                "description": f"示例工具 - {name}",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        }]
        (dest / "schemas.json").write_text(json.dumps(schemas, indent=2, ensure_ascii=False), encoding="utf-8")

        # prompt.md 模板
        (dest / "prompt.md").write_text(f"""## {name.replace('_', ' ').title()} Skill

这个技能提供了以下工具：
- `{name}_hello` — 示例工具

### 使用场景
（在这里描述 AI 应该在什么情况下使用这些工具）
""", encoding="utf-8")

        # README.md
        (dest / "README.md").write_text(f"""# {name.replace('_', ' ').title()}

Gary Dev Agent Skill.

## 安装
```
/skill install {dest}
```

## 工具列表
- `{name}_hello` — 示例

## 开发
编辑 `tools.py` 添加工具函数，同步更新 `schemas.json` 和 `TOOLS_MAP`。
""", encoding="utf-8")

        # requirements.txt（空）
        (dest / "requirements.txt").write_text("# 在此添加 Python 依赖\n", encoding="utf-8")

        return {
            "success": True,
            "name": name,
            "path": str(dest),
            "message": f"模板已创建: {dest}\n编辑 tools.py 添加工具，schemas.json 添加 Schema",
            "files": [str(f.relative_to(dest)) for f in dest.iterdir()],
        }

    # ── 导出技能为 .zip ─────────────────────────────────────

    def export(self, name: str, output_dir: str = None) -> dict:
        """导出技能为 .zip 分享包"""
        skill_dir = SKILLS_DIR / name
        if not skill_dir.exists():
            skill_dir = DISABLED_DIR / name
        if not skill_dir.exists():
            return {"success": False, "message": f"技能不存在: {name}"}

        out_dir = Path(output_dir or ".").resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        zip_name = f"gary_skill_{name}.zip"
        zip_path = out_dir / zip_name

        with zipfile.ZipFile(str(zip_path), 'w', zipfile.ZIP_DEFLATED) as zf:
            for fp in skill_dir.rglob("*"):
                if fp.is_file() and "__pycache__" not in str(fp):
                    zf.write(str(fp), str(fp.relative_to(skill_dir.parent)))

        size_kb = zip_path.stat().st_size / 1024
        return {
            "success": True,
            "path": str(zip_path),
            "size_kb": round(size_kb, 1),
            "message": f"已导出: {zip_path} ({size_kb:.1f} KB)",
        }

    # ── 重新加载 ────────────────────────────────────────────

    def reload_all(self) -> dict:
        """重新加载所有技能"""
        old_count = len(self._skills)
        self._skills.clear()

        # 清除已加载的 module 缓存
        to_remove = [k for k in sys.modules if k.startswith("gary_skill_")]
        for k in to_remove:
            del sys.modules[k]

        loaded = self.load_all()
        return {
            "success": True,
            "loaded": len(loaded),
            "message": f"已重新加载 {len(loaded)} 个技能（之前 {old_count} 个）",
        }


# ─────────────────────────────────────────────────────────────
# 给 stm32_agent.py 用的工具函数
# ─────────────────────────────────────────────────────────────

_manager: Optional[SkillsManager] = None

def _get_manager() -> SkillsManager:
    global _manager
    if _manager is None:
        _manager = SkillsManager()
    return _manager


def skill_list() -> dict:
    """列出所有已安装的技能包"""
    return _get_manager().list_skills()

def skill_install(source: str) -> dict:
    """
    安装技能包。支持：本地目录、.zip、.py 单文件、Git URL。
    安装后自动加载并注册工具。
    """
    return _get_manager().install(source)

def skill_uninstall(name: str) -> dict:
    """卸载技能包（删除文件）"""
    return _get_manager().uninstall(name)

def skill_enable(name: str) -> dict:
    """启用已禁用的技能"""
    return _get_manager().enable(name)

def skill_disable(name: str) -> dict:
    """禁用技能（保留文件，不加载）"""
    return _get_manager().disable(name)

def skill_info(name: str) -> dict:
    """查看技能详细信息"""
    return _get_manager().info(name)

def skill_create(name: str, description: str = "") -> dict:
    """创建新技能的标准模板目录"""
    return _get_manager().create_template(name, description)

def skill_export(name: str, output_dir: str = None) -> dict:
    """导出技能为 .zip 文件，方便分享"""
    return _get_manager().export(name, output_dir)

def skill_reload() -> dict:
    """重新加载所有技能（修改 tools.py 后使用）"""
    return _get_manager().reload_all()


# ── 工具注册表 ───────────────────────────────────────────────

SKILL_TOOLS_MAP = {
    "skill_list":      skill_list,
    "skill_install":   skill_install,
    "skill_uninstall": skill_uninstall,
    "skill_enable":    skill_enable,
    "skill_disable":   skill_disable,
    "skill_info":      skill_info,
    "skill_create":    skill_create,
    "skill_export":    skill_export,
    "skill_reload":    skill_reload,
}

SKILL_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "skill_list",
            "description": "列出所有已安装的 Gary 技能包（含已禁用的）",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "skill_install",
            "description": (
                "安装技能包到 Gary。支持：本地目录路径、.zip 压缩包、.py 单文件（自动包装）、Git 仓库 URL。"
                "安装后自动加载工具和 AI 提示词。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "技能来源：目录路径 / .zip 路径 / .py 文件 / Git URL"},
                },
                "required": ["source"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "skill_uninstall",
            "description": "卸载技能包（删除文件和注册信息）",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "技能名称"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "skill_enable",
            "description": "启用已禁用的技能",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "skill_disable",
            "description": "禁用技能（保留文件但不加载，节省资源）",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "skill_info",
            "description": "查看技能详情：版本、作者、工具列表、提示词预览",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "skill_create",
            "description": "创建新技能的标准模板目录，包含 skill.json / tools.py / schemas.json / prompt.md",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "技能名称（英文下划线）"},
                    "description": {"type": "string", "description": "技能描述"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "skill_export",
            "description": "导出技能为 .zip 文件，方便分享给其他用户",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "技能名称"},
                    "output_dir": {"type": "string", "description": "输出目录（默认当前目录）"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "skill_reload",
            "description": "重新加载所有技能（修改了 tools.py 后使用）",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


# ─────────────────────────────────────────────────────────────
# CLI 命令处理（供 stm32_agent.py 的 handle_builtin 调用）
# ─────────────────────────────────────────────────────────────

def handle_skill_command(args: str, agent=None) -> bool:
    """
    处理 /skill 命令。在 stm32_agent.py 的 handle_builtin 中调用：

        if head == "/skill":
            from gary_skills import handle_skill_command
            handle_skill_command(arg, agent=self)
            return True
    """
    parts = args.strip().split(None, 1)
    subcmd = parts[0].lower() if parts else "list"
    subarg = parts[1].strip() if len(parts) > 1 else ""

    mgr = _get_manager()

    # ── /skill list ──────────────────────────────────────────
    if subcmd in ("list", "ls", ""):
        r = mgr.list_skills()
        if not r["skills"]:
            CONSOLE.print("[dim]  暂无已安装技能[/]")
            CONSOLE.print(f"[dim]  技能目录: {SKILLS_DIR}[/]")
            CONSOLE.print(f"[dim]  安装: /skill install <路径/URL>[/]")
        else:
            try:
                table = Table(title="已安装技能", box=box.SIMPLE)
                table.add_column("名称", style="bold cyan")
                table.add_column("版本", style="dim")
                table.add_column("工具数", style="green")
                table.add_column("状态", style="white")
                table.add_column("描述", style="dim")
                for s in r["skills"]:
                    status = "[green]●[/]" if s["enabled"] else "[dim]○ 禁用[/]"
                    if s.get("error"):
                        status = f"[yellow]⚠ {s['error'][:30]}[/]"
                    table.add_row(
                        s["display_name"],
                        s["version"],
                        str(s["tools_count"]) if s["enabled"] else "-",
                        status,
                        s["description"][:40],
                    )
                CONSOLE.print(table)
            except Exception:
                for s in r["skills"]:
                    flag = "●" if s["enabled"] else "○"
                    CONSOLE.print(f"  {flag} {s['display_name']} v{s['version']} ({s['tools_count']} tools)")
        CONSOLE.print()
        return True

    # ── /skill install <source> ──────────────────────────────
    if subcmd == "install":
        if not subarg:
            CONSOLE.print("[yellow]  用法: /skill install <目录/zip/py/URL>[/]\n")
            return True
        CONSOLE.print(f"[dim]  安装: {subarg}[/]")
        r = mgr.install(subarg)
        color = "green" if r["success"] else "red"
        CONSOLE.print(f"[{color}]  {r['message']}[/]\n")

        # 安装成功后热注册到 agent
        if r["success"] and agent is not None:
            _hot_reload_agent(agent, mgr)
        return True

    # ── /skill uninstall <name> ──────────────────────────────
    if subcmd in ("uninstall", "remove", "rm"):
        if not subarg:
            CONSOLE.print("[yellow]  用法: /skill uninstall <名称>[/]\n")
            return True
        r = mgr.uninstall(subarg)
        color = "green" if r["success"] else "red"
        CONSOLE.print(f"[{color}]  {r['message']}[/]\n")
        if r["success"] and agent is not None:
            _hot_reload_agent(agent, mgr)
        return True

    # ── /skill enable/disable ────────────────────────────────
    if subcmd == "enable":
        r = mgr.enable(subarg)
        CONSOLE.print(f"[{'green' if r['success'] else 'red'}]  {r['message']}[/]\n")
        if r["success"] and agent is not None:
            _hot_reload_agent(agent, mgr)
        return True

    if subcmd == "disable":
        r = mgr.disable(subarg)
        CONSOLE.print(f"[{'green' if r['success'] else 'red'}]  {r['message']}[/]\n")
        if r["success"] and agent is not None:
            _hot_reload_agent(agent, mgr)
        return True

    # ── /skill info <name> ───────────────────────────────────
    if subcmd == "info":
        r = mgr.info(subarg)
        if r["success"]:
            meta = r["meta"]
            CONSOLE.print(f"  [bold cyan]{meta.get('display_name', meta.get('name'))}[/] v{meta.get('version')}")
            CONSOLE.print(f"  [dim]作者:[/] {meta.get('author', '未知')}")
            CONSOLE.print(f"  [dim]描述:[/] {meta.get('description', '')}")
            CONSOLE.print(f"  [dim]标签:[/] {', '.join(meta.get('tags', []))}")
            if "tools" in r:
                CONSOLE.print(f"  [dim]工具:[/] {', '.join(r['tools'])}")
            CONSOLE.print(f"  [dim]路径:[/] {r.get('path', '')}")
            if r.get("prompt_preview"):
                CONSOLE.print(f"  [dim]提示词预览:[/] {r['prompt_preview'][:100]}...")
        else:
            CONSOLE.print(f"[red]  {r['message']}[/]")
        CONSOLE.print()
        return True

    # ── /skill create <name> ─────────────────────────────────
    if subcmd in ("create", "new"):
        if not subarg:
            CONSOLE.print("[yellow]  用法: /skill create <名称> [描述][/]\n")
            return True
        parts2 = subarg.split(None, 1)
        name = parts2[0]
        desc = parts2[1] if len(parts2) > 1 else ""
        r = mgr.create_template(name, desc)
        color = "green" if r["success"] else "red"
        CONSOLE.print(f"[{color}]  {r['message']}[/]\n")
        return True

    # ── /skill export <name> ─────────────────────────────────
    if subcmd == "export":
        if not subarg:
            CONSOLE.print("[yellow]  用法: /skill export <名称>[/]\n")
            return True
        r = mgr.export(subarg)
        color = "green" if r["success"] else "red"
        CONSOLE.print(f"[{color}]  {r['message']}[/]\n")
        return True

    # ── /skill reload ────────────────────────────────────────
    if subcmd == "reload":
        r = mgr.reload_all()
        CONSOLE.print(f"[green]  {r['message']}[/]\n")
        if agent is not None:
            _hot_reload_agent(agent, mgr)
        return True

    # ── /skill dir ───────────────────────────────────────────
    if subcmd == "dir":
        CONSOLE.print(f"  技能目录: {SKILLS_DIR}")
        CONSOLE.print(f"  禁用目录: {DISABLED_DIR}\n")
        return True

    # 未知子命令
    CONSOLE.print(f"[yellow]  未知命令: /skill {subcmd}[/]")
    CONSOLE.print("  可用: list | install | uninstall | enable | disable | info | create | export | reload | dir\n")
    return True


def _hot_reload_agent(agent, mgr: SkillsManager):
    """安装/卸载后热更新 agent 的工具和提示词"""
    try:
        # 动态获取 stm32_agent 模块中的 TOOLS_MAP 和 TOOL_SCHEMAS
        import stm32_agent as sa

        # 移除旧 skill 工具（以 skill_ 前缀或在某个 skill 注册表中的）
        # 简单策略：重建
        extra_tools = mgr.get_all_tools_map()
        extra_schemas = mgr.get_all_tool_schemas()
        prompt_add = mgr.get_all_prompt_additions()

        # 注册工具
        sa.TOOLS_MAP.update(extra_tools)

        # 去重后追加 schema
        existing_names = {s["function"]["name"] for s in sa.TOOL_SCHEMAS if "function" in s}
        for schema in extra_schemas:
            fname = schema.get("function", {}).get("name", "")
            if fname and fname not in existing_names:
                sa.TOOL_SCHEMAS.append(schema)
                existing_names.add(fname)

        CONSOLE.print(f"[dim]  已热注册 {len(extra_tools)} 个工具[/]")

    except Exception as e:
        CONSOLE.print(f"[yellow]  热重载失败（重启生效）: {e}[/]")


# ─────────────────────────────────────────────────────────────
# 集成函数（在 stm32_agent.py 中调用一次即可）
# ─────────────────────────────────────────────────────────────

def init_skills(tools_map: dict = None, tool_schemas: list = None) -> SkillsManager:
    """
    初始化技能系统。在 stm32_agent.py 启动时调用：

    ```python
    from gary_skills import init_skills, SKILL_TOOLS_MAP, SKILL_TOOL_SCHEMAS, handle_skill_command

    # 注册 skill 管理工具本身
    TOOLS_MAP.update(SKILL_TOOLS_MAP)
    TOOL_SCHEMAS.extend(SKILL_TOOL_SCHEMAS)

    # 加载所有已安装的 skill
    skill_mgr = init_skills(TOOLS_MAP, TOOL_SCHEMAS)

    # 将 skill 的 prompt 追加到 SYSTEM_PROMPT
    STM32_SYSTEM_PROMPT += skill_mgr.get_all_prompt_additions()
    ```
    """
    mgr = _get_manager()
    CONSOLE.print("[dim]  加载技能包...[/]")
    mgr.load_all()

    if tools_map is not None:
        tools_map.update(mgr.get_all_tools_map())
    if tool_schemas is not None:
        existing = {s["function"]["name"] for s in tool_schemas if "function" in s}
        for schema in mgr.get_all_tool_schemas():
            fname = schema.get("function", {}).get("name", "")
            if fname and fname not in existing:
                tool_schemas.append(schema)
                existing.add(fname)

    return mgr


# ─────────────────────────────────────────────────────────────
# 独立运行
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Gary Skills Manager")
    parser.add_argument("action", nargs="?", default="list",
                        choices=["list", "install", "uninstall", "enable", "disable",
                                 "info", "create", "export", "reload", "dir"],
                        help="操作")
    parser.add_argument("target", nargs="?", default="", help="目标名称/路径")
    parser.add_argument("-d", "--description", default="", help="描述（create 时使用）")
    args = parser.parse_args()

    mgr = _get_manager()
    mgr.load_all()

    if args.action == "list":
        r = mgr.list_skills()
        print(f"\n已安装 {r['total']} 个技能:\n")
        for s in r["skills"]:
            flag = "●" if s["enabled"] else "○"
            print(f"  {flag} {s['display_name']:<24} v{s['version']:<8} {s['tools_count']} tools  {s['description'][:40]}")
        print(f"\n技能目录: {SKILLS_DIR}\n")

    elif args.action == "install":
        if not args.target:
            print("用法: gary_skills.py install <路径/URL>")
            sys.exit(1)
        r = mgr.install(args.target)
        print(r["message"])

    elif args.action == "uninstall":
        r = mgr.uninstall(args.target)
        print(r["message"])

    elif args.action == "enable":
        r = mgr.enable(args.target)
        print(r["message"])

    elif args.action == "disable":
        r = mgr.disable(args.target)
        print(r["message"])

    elif args.action == "info":
        r = mgr.info(args.target)
        if r["success"]:
            print(json.dumps(r["meta"], indent=2, ensure_ascii=False))
        else:
            print(r["message"])

    elif args.action == "create":
        r = mgr.create_template(args.target, args.description)
        print(r["message"])

    elif args.action == "export":
        r = mgr.export(args.target)
        print(r["message"])

    elif args.action == "reload":
        r = mgr.reload_all()
        print(r["message"])

    elif args.action == "dir":
        print(f"技能目录: {SKILLS_DIR}")
        print(f"禁用目录: {DISABLED_DIR}")

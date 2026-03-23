"""
Shared pytest fixtures for Gary CLI test suite.
"""

import json
import pytest


@pytest.fixture
def tmp_gary_home(tmp_path):
    """Create a temporary ~/.gary directory structure for testing."""
    gary_home = tmp_path / ".gary"
    (gary_home / "skills").mkdir(parents=True)
    (gary_home / "projects").mkdir(parents=True)
    (gary_home / "templates").mkdir(parents=True)
    return gary_home


@pytest.fixture
def sample_config(tmp_path):
    """Create a minimal valid config file."""
    config = {
        "api_key": "sk-test-key-for-unit-tests",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "chip": "STM32F103C8T6",
    }
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(config, indent=2))
    return config_file


@pytest.fixture
def sample_skill_dir(tmp_path):
    """Create a minimal valid Skill directory."""
    skill_dir = tmp_path / "test_skill"
    skill_dir.mkdir()

    skill_json = {
        "name": "test_skill",
        "version": "1.0.0",
        "description": "Test skill fixture",
        "author": "pytest",
        "tags": ["test"],
        "gary_min_version": "0.1.0",
    }
    (skill_dir / "skill.json").write_text(json.dumps(skill_json, indent=2))

    tools_py = '''
def test_tool(param: str) -> dict:
    """A test tool — returns the param back."""
    return {"success": True, "result": param}

TOOLS_MAP = {"test_tool": test_tool}
'''
    (skill_dir / "tools.py").write_text(tools_py)

    schemas = [
        {
            "type": "function",
            "function": {
                "name": "test_tool",
                "description": "A test tool for unit testing",
                "parameters": {
                    "type": "object",
                    "properties": {"param": {"type": "string", "description": "Input param"}},
                    "required": ["param"],
                },
            },
        }
    ]
    (skill_dir / "schemas.json").write_text(json.dumps(schemas, indent=2))
    (skill_dir / "prompt.md").write_text("## Test Skill\nUse test_tool when testing.\n")

    return skill_dir

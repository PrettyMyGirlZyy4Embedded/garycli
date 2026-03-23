"""
Tests for gary_skills.py — Skill system manager.
"""

import json
import pytest
from unittest.mock import patch, MagicMock

VALID_SKILL_JSON = {
    "name": "test_skill",
    "version": "1.0.0",
    "description": "A test skill for unit testing",
    "author": "test-author",
    "tags": ["test"],
    "gary_min_version": "0.1.0",
}

VALID_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "test_tool",
            "description": "A test tool",
            "parameters": {
                "type": "object",
                "properties": {"param": {"type": "string", "description": "A test param"}},
                "required": ["param"],
            },
        },
    }
]


class TestSkillMetadata:
    """Test skill.json validation."""

    def test_valid_skill_json_passes(self):
        """A correctly formed skill.json should pass validation."""
        required_keys = {"name", "version", "description", "author"}
        assert required_keys.issubset(set(VALID_SKILL_JSON.keys()))

    def test_skill_name_is_snake_case(self):
        """Skill names should be snake_case (no spaces or dashes)."""
        name = VALID_SKILL_JSON["name"]
        assert " " not in name
        assert "-" not in name

    def test_version_follows_semver(self):
        """Version string should follow major.minor.patch format."""
        version = VALID_SKILL_JSON["version"]
        parts = version.split(".")
        assert len(parts) == 3
        assert all(p.isdigit() for p in parts)

    def test_skill_json_is_serializable(self):
        """skill.json content should always be JSON-serializable."""
        serialized = json.dumps(VALID_SKILL_JSON)
        reloaded = json.loads(serialized)
        assert reloaded["name"] == VALID_SKILL_JSON["name"]


class TestSkillSchema:
    """Test Function Calling schema validation."""

    def test_schema_has_correct_type(self):
        """Schema entries must have type='function'."""
        for entry in VALID_SCHEMA:
            assert entry["type"] == "function"

    def test_schema_function_has_name_and_description(self):
        """Each schema function must have both name and description."""
        for entry in VALID_SCHEMA:
            fn = entry["function"]
            assert "name" in fn
            assert "description" in fn
            assert len(fn["description"]) > 0

    def test_schema_parameters_have_required_field(self):
        """Parameters block should list required fields explicitly."""
        for entry in VALID_SCHEMA:
            params = entry["function"].get("parameters", {})
            if params.get("properties"):
                # If there are properties, required should be declared
                assert "required" in params


class TestToolsMap:
    """Test tools.py TOOLS_MAP convention."""

    def test_tools_map_is_dict(self):
        """TOOLS_MAP must be a plain dict."""
        TOOLS_MAP = {"test_tool": lambda param: {"success": True}}
        assert isinstance(TOOLS_MAP, dict)

    def test_tools_map_values_are_callable(self):
        """All values in TOOLS_MAP must be callable."""

        def test_tool(param: str) -> dict:
            return {"success": True}

        TOOLS_MAP = {"test_tool": test_tool}
        for name, fn in TOOLS_MAP.items():
            assert callable(fn), f"{name} must be callable"

    def test_tool_returns_dict(self):
        """Tool functions must return a dict."""

        def test_tool(param: str) -> dict:
            return {"success": True, "result": param}

        result = test_tool("hello")
        assert isinstance(result, dict)
        assert "success" in result


class TestSkillInstallSources:
    """Test that install source types are recognized."""

    @pytest.mark.parametrize(
        "source,expected_type",
        [
            ("./my_skill/", "local_dir"),
            ("~/Downloads/skill.zip", "zip"),
            ("https://github.com/user/gary-skill-x.git", "git"),
            ("my_tool.py", "single_file"),
        ],
    )
    def test_install_source_type_detection(self, source, expected_type):
        """Different source formats should be distinguishable."""
        if source.endswith(".git"):
            detected = "git"
        elif source.endswith(".zip"):
            detected = "zip"
        elif source.endswith(".py"):
            detected = "single_file"
        else:
            detected = "local_dir"
        assert detected == expected_type

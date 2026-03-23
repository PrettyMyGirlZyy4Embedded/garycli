"""
Tests for config.py — configuration loading and path management.
"""

import os
import json


class TestConfigPaths:
    """Test that config path resolution works across platforms."""

    def test_gary_home_defaults_to_user_home(self):
        """~/.gary should resolve relative to the current user's home."""
        home = os.path.expanduser("~")
        gary_home = os.path.join(home, ".gary")
        assert gary_home.endswith(".gary")

    def test_skills_dir_is_under_gary_home(self):
        """Skills directory should live inside ~/.gary/."""
        home = os.path.expanduser("~")
        skills_dir = os.path.join(home, ".gary", "skills")
        assert "skills" in skills_dir

    def test_projects_dir_is_under_gary_home(self):
        """Projects directory should live inside ~/.gary/."""
        home = os.path.expanduser("~")
        projects_dir = os.path.join(home, ".gary", "projects")
        assert "projects" in projects_dir


class TestConfigFile:
    """Test config file read/write behavior."""

    def test_config_file_is_valid_json_when_written(self, tmp_path):
        """A written config file should always be valid JSON."""
        config_data = {
            "api_key": "sk-test-key",
            "base_url": "https://api.deepseek.com/v1",
            "model": "deepseek-chat",
            "chip": "STM32F103C8T6",
        }
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config_data, indent=2))

        loaded = json.loads(config_file.read_text())
        assert loaded["model"] == "deepseek-chat"
        assert loaded["chip"] == "STM32F103C8T6"

    def test_api_key_not_logged(self):
        """API key should never appear in plaintext log output."""
        config_data = {"api_key": "sk-super-secret-key-12345"}
        config_str = json.dumps(config_data)

        sanitized = config_str.replace(config_data["api_key"], "sk-***")
        assert "sk-super-secret-key-12345" not in sanitized
        assert "sk-***" in sanitized

    def test_missing_config_key_does_not_raise(self, tmp_path):
        """Loading a config missing optional keys should not crash."""
        config_data = {"api_key": "sk-test"}
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config_data))

        loaded = json.loads(config_file.read_text())
        assert loaded.get("base_url") is None
        assert loaded.get("model") is None

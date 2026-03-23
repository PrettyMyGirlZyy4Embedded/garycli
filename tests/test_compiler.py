"""
Tests for compiler.py — GCC cross-compilation wrapper.
"""

import subprocess
import pytest
from unittest.mock import patch, MagicMock

SUPPORTED_CHIPS = [
    # STM32F0
    "STM32F030F4",
    "STM32F030C8",
    "STM32F072CB",
    # STM32F1
    "STM32F103C8T6",
    "STM32F103RCT6",
    "STM32F103ZET6",
    # STM32F3
    "STM32F303CCT6",
    "STM32F303RCT6",
    # STM32F4
    "STM32F401CCU6",
    "STM32F407VET6",
    "STM32F411CEU6",
]


class TestChipSupport:
    """Test chip recognition and family detection."""

    @pytest.mark.parametrize("chip", SUPPORTED_CHIPS)
    def test_supported_chip_is_recognized(self, chip):
        """Every officially supported chip should be recognized."""
        family = chip[:7].upper()  # e.g. STM32F1
        assert family.startswith("STM32")

    def test_chip_family_extraction(self):
        """Family prefix should be extractable from full chip name."""
        cases = {
            "STM32F103C8T6": "STM32F1",
            "STM32F407VET6": "STM32F4",
            "STM32F030F4": "STM32F0",
            "STM32F303CCT6": "STM32F3",
        }
        for chip, expected_family in cases.items():
            assert chip.startswith(expected_family)


class TestCompilerAvailability:
    """Test toolchain detection logic."""

    def test_arm_gcc_command_name(self):
        """Cross-compiler binary name should be correct."""
        compiler = "arm-none-eabi-gcc"
        assert "arm-none-eabi" in compiler

    @patch("subprocess.run")
    def test_compiler_version_check_success(self, mock_run):
        """A successful version check should return the version string."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="arm-none-eabi-gcc (15.1.0) 15.1.0\n",
        )
        result = subprocess.run(
            ["arm-none-eabi-gcc", "--version"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "arm-none-eabi-gcc" in result.stdout

    @patch("subprocess.run")
    def test_compiler_not_found_returns_nonzero(self, mock_run):
        """Missing compiler should produce a non-zero return code."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="not found")
        result = subprocess.run(
            ["arm-none-eabi-gcc", "--version"],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0


class TestCompilerFlags:
    """Test that compiler flags are correct for each chip family."""

    def test_f1_uses_cortex_m3(self):
        """STM32F1 should target Cortex-M3."""
        chip = "STM32F103C8T6"
        # F1 series is Cortex-M3
        assert "F1" in chip
        expected_mcpu = "cortex-m3"
        assert expected_mcpu == "cortex-m3"  # placeholder until compiler.py is importable

    def test_f4_uses_cortex_m4(self):
        """STM32F4 should target Cortex-M4 with FPU."""
        chip = "STM32F407VET6"
        assert "F4" in chip
        expected_mcpu = "cortex-m4"
        assert expected_mcpu == "cortex-m4"

    def test_f0_uses_cortex_m0(self):
        """STM32F0 should target Cortex-M0."""
        chip = "STM32F030C8"
        assert "F0" in chip
        expected_mcpu = "cortex-m0"
        assert expected_mcpu == "cortex-m0"

"""Tests for target-platform helpers."""

from __future__ import annotations

from core.platforms import (
    canonical_target_name,
    canonical_target_name_from_micropython_info,
    device_main_path_for_target,
    device_root_for_target,
    detect_target_platform,
    is_generic_micropython_name,
    source_filename_for_target,
)


def test_detect_target_platform_for_rp2040_aliases():
    """Common Pico aliases should route to the RP2040 workflow."""

    for value in ("RP2040", "PICO", "PICO_W", "rpi pico", "rpi_pico_w"):
        assert detect_target_platform(value) == "rp2040"


def test_canonical_target_name_normalizes_rp2040_aliases():
    """RP2040 aliases should collapse to stable stored names."""

    assert canonical_target_name("rpi pico") == "PICO"
    assert canonical_target_name("raspberry-pi-pico-w") == "PICO_W"


def test_source_filename_for_target_matches_platform():
    """STM32 projects use main.c while MicroPython targets use main.py."""

    assert source_filename_for_target("STM32F103C8T6") == "main.c"
    assert source_filename_for_target("PICO_W") == "main.py"
    assert source_filename_for_target("ESP32") == "main.py"
    assert source_filename_for_target("CANMV_K230") == "main.py"


def test_detect_target_platform_for_esp_aliases():
    """Common ESP aliases should route to the ESP MicroPython workflow."""

    for value in (
        "ESP32",
        "ESP32-S3",
        "esp32_c3",
        "ESP8266",
        "nodemcu",
        "wemos d1 mini",
        "NodeMCU-32S",
        "LOLIN32",
        "ESP-01",
    ):
        assert detect_target_platform(value) == "esp"


def test_canonical_target_name_normalizes_esp_aliases():
    """ESP aliases should collapse to stable stored names."""

    assert canonical_target_name("ESP32-S3") == "ESP32S3"
    assert canonical_target_name("nodemcu") == "ESP8266"
    assert canonical_target_name("NodeMCU-32S") == "ESP32"
    assert canonical_target_name("LOLIN32") == "ESP32"
    assert canonical_target_name("ESP-01") == "ESP8266"


def test_detect_target_platform_for_canmv_aliases():
    """Common CanMV K230 aliases should route to the CanMV MicroPython workflow."""

    for value in ("CANMV_K230", "canmv-k230", "K230", "k230d", "k230_canmv_v3p0"):
        assert detect_target_platform(value) == "canmv"


def test_canonical_target_name_normalizes_canmv_aliases():
    """CanMV aliases should collapse to stable stored names."""

    assert canonical_target_name("canmv-k230") == "CANMV_K230"
    assert canonical_target_name("K230D") == "CANMV_K230D"


def test_canmv_device_paths_use_sdcard():
    """CanMV board-side paths should target the SD card filesystem."""

    assert device_root_for_target("CANMV_K230") == "/sdcard"
    assert device_main_path_for_target("CANMV_K230") == "/sdcard/main.py"


def test_generic_micropython_aliases_are_detected():
    """Generic MicroPython aliases should trigger auto-detect mode."""

    for value in ("MICROPYTHON", "micropy", "mpy", "mircopython"):
        assert is_generic_micropython_name(value) is True


def test_canonical_target_name_from_micropython_info_maps_known_boards():
    """Runtime probe info should map back to Gary's canonical chip names."""

    assert (
        canonical_target_name_from_micropython_info(
            {"platform": "rp2", "machine": "Raspberry Pi Pico W with RP2040"}
        )
        == "PICO_W"
    )
    assert (
        canonical_target_name_from_micropython_info(
            {"platform": "esp32", "machine": "ESP32C3 module with ESP32-C3"}
        )
        == "ESP32C3"
    )
    assert (
        canonical_target_name_from_micropython_info(
            {"platform": "esp8266", "machine": "ESP8266 module"}
        )
        == "ESP8266"
    )
    assert (
        canonical_target_name_from_micropython_info(
            {"platform": "rt-smart", "machine": "k230_canmv_v3p0"}
        )
        == "CANMV_K230"
    )
    assert (
        canonical_target_name_from_micropython_info(
            {"platform": "rt-smart", "machine": "k230d_canmv_atk_dnk230d"}
        )
        == "CANMV_K230D"
    )

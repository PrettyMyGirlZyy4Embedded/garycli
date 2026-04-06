"""Target-platform detection and naming helpers."""

from __future__ import annotations

import re

RP2040_TARGET_CHOICES = (
    "RP2040",
    "PICO",
    "PICO_W",
    "RPI_PICO",
    "RPI_PICO_W",
    "RASPBERRY_PI_PICO",
    "RASPBERRY_PI_PICO_W",
)
MICROPYTHON_TARGET_CHOICES = (
    "MICROPYTHON",
    "MICROPY",
    "MPY",
    "MIRCOPYTHON",
)
ESP_TARGET_CHOICES = (
    "ESP32",
    "ESP32-DEVKITC",
    "NODEMCU-32S",
    "LOLIN32",
    "LOLIN-D32",
    "WROOM32",
    "ESP32S2",
    "ESP32_S2",
    "ESP32-S2",
    "ESP32S3",
    "ESP32_S3",
    "ESP32-S3",
    "ESP32C3",
    "ESP32_C3",
    "ESP32-C3",
    "ESP32C6",
    "ESP32_C6",
    "ESP32-C6",
    "ESP8266",
    "NODEMCU",
    "D1_MINI",
    "D1-MINI",
    "WEMOS_D1_MINI",
    "WEMOS-D1-MINI",
    "ESP-01",
    "ESP_01",
    "ESP12E",
    "ESP12F",
)
CANMV_TARGET_CHOICES = (
    "CANMV_K230",
    "CANMV-K230",
    "K230",
    "K230_CANMV",
    "K230-CANMV",
    "CANMV_K230D",
    "CANMV-K230D",
    "K230D",
    "K230D_CANMV",
    "K230D-CANMV",
)


def normalize_target_name(value: str | None) -> str:
    """Normalize a user-provided target name for matching."""

    text = re.sub(r"[\s\-]+", "_", str(value or "").strip().upper())
    text = re.sub(r"_+", "_", text).strip("_")
    return text


def detect_target_platform(chip: str | None) -> str:
    """Return the platform identifier for the selected target."""

    name = normalize_target_name(chip)
    if not name:
        return "stm32"
    if name in MICROPYTHON_TARGET_CHOICES:
        return "unknown"
    if "RP2350" in name or "PICO2" in name:
        return "unknown"
    if "RP2040" in name:
        return "rp2040"
    if name in RP2040_TARGET_CHOICES or name.startswith("PICO_") or name == "PICO":
        return "rp2040"
    if "ESP32" in name or "ESP8266" in name:
        return "esp"
    if (
        name in ESP_TARGET_CHOICES
        or name.startswith("NODEMCU")
        or name.startswith("WEMOS")
        or name.startswith("LOLIN")
        or name.startswith("WROOM32")
        or name.startswith("ESP32_DEVKIT")
        or name.startswith("ESP01")
        or name.startswith("ESP_01")
        or name.startswith("ESP12")
    ):
        return "esp"
    if (
        name in CANMV_TARGET_CHOICES
        or "K230" in name
        or name.startswith("CANMV_K230")
        or name.startswith("CANMV_K230D")
    ):
        return "canmv"
    if name.startswith("STM32"):
        return "stm32"
    return "unknown"


def is_rp2040_target(chip: str | None) -> bool:
    """Return whether the selected target is handled by the RP2040 workflow."""

    return detect_target_platform(chip) == "rp2040"


def is_esp_target(chip: str | None) -> bool:
    """Return whether the selected target is handled by the ESP MicroPython workflow."""

    return detect_target_platform(chip) == "esp"


def is_micropython_target(chip: str | None) -> bool:
    """Return whether the selected target uses the serial MicroPython workflow."""

    return detect_target_platform(chip) in {"rp2040", "esp", "canmv"}


def is_canmv_target(chip: str | None) -> bool:
    """Return whether the selected target uses the CanMV K230 workflow."""

    return detect_target_platform(chip) == "canmv"


def is_generic_micropython_name(chip: str | None) -> bool:
    """Return whether the input asks Gary to auto-detect a MicroPython board."""

    return normalize_target_name(chip) in MICROPYTHON_TARGET_CHOICES


def canonical_target_name(chip: str | None) -> str:
    """Return a stable display / storage name for the selected target."""

    name = normalize_target_name(chip)
    if name in MICROPYTHON_TARGET_CHOICES:
        return "MICROPYTHON"
    platform = detect_target_platform(name)
    if platform == "rp2040":
        if name in {"PICO_W", "RPI_PICO_W", "RASPBERRY_PI_PICO_W"}:
            return "PICO_W"
        if name in {"PICO", "RPI_PICO", "RASPBERRY_PI_PICO"}:
            return "PICO"
        return "RP2040"
    if platform == "esp":
        if name in {
            "NODEMCU",
            "D1_MINI",
            "WEMOS_D1_MINI",
            "ESP01",
            "ESP_01",
            "ESP12E",
            "ESP12F",
        }:
            return "ESP8266"
        if name in {"ESP32_DEVKITC", "NODEMCU_32S", "LOLIN32", "LOLIN_D32", "WROOM32"}:
            return "ESP32"
        if name in {"ESP32_S2", "ESP32S2"}:
            return "ESP32S2"
        if name in {"ESP32_S3", "ESP32S3"}:
            return "ESP32S3"
        if name in {"ESP32_C3", "ESP32C3"}:
            return "ESP32C3"
        if name in {"ESP32_C6", "ESP32C6"}:
            return "ESP32C6"
        if name == "ESP8266":
            return "ESP8266"
        return "ESP32"
    if platform == "canmv":
        return "CANMV_K230D" if "K230D" in name else "CANMV_K230"
    return name or "STM32F103C8T6"


def canonical_target_name_from_micropython_info(info: dict[str, str] | None) -> str | None:
    """Infer Gary's canonical chip name from MicroPython runtime probe info."""

    data = info or {}
    fields = [
        str(data.get("platform") or ""),
        str(data.get("machine") or ""),
        str(data.get("sysname") or ""),
        str(data.get("release") or ""),
        str(data.get("version") or ""),
    ]
    text = " ".join(fields).strip().lower()
    compact = re.sub(r"[\s_\-]+", "", text)

    if "pico w" in text or "picow" in compact:
        return "PICO_W"
    if "raspberry pi pico" in text or " pico" in text or compact.startswith("pico"):
        return "PICO"
    if "rp2040" in compact or str(data.get("platform") or "").strip().lower() == "rp2":
        return "RP2040"

    esp_patterns = (
        ("ESP32C6", ("esp32-c6", "esp32 c6", "esp32c6")),
        ("ESP32C3", ("esp32-c3", "esp32 c3", "esp32c3")),
        ("ESP32S3", ("esp32-s3", "esp32 s3", "esp32s3")),
        ("ESP32S2", ("esp32-s2", "esp32 s2", "esp32s2")),
        ("ESP8266", ("esp8266", "nodemcu", "d1 mini", "wemos d1")),
        ("ESP32", ("esp32", "lolin32", "nodemcu-32s", "wroom32")),
    )
    for chip_name, patterns in esp_patterns:
        if any(pattern in text or pattern.replace("-", "").replace(" ", "") in compact for pattern in patterns):
            return chip_name
    if "k230d" in compact:
        return "CANMV_K230D"
    if "k230" in compact and ("canmv" in compact or str(data.get("platform") or "").strip().lower() == "rt-smart"):
        return "CANMV_K230"
    return None


def source_filename_for_target(chip: str | None) -> str:
    """Return the canonical source filename for the current platform."""

    return "main.py" if is_micropython_target(chip) else "main.c"


def device_root_for_target(chip: str | None) -> str:
    """Return the preferred writable device root for the selected target."""

    return "/sdcard" if is_canmv_target(chip) else "."


def device_main_path_for_target(chip: str | None) -> str:
    """Return the on-device path used for the deployed startup script."""

    if is_canmv_target(chip):
        return "/sdcard/main.py"
    return "main.py"


def target_runtime_label(chip: str | None) -> str:
    """Return a short runtime label for UI and tool status."""

    platform = detect_target_platform(chip)
    if platform == "canmv":
        return "CanMV MicroPython"
    if platform in {"rp2040", "esp"}:
        return "MicroPython"
    if platform == "stm32":
        return "STM32 HAL"
    return "Unknown"


__all__ = [
    "CANMV_TARGET_CHOICES",
    "MICROPYTHON_TARGET_CHOICES",
    "ESP_TARGET_CHOICES",
    "RP2040_TARGET_CHOICES",
    "canonical_target_name_from_micropython_info",
    "canonical_target_name",
    "device_main_path_for_target",
    "device_root_for_target",
    "detect_target_platform",
    "is_generic_micropython_name",
    "is_canmv_target",
    "is_esp_target",
    "is_micropython_target",
    "is_rp2040_target",
    "normalize_target_name",
    "source_filename_for_target",
    "target_runtime_label",
]

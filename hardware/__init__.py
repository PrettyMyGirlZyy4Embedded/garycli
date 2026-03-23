"""Public hardware module API."""

from hardware.serial_mon import connect_serial, disconnect_serial, read_serial_output
from hardware.swd import connect_swd, disconnect_swd, flash_via_swd, read_registers
from hardware.uart_isp import flash_via_uart

__all__ = [
    "connect_serial",
    "connect_swd",
    "disconnect_serial",
    "disconnect_swd",
    "flash_via_swd",
    "flash_via_uart",
    "read_registers",
    "read_serial_output",
]

"""Frame format of the pad calibration protocol (see "data format.ods").

Every frame is 11 bytes:

    fe ed | platform ID | pad ID | cmd | extra1 | extra2 | CRC_LOW CRC_HIGH | 04 04

The CRC covers the five bytes from platform ID to extra2 and is sent low byte
first. Qt-free on purpose, like serial_link.py.
"""

from __future__ import annotations

HEADER = b"\xfe\xed"
EOT = b"\x04\x04"
FRAME_SIZE = 11

# commands
CMD_PADS_CALIBRATION_START = 0x50
CMD_PADS_CALIBRATION_STOP = 0x51
CMD_PADS_GET_FACTORY_GF = 0x52
CMD_PADS_SAVE_FACTORY_GF = 0x53

# accepted range of a factory gain factor
GF_MIN = 10
GF_MAX = 200


class ProtocolError(ValueError):
    """A field does not fit the frame."""


def crc16(data: bytes) -> int:
    """CRC-16/CCITT-FALSE — poly 0x1021, init 0xFFFF, no reflection."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def build_frame(
    platform_id: int,
    pad_id: int,
    cmd: int,
    extra1: int = 0,
    extra2: int = 0,
) -> bytes:
    """Assemble a command frame with its CRC."""
    body = bytes(
        _byte(value, name)
        for value, name in (
            (platform_id, "platform ID"),
            (pad_id, "pad ID"),
            (cmd, "cmd"),
            (extra1, "extra1"),
            (extra2, "extra2"),
        )
    )
    crc = crc16(body)
    return HEADER + body + bytes((crc & 0xFF, crc >> 8)) + EOT


def save_factory_gf(platform_id: int, pad_id: int, channel: int, value: int) -> bytes:
    """"Enter (value changed)": store one channel's factory GF on the device."""
    if not GF_MIN <= value <= GF_MAX:
        raise ProtocolError(f"GF value {value} outside {GF_MIN}..{GF_MAX}")
    return build_frame(
        platform_id, pad_id, CMD_PADS_SAVE_FACTORY_GF, channel, value
    )


def get_factory_gf(platform_id: int, pad_id: int) -> bytes:
    """"Read": ask one pad for its stored factory GFs."""
    return build_frame(platform_id, pad_id, CMD_PADS_GET_FACTORY_GF)


def write_factory_gf(platform_id: int, pad_id: int) -> bytes:
    """"Write": commit the factory GFs held by the device."""
    return build_frame(platform_id, pad_id, CMD_PADS_SAVE_FACTORY_GF)


def hex_dump(frame: bytes) -> str:
    """Readable form for logs and status messages: ``fe ed 01 ...``."""
    return " ".join(f"{byte:02x}" for byte in frame)


def _byte(value: int, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ProtocolError(f"{name}: expected an integer, got {value!r}")
    if not 0 <= value <= 0xFF:
        raise ProtocolError(f"{name}: {value} does not fit in one byte")
    return value

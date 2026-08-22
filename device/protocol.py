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
CMD_PADS_SAVE_CF = 0x55

# pad ID of a command meant for the whole platform
NO_PAD = 0

# accepted range of a factory gain factor
GF_MIN = 10
GF_MAX = 200

# Answers come behind their own header and share one layout:
#     be ef | platform ID | pad ID | GF[8]       | CRC_LOW CRC_HIGH | 04 04
#     be ef | platform ID | pad ID | readings[8] | CRC_LOW CRC_HIGH | 04 04
# They are the same size, so only the run tells them apart: readings arrive
# between Start and Stop, gain factors the rest of the time. A command that
# stores something is acknowledged with a shorter frame, which carries no pad:
#     be ef | platform ID | cmd | 0x06 | CRC_LOW CRC_HIGH | 04 04
RESPONSE_HEADER = b"\xbe\xef"
GF_COUNT = 8
RESPONSE_SIZE = 2 + 2 + GF_COUNT + 2 + 2
ACK = 0x06
ACK_SIZE = 2 + 2 + 1 + 2 + 2
# Shortest first: a short frame that checks out cannot be the head of a long one.
RESPONSE_SIZES = (ACK_SIZE, RESPONSE_SIZE)


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


def save_cf(platform_id: int, pad_id: int, channel: int, value: int) -> bytes:
    """"Write" in the CAL section: store one channel's calibration factor."""
    return build_frame(platform_id, pad_id, CMD_PADS_SAVE_CF, channel, value)


def start_calibration(platform_id: int) -> bytes:
    """"Start": begin a calibration run. Whole platform, so no pad ID."""
    return build_frame(platform_id, NO_PAD, CMD_PADS_CALIBRATION_START)


def stop_calibration(platform_id: int) -> bytes:
    """"Stop": end the calibration run."""
    return build_frame(platform_id, NO_PAD, CMD_PADS_CALIBRATION_STOP)


def is_ack(frame: bytes) -> bool:
    """True for the short frame a stored value is acknowledged with."""
    return len(frame) == ACK_SIZE


def parse_ack(frame: bytes) -> tuple[int, int]:
    """Split an acknowledgement into platform ID and the command acknowledged."""
    body = _response_body(frame, ACK_SIZE)
    if body[2] != ACK:
        raise ProtocolError(f"ack byte {body[2]:#04x}, expected {ACK:#04x}")
    return body[0], body[1]


def parse_response(frame: bytes, *, signed: bool = False) -> tuple[int, int, list[int]]:
    """Split an answer into platform ID, pad ID and its eight values.

    Gain factors are plain bytes; readings are signed.
    """
    body = _response_body(frame, RESPONSE_SIZE)
    values = body[2:]
    return body[0], body[1], list(
        int.from_bytes(values[i : i + 1], "little", signed=signed)
        for i in range(GF_COUNT)
    )


def _response_body(frame: bytes, size: int) -> bytes:
    """The CRC-checked payload of an answer: everything but header, CRC and eot."""
    if len(frame) != size:
        raise ProtocolError(f"expected {size} bytes, got {len(frame)}")
    if not frame.startswith(RESPONSE_HEADER) or not frame.endswith(EOT):
        raise ProtocolError(f"not a response frame: {hex_dump(frame)}")
    body = frame[2:-4]
    sent = frame[-4] | frame[-3] << 8
    expected = crc16(body)
    if sent != expected:
        raise ProtocolError(f"CRC {sent:#06x}, expected {expected:#06x}")
    return body


def take_responses(buffer: bytearray) -> list[bytes]:
    """Pull whole response frames out of a byte stream, in order.

    Anything before a header, and any header not followed by a complete frame
    with the right terminator, is dropped; a partial tail stays in `buffer` for
    the next read.
    """
    frames: list[bytes] = []
    while True:
        start = buffer.find(RESPONSE_HEADER)
        if start < 0:
            # A lone be at the end may still be the start of a header.
            del buffer[: max(0, len(buffer) - 1)]
            return frames
        del buffer[:start]

        # Answers come in two lengths, so the CRC is what says which one this
        # is; a short frame that checks out cannot be the head of a long one.
        frame = next(
            (
                bytes(buffer[:size])
                for size in RESPONSE_SIZES
                if len(buffer) >= size and _looks_whole(bytes(buffer[:size]))
            ),
            None,
        )
        if frame is not None:
            del buffer[: len(frame)]
            frames.append(frame)
            continue
        if len(buffer) < max(RESPONSE_SIZES):
            return frames  # may still be the start of a longer frame
        del buffer[:2]  # false header, look for the next one


def _looks_whole(frame: bytes) -> bool:
    if not frame.endswith(EOT):
        return False
    body = frame[2:-4]
    return frame[-4] | frame[-3] << 8 == crc16(body)


def hex_dump(frame: bytes) -> str:
    """Readable form for logs and status messages: ``fe ed 01 ...``."""
    return " ".join(f"{byte:02x}" for byte in frame)


def _byte(value: int, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ProtocolError(f"{name}: expected an integer, got {value!r}")
    if not 0 <= value <= 0xFF:
        raise ProtocolError(f"{name}: {value} does not fit in one byte")
    return value

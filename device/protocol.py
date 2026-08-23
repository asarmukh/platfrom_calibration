"""Frame format of the pad calibration platform protocol (ТЗ section 2).

Every command is 11 bytes:

    fe ed | platform ID | pad ID | cmd | extra1 | extra2 | CRC_LOW CRC_HIGH | 04 04

The CRC covers the five bytes from platform ID to extra2 and is sent low byte
first; an answer's CRC covers everything between its header and the CRC in the
same way. Qt-free on purpose, like serial_link.py.
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
CMD_PADS_GET_CF = 0x54
CMD_PADS_SAVE_CF = 0x55

# pad ID of a command meant for the whole platform
NO_PAD = 0

# accepted range of a factory gain factor and of a calibration factor
GF_MIN = 10
GF_MAX = 200

# Answers come behind their own header in one of three lengths (ТЗ 2.1.2):
#     be ef | platform ID | cmd    | 0x06              | CRC_LOW CRC_HIGH | 04 04
#     be ef | platform ID | pad ID | uint8_t factor[8] | CRC_LOW CRC_HIGH | 04 04
#     be ef | platform ID | pad ID | int16_t reading[8]| CRC_LOW CRC_HIGH | 04 04
# The factor frame answers both GET_FACTORY_GF and GET_CF and carries nothing
# to tell them apart, so the caller matches it against the request it sent.
RESPONSE_HEADER = b"\xbe\xef"
CHANNELS = 8
ACK = 0x06
ACK_SIZE = 2 + 2 + 1 + 2 + 2
FACTOR_SIZE = 2 + 2 + CHANNELS + 2 + 2
READING_SIZE = 2 + 2 + CHANNELS * 2 + 2 + 2
# Shortest first: a short frame that checks out cannot be the head of a long one.
RESPONSE_SIZES = (ACK_SIZE, FACTOR_SIZE, READING_SIZE)


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


def get_cf(platform_id: int, pad_id: int) -> bytes:
    """"Read" in the CAL section: ask one pad for its calibration factors."""
    return build_frame(platform_id, pad_id, CMD_PADS_GET_CF)


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


def is_reading(frame: bytes) -> bool:
    """True for the long frame the platform streams between Start and Stop."""
    return len(frame) == READING_SIZE


def parse_factors(frame: bytes) -> tuple[int, int, list[int]]:
    """Split a 16-byte answer into platform ID, pad ID and eight factors.

    Answers both GET_FACTORY_GF and GET_CF; the values are plain bytes.
    """
    body = _response_body(frame, FACTOR_SIZE)
    return body[0], body[1], list(body[2:])


def parse_readings(frame: bytes) -> tuple[int, int, list[int]]:
    """Split a 24-byte answer into platform ID, pad ID and eight readings.

    Readings are signed 16-bit, low byte first — the order the frame's own CRC
    is sent in.
    """
    body = _response_body(frame, READING_SIZE)
    values = body[2:]
    return body[0], body[1], [
        int.from_bytes(values[i * 2 : i * 2 + 2], "little", signed=True)
        for i in range(CHANNELS)
    ]


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

"""ТЗ section 2 and 7: frame layouts, CRC, and pulling frames off the wire."""

from __future__ import annotations

import pytest

from device import protocol as p


def crc_bytes(body: bytes) -> bytes:
    crc = p.crc16(body)
    return bytes((crc & 0xFF, crc >> 8))


def response(pad_body: bytes) -> bytes:
    """Wrap an answer body (platform ID onwards) in header, CRC and eot."""
    return p.RESPONSE_HEADER + pad_body + crc_bytes(pad_body) + p.EOT


# --- section 7: CRC ---------------------------------------------------------


@pytest.mark.parametrize(
    "data, expected",
    [
        (b"", 0xFFFF),
        (b"\x00", 0xE1F0),
        (b"123456789", 0x29B1),  # the CCITT-FALSE check value
    ],
)
def test_crc16_is_ccitt_false(data, expected):
    assert p.crc16(data) == expected


# --- section 2.1.1: command frames ------------------------------------------


def test_command_frame_layout():
    frame = p.build_frame(0x01, 0x02, p.CMD_PADS_SAVE_CF, 0x06, 0x39)
    assert len(frame) == p.FRAME_SIZE == 11
    assert frame[:2] == b"\xfe\xed"
    assert frame[2:7] == bytes((0x01, 0x02, 0x55, 0x06, 0x39))
    assert frame[7:9] == crc_bytes(frame[2:7])  # low byte first
    assert frame[9:] == b"\x04\x04"


@pytest.mark.parametrize(
    "build, cmd, pad",
    [
        (lambda: p.start_calibration(7), 0x50, p.NO_PAD),
        (lambda: p.stop_calibration(7), 0x51, p.NO_PAD),
        (lambda: p.get_factory_gf(7, 1), 0x52, 1),
        (lambda: p.write_factory_gf(7, 2), 0x53, 2),
        (lambda: p.get_cf(7, 2), 0x54, 2),
        (lambda: p.save_cf(7, 1, 0, 0), 0x55, 1),
    ],
)
def test_command_codes_and_addressing(build, cmd, pad):
    frame = build()
    assert frame[2] == 7  # platform ID
    assert frame[3] == pad
    assert frame[4] == cmd


def test_start_and_stop_address_the_whole_platform():
    assert p.start_calibration(3)[3] == 0
    assert p.stop_calibration(3)[3] == 0


def test_save_factory_gf_carries_channel_and_value():
    frame = p.save_factory_gf(1, 2, 6, 57)
    assert frame[3:7] == bytes((2, 0x53, 6, 57))


def test_save_cf_carries_channel_and_value():
    frame = p.save_cf(1, 2, 4, 120)
    assert frame[3:7] == bytes((2, 0x55, 4, 120))


@pytest.mark.parametrize("value", [p.GF_MIN - 1, p.GF_MAX + 1])
def test_factory_gf_outside_its_range_is_refused(value):
    with pytest.raises(p.ProtocolError):
        p.save_factory_gf(1, 1, 0, value)


@pytest.mark.parametrize("value", [-1, 256, "3", True])
def test_a_field_that_is_not_a_byte_is_refused(value):
    with pytest.raises(p.ProtocolError):
        p.build_frame(value, 1, p.CMD_PADS_GET_CF)


# --- section 2.1.2: answers -------------------------------------------------


def test_acknowledge_is_nine_bytes():
    frame = response(bytes((5, 0x55, p.ACK)))
    assert len(frame) == p.ACK_SIZE == 9
    assert p.is_ack(frame)
    assert p.parse_ack(frame) == (5, 0x55)


def test_acknowledge_with_the_wrong_ack_byte_is_refused():
    with pytest.raises(p.ProtocolError):
        p.parse_ack(response(bytes((5, 0x55, 0x15))))


def test_factor_answer_is_sixteen_bytes_of_plain_bytes():
    values = [10, 20, 30, 40, 50, 60, 70, 200]
    frame = response(bytes((5, 1)) + bytes(values))
    assert len(frame) == p.FACTOR_SIZE == 16
    assert not p.is_ack(frame) and not p.is_reading(frame)
    assert p.parse_factors(frame) == (5, 1, values)


def test_reading_answer_is_twenty_four_bytes_of_signed_int16():
    values = [0, 1, -1, 32767, -32768, 1028, -300, 7]
    body = bytes((5, 2)) + b"".join(
        v.to_bytes(2, "little", signed=True) for v in values
    )
    frame = response(body)
    assert len(frame) == p.READING_SIZE == 24
    assert p.is_reading(frame)
    assert p.parse_readings(frame) == (5, 2, values)


def test_a_bad_crc_is_refused():
    frame = bytearray(response(bytes((5, 1)) + bytes(8)))
    frame[-3] ^= 0xFF
    with pytest.raises(p.ProtocolError):
        p.parse_factors(bytes(frame))


def test_the_wrong_length_is_refused():
    with pytest.raises(p.ProtocolError):
        p.parse_factors(response(bytes((5, 1)) + bytes(4)))


# --- framing ----------------------------------------------------------------


def test_whole_frames_are_pulled_out_in_order():
    ack = response(bytes((5, 0x55, p.ACK)))
    factors = response(bytes((5, 1)) + bytes(range(8)))
    buffer = bytearray(ack + factors)
    assert p.take_responses(buffer) == [ack, factors]
    assert not buffer


def test_leading_noise_is_dropped():
    ack = response(bytes((5, 0x55, p.ACK)))
    buffer = bytearray(b"\x00\x11\x22" + ack)
    assert p.take_responses(buffer) == [ack]


def test_a_split_frame_waits_for_its_tail():
    reading = response(bytes((5, 1)) + bytes(16))
    buffer = bytearray(reading[:10])
    assert p.take_responses(buffer) == []
    buffer += reading[10:]
    assert p.take_responses(buffer) == [reading]


def test_a_reading_payload_may_contain_a_header_or_a_terminator():
    # 0xEFBE and 0x0404 are legal int16 readings, so neither byte pair can be
    # trusted as a delimiter — only length plus CRC can.
    values = [-4162, 1028, 0, 0, 0, 0, 0, 0]  # -4162 == 0xEFBE little-endian
    body = bytes((5, 1)) + b"".join(
        v.to_bytes(2, "little", signed=True) for v in values
    )
    frame = response(body)
    buffer = bytearray(frame)
    assert p.take_responses(buffer) == [frame]
    assert p.parse_readings(frame)[2] == values

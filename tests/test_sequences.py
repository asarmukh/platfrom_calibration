"""ТЗ sections 3, 4 and 5: what each control puts on the wire, and when."""

from __future__ import annotations

import pytest

import app as app_module
from device import protocol as p
from device.connection import CONNECTED, FAILED
from widgets.workspace import CAL, EMPTY, GF, PADS

from conftest import DOUBLE, SINGLE


def set_double(window) -> None:
    window.sidebar.platform_type.set_active(DOUBLE)


def channels(window, pad: int = 1) -> list[int]:
    return window.workspace.pad_view.channel_numbers(pad)


# --- section 3: nothing happens before a platform type and ID ---------------


def test_the_platform_type_starts_unchosen(window):
    """Neither segment is lit: picking one is the operator's first decision."""
    assert not window.sidebar.platform_type.chosen


def test_with_nothing_chosen_every_control_is_dead(window):
    assert not window.sidebar.read_button.isEnabled()
    assert not window.sidebar.write_button.isEnabled()
    assert not window.sidebar.start_button.isEnabled()
    assert not window.workspace.pad_view.isEnabled()
    assert window.workspace.stack.currentIndex() == EMPTY


def test_a_platform_id_alone_does_not_show_the_pads(window):
    window.sidebar.platform_id.setText("1")
    assert window.workspace.stack.currentIndex() == EMPTY
    assert not window.sidebar.read_button.isEnabled()


@pytest.mark.parametrize("choice, pads", [(SINGLE, 1), (DOUBLE, 2)])
def test_choosing_a_type_brings_up_that_many_pads(window, choice, pads):
    """ТЗ 3б: the defaults go on screen as soon as the pad count is known."""
    window.sidebar.platform_type.set_active(choice)
    assert window.workspace.stack.currentIndex() == PADS
    assert len(window.workspace.pad_view.pads) == pads


def test_the_pads_are_shown_but_inert_without_a_platform_id(window):
    """ТЗ 3: visible is not the same as usable — no ID, no actions."""
    window.sidebar.platform_type.set_active(SINGLE)
    assert window.workspace.stack.currentIndex() == PADS
    assert not window.workspace.pad_view.isEnabled()
    assert not window.sidebar.read_button.isEnabled()
    assert not window.sidebar.write_button.isEnabled()
    assert not window.sidebar.start_button.isEnabled()


def test_both_chosen_opens_the_app_up(identified):
    assert identified.sidebar.read_button.isEnabled()
    assert identified.sidebar.write_button.isEnabled()
    assert identified.workspace.pad_view.isEnabled()
    assert identified.workspace.stack.currentIndex() == PADS


def test_clearing_the_platform_id_makes_the_pads_inert_again(identified):
    identified.sidebar.platform_id.setText("")
    # The type is still chosen, so the pads stay on screen — just unusable.
    assert identified.workspace.stack.currentIndex() == PADS
    assert not identified.workspace.pad_view.isEnabled()
    assert not identified.sidebar.read_button.isEnabled()


def test_defaults_are_ten(window):
    """ТЗ 3: factory GF and calibration factor both start at 10."""
    view = window.workspace.pad_view
    assert view.factory_field(1, 0).value == 10
    assert view.calibration_factor_single == [10] * 8
    assert view.calibration_factor_double == [[10] * 8, [10] * 8]


# --- section 4.1: committing a factory GF field -----------------------------


def test_committing_a_gf_field_stores_that_channel(identified, device):
    identified.workspace.pad_view.factory_field(1, 2).setText("57")
    identified.workspace.pad_view.factory_field(1, 2)._commit()
    assert device.commands == [(1, 1, p.CMD_PADS_SAVE_FACTORY_GF, 2, 57)]


def test_re_entering_the_same_value_sends_nothing(identified, device):
    editor = identified.workspace.pad_view.factory_field(1, 2)
    editor.setText("57")
    editor._commit()
    editor.setText("57")
    editor._commit()
    assert len(device.commands) == 1


# --- section 4.2 / 5.2: READ ------------------------------------------------


def test_read_in_the_gf_section_asks_for_factory_gf(identified, device):
    identified.sidebar.read_button.click()
    assert device.commands == [(1, 1, p.CMD_PADS_GET_FACTORY_GF, 0, 0)]


def test_read_in_the_cal_section_asks_for_calibration_factors(identified, device):
    identified.workspace.pad_view.set_view(CAL)
    identified.sidebar.read_button.click()
    assert device.commands == [(1, 1, p.CMD_PADS_GET_CF, 0, 0)]


def test_read_on_a_double_platform_asks_each_pad(identified, device):
    set_double(identified)
    identified.sidebar.read_button.click()
    assert device.commands == [
        (1, 1, p.CMD_PADS_GET_FACTORY_GF, 0, 0),
        (1, 2, p.CMD_PADS_GET_FACTORY_GF, 0, 0),
    ]


def test_the_second_pad_waits_out_the_pad_gap(identified, device, qtbot, monkeypatch):
    monkeypatch.setattr(app_module, "PAD_GAP", 120)
    set_double(identified)
    identified.sidebar.read_button.click()
    assert len(device.commands) == 1  # pad 2 has not gone out yet
    qtbot.wait(250)
    assert len(device.commands) == 2


def test_a_gf_answer_fills_the_fields(identified, device):
    identified.sidebar.read_button.click()
    device.factors(1, 1, [11, 12, 13, 14, 15, 16, 17, 18])
    view = identified.workspace.pad_view
    assert view.factory_field(1, 0).value == 11
    assert view.factory_field(1, 6).value == 17


def test_a_gf_answer_leaves_the_calibration_baseline_alone(identified, device):
    """ТЗ 4: factory GF is for the operator to look at, nothing more."""
    identified.sidebar.read_button.click()
    device.factors(1, 1, [99] * 8)
    assert identified.workspace.pad_view.calibration_factor_single == [10] * 8


def test_a_cf_answer_moves_the_baseline(identified, device):
    identified.workspace.pad_view.set_view(CAL)
    identified.sidebar.read_button.click()
    device.factors(1, 1, [20, 21, 22, 23, 24, 25, 26, 27])
    view = identified.workspace.pad_view
    assert view.calibration_factor_single == [20, 21, 22, 23, 24, 25, 26, 27]
    assert view.channel_block(1, 2).factor == 22


def test_an_answer_nobody_asked_for_is_ignored(identified, device):
    device.factors(1, 1, [99] * 8)
    assert identified.workspace.pad_view.factory_field(1, 0).value == 10


def test_an_answer_from_another_platform_is_ignored(identified, device):
    identified.sidebar.read_button.click()
    device.factors(9, 1, [99] * 8)
    assert identified.workspace.pad_view.factory_field(1, 0).value == 10


# --- section 4.3: WRITE in the GF section -----------------------------------


def test_gf_write_sends_a_zeroed_frame_per_pad(identified, device):
    set_double(identified)
    identified.sidebar.write_button.click()
    device.ack(1, p.CMD_PADS_SAVE_FACTORY_GF)
    assert device.commands == [
        (1, 1, p.CMD_PADS_SAVE_FACTORY_GF, 0, 0),
        (1, 2, p.CMD_PADS_SAVE_FACTORY_GF, 0, 0),
    ]


def test_gf_write_waits_for_each_acknowledgement(identified, device):
    set_double(identified)
    identified.sidebar.write_button.click()
    assert len(device.commands) == 1  # pad 2 waits for pad 1's ack
    device.ack(1, p.CMD_PADS_SAVE_FACTORY_GF)
    assert len(device.commands) == 2


def test_the_gui_is_dead_until_the_last_acknowledgement(identified, device):
    set_double(identified)
    identified.sidebar.write_button.click()
    assert not identified.workspace.pad_view.isEnabled()
    assert not identified.sidebar.platform_id.isEnabled()

    device.ack(1, p.CMD_PADS_SAVE_FACTORY_GF)
    assert not identified.workspace.pad_view.isEnabled()  # pad 2 still out there
    device.ack(1, p.CMD_PADS_SAVE_FACTORY_GF)
    assert identified.workspace.pad_view.isEnabled()


def test_a_silent_device_releases_the_gui(identified, device, qtbot, monkeypatch):
    monkeypatch.setattr(app_module, "ACK_TIMEOUT", 50)
    identified._ack_timer.setInterval(50)
    identified.sidebar.write_button.click()
    assert not identified.workspace.pad_view.isEnabled()
    qtbot.wait(150)
    assert identified.workspace.pad_view.isEnabled()
    assert "no answer" in identified.status_label.text()


# --- section 5.1: WRITE in the CAL section ----------------------------------


def test_cal_write_sends_every_channel_then_a_save(identified, device):
    identified.workspace.pad_view.set_view(CAL)
    identified.sidebar.write_button.click()
    for _ in range(len(channels(identified)) + 1):
        device.ack(1, p.CMD_PADS_SAVE_CF)

    expected = [(1, 1, p.CMD_PADS_SAVE_CF, ch, 10) for ch in channels(identified)]
    expected.append((1, 1, p.CMD_PADS_SAVE_CF, 0, 0))
    assert device.commands == expected


def test_cal_write_on_a_double_platform_alternates_pads(identified, device):
    set_double(identified)
    identified.workspace.pad_view.set_view(CAL)
    identified.sidebar.write_button.click()
    for _ in range(2 * len(channels(identified)) + 2):
        device.ack(1, p.CMD_PADS_SAVE_CF)

    sent = device.commands
    # channel-major: each channel goes to pad 1 then pad 2
    assert [(pad, ch) for _, pad, _, ch, _ in sent[:4]] == [
        (1, 0), (2, 0), (1, 1), (2, 1)
    ]
    # ТЗ 5.1 closes with a save; both pads need one or pad 2 loses its values
    assert sent[-2:] == [
        (1, 1, p.CMD_PADS_SAVE_CF, 0, 0),
        (1, 2, p.CMD_PADS_SAVE_CF, 0, 0),
    ]


def test_cal_write_carries_the_shown_factor(identified, device):
    view = identified.workspace.pad_view
    view.set_view(CAL)
    view.channel_block(1, 2).set_factor(57)
    identified.sidebar.write_button.click()
    for _ in range(len(channels(identified)) + 1):
        device.ack(1, p.CMD_PADS_SAVE_CF)
    assert (1, 1, p.CMD_PADS_SAVE_CF, 2, 57) in device.commands


def test_an_acknowledgement_for_another_command_does_not_advance(identified, device):
    identified.workspace.pad_view.set_view(CAL)
    identified.sidebar.write_button.click()
    device.ack(1, p.CMD_PADS_CALIBRATION_STOP)
    assert len(device.commands) == 1


# --- section 5.3 / 5.4: the run ---------------------------------------------


def test_start_and_stop_address_the_platform(identified, device):
    identified.workspace.pad_view.set_view(CAL)
    identified.sidebar.start_button.click()
    identified.sidebar.start_button.click()
    assert device.commands == [
        (1, 0, p.CMD_PADS_CALIBRATION_START, 0, 0),
        (1, 0, p.CMD_PADS_CALIBRATION_STOP, 0, 0),
    ]


def test_readings_are_scaled_by_the_factors(identified, device, qtbot):
    view = identified.workspace.pad_view
    view.set_view(CAL)
    identified.sidebar.read_button.click()
    device.factors(1, 1, [50] * 8)  # baseline cf = 50 on every channel
    view.channel_block(1, 1).set_factor(100)  # steppers moved this one

    identified.sidebar.start_button.click()
    device.readings(1, 1, [0, 2500, 0, 0, 0, 0, 0, 0])
    qtbot.wait(app_module.RENDER_INTERVAL * 3)

    # 2500 * 100 / (50 * 100) == 50.0
    assert view.channel_block(1, 1).value.text() == "50.0"


def test_readings_drive_the_totals(identified, device, qtbot):
    view = identified.workspace.pad_view
    view.set_view(CAL)
    identified.sidebar.read_button.click()
    device.factors(1, 1, [100] * 8)  # baseline 100, shown factor 100 -> raw/100

    identified.sidebar.start_button.click()
    device.readings(1, 1, [0, 1000, 1000, 0, 1000, 1000, 0, 0])
    qtbot.wait(app_module.RENDER_INTERVAL * 3)

    assert identified.sidebar.totals["Fz"].text() == "40.0"
    assert identified.sidebar.totals["xcop"].text() == "0.00"


def test_stopping_clears_what_the_run_showed(identified, device, qtbot):
    view = identified.workspace.pad_view
    view.set_view(CAL)
    identified.sidebar.read_button.click()
    device.factors(1, 1, [100] * 8)
    identified.sidebar.start_button.click()
    device.readings(1, 1, [0, 1000, 0, 0, 0, 0, 0, 0])
    qtbot.wait(app_module.RENDER_INTERVAL * 3)

    identified.sidebar.start_button.click()
    assert identified.sidebar.totals["Fz"].text() == "0.0"
    assert identified.sidebar.totals["xcop"].text() == "—"


def test_readings_without_a_run_provoke_a_stop(identified, device):
    device.readings(1, 1, [0] * 8)
    assert device.commands == [(1, 0, p.CMD_PADS_CALIBRATION_STOP, 0, 0)]


def test_losing_the_port_ends_the_run(identified, device):
    identified.workspace.pad_view.set_view(CAL)
    identified.sidebar.start_button.click()
    device.state = FAILED
    device.stateChanged.emit(FAILED, "gone")
    assert not identified._running
    assert not identified._render_timer.isActive()


def test_leaving_the_cal_section_ends_the_run(identified, device):
    identified.workspace.pad_view.set_view(CAL)
    identified.sidebar.start_button.click()
    identified.workspace.pad_view.set_view(GF)
    assert not identified._running
    assert device.commands[-1] == (1, 0, p.CMD_PADS_CALIBRATION_STOP, 0, 0)


# --- section 5.5: the steppers ----------------------------------------------


def test_the_steppers_move_the_shown_factor_only(identified, device):
    view = identified.workspace.pad_view
    view.set_view(CAL)
    view.channel_block(1, 0).increment.click()
    assert view.channel_block(1, 0).factor == 11
    assert view.calibration_factor_single[0] == 10  # baseline untouched
    assert device.commands == []  # nothing goes out until Write


@pytest.mark.parametrize("edge, button", [(10, "decrement"), (200, "increment")])
def test_a_stepper_stops_at_the_end_of_its_range(identified, edge, button):
    view = identified.workspace.pad_view
    view.set_view(CAL)
    block = view.channel_block(1, 0)
    block.set_factor(edge)
    getattr(block, button).click()
    assert block.factor == edge
    assert "calibration factor" in identified.status_label.text()

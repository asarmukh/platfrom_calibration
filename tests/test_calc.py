"""ТЗ section 6: forces and centre of pressure."""

from __future__ import annotations

import pytest

import calc

# A pad with nothing on it but a known load, channel by channel.
EMPTY = {ch: 0.0 for ch in range(8)}


def pad(**channels: float) -> dict[int, float]:
    values = dict(EMPTY)
    values.update({int(name.removeprefix("ch")): value for name, value in channels.items()})
    return values


# --- per-pad forces ---------------------------------------------------------


def test_forces_map_to_their_channels():
    forces = calc.pad_forces(pad(ch6=3.0, ch0=2.0, ch1=1.0, ch2=2.0, ch4=3.0, ch5=4.0))
    assert forces.fx == 3.0  # ch6
    assert forces.fy == 2.0  # ch0
    assert forces.fz == 10.0  # ch1 + ch2 + ch4 + ch5


def test_unused_channels_do_not_reach_the_forces():
    # ch3 and ch7 exist in the frame but belong to no sensor.
    forces = calc.pad_forces(pad(ch3=99.0, ch7=99.0))
    assert forces == (0.0, 0.0, 0.0)


# --- single platform --------------------------------------------------------


def test_single_load_dead_centre_has_no_offset():
    totals = calc.single_totals(pad(ch1=10, ch2=10, ch4=10, ch5=10))
    assert totals.fz == 40
    assert totals.xcop == 0
    assert totals.ycop == 0


def test_single_load_on_one_sensor_sits_at_its_coordinates():
    # ch1 is the sensor at (+10, +7) in the ТЗ figure.
    totals = calc.single_totals(pad(ch1=40))
    assert totals.xcop == pytest.approx(10.0)
    assert totals.ycop == pytest.approx(7.0)


@pytest.mark.parametrize(
    "channel, x, y",
    [("ch1", 10.0, 7.0), ("ch2", -10.0, 7.0), ("ch4", -10.0, -7.0), ("ch5", 10.0, -7.0)],
)
def test_single_cop_reaches_every_corner(channel, x, y):
    totals = calc.single_totals(pad(**{channel: 25}))
    assert totals.xcop == pytest.approx(x)
    assert totals.ycop == pytest.approx(y)


def test_single_cop_follows_the_formula_verbatim():
    values = pad(ch0=1, ch1=8, ch2=4, ch4=2, ch5=6, ch6=3)
    fz = 8 + 4 + 2 + 6
    totals = calc.single_totals(values)
    assert totals.fx == 3 and totals.fy == 1 and totals.fz == fz
    assert totals.xcop == pytest.approx(10 * (8 - 4 + 6 - 2) / fz)
    assert totals.ycop == pytest.approx(7 * (8 + 4 - 2 - 6) / fz)


def test_an_unloaded_platform_reports_dead_centre():
    totals = calc.single_totals(EMPTY)
    assert totals.fz == 0
    assert totals.xcop == 0.0 and totals.ycop == 0.0


def test_a_load_under_the_threshold_reports_dead_centre():
    """Below COP_MIN_LOAD the ratio is all noise, so it is not reported."""
    totals = calc.single_totals(pad(ch1=2.9))
    assert totals.fz == pytest.approx(2.9)
    assert totals.xcop == 0.0 and totals.ycop == 0.0


def test_a_load_on_the_threshold_is_reported():
    totals = calc.single_totals(pad(ch1=calc.COP_MIN_LOAD))
    assert totals.xcop == pytest.approx(10.0)
    assert totals.ycop == pytest.approx(7.0)


def test_a_negative_load_reports_dead_centre():
    """Drift on an empty platform must not come out as a position."""
    totals = calc.single_totals(pad(ch1=-50))
    assert totals.xcop == 0.0 and totals.ycop == 0.0


# --- double platform --------------------------------------------------------


def test_double_sums_the_forces_of_both_pads():
    totals = calc.double_totals(
        pad(ch6=1, ch0=2, ch1=3, ch2=3), pad(ch6=4, ch0=5, ch4=6, ch5=6)
    )
    assert totals.fx == 5
    assert totals.fy == 7
    assert totals.fz == 18


def test_double_load_split_evenly_sits_at_the_centre():
    load = pad(ch1=10, ch2=10, ch4=10, ch5=10)
    totals = calc.double_totals(load, load)
    assert totals.xcop == pytest.approx(0.0)
    # Pad 1 pulls +21/+7, pad 2 pulls -7/-21; an even load cancels them out.
    assert totals.ycop == pytest.approx(0.0)


@pytest.mark.parametrize(
    "which, channel, y",
    [(0, "ch1", 21.0), (0, "ch4", 7.0), (1, "ch1", -7.0), (1, "ch4", -21.0)],
)
def test_double_ycop_matches_the_sensor_coordinates(which, channel, y):
    load = pad(**{channel: 40})
    pads = [EMPTY, EMPTY]
    pads[which] = load
    totals = calc.double_totals(*pads)
    assert totals.ycop == pytest.approx(y)


def test_double_xcop_spans_both_pads():
    totals = calc.double_totals(pad(ch1=20), pad(ch1=20))
    assert totals.xcop == pytest.approx(10.0)


def test_double_cop_follows_the_formula_verbatim():
    a = pad(ch1=8, ch2=4, ch4=2, ch5=6)
    b = pad(ch1=1, ch2=2, ch4=3, ch5=4)
    fz = sum(a[ch] for ch in (1, 2, 4, 5)) + sum(b[ch] for ch in (1, 2, 4, 5))
    totals = calc.double_totals(a, b)
    x = (a[1] - a[2] + a[5] - a[4]) + (b[1] - b[2] + b[5] - b[4])
    y = 21 * (a[1] + a[2]) + 7 * (a[4] + a[5]) - 7 * (b[1] + b[2]) - 21 * (b[4] + b[5])
    assert totals.xcop == pytest.approx(10 * x / fz)
    assert totals.ycop == pytest.approx(y / fz)


def test_double_ycop_divides_by_the_total_load():
    """A load resting wholly on pad 2 must not divide by pad 1's zero."""
    totals = calc.double_totals(EMPTY, pad(ch1=10, ch2=10, ch4=10, ch5=10))
    assert totals.ycop == pytest.approx(-14.0)


def test_double_under_the_threshold_reports_dead_centre():
    """The threshold is on the combined load, which is the divisor."""
    totals = calc.double_totals(pad(ch1=1.0), pad(ch4=1.0))
    assert totals.fz == pytest.approx(2.0)
    assert totals.xcop == 0.0 and totals.ycop == 0.0


def test_cop_stays_inside_the_plot_range():
    for load in ({1: 40.0}, {2: 40.0}, {4: 40.0}, {5: 40.0}):
        totals = calc.double_totals({**EMPTY, **load}, EMPTY)
        assert abs(totals.xcop) <= calc.DOUBLE_COP_RANGE[0]
        assert abs(totals.ycop) <= calc.DOUBLE_COP_RANGE[1]

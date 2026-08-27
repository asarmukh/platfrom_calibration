"""The cop plot as a scale drawing of the plate (ТЗ section 1 figure)."""

from __future__ import annotations

import pytest

import calc
from widgets.cop_plot import CopPlot

WIDTH = 180


def plot(*, double: bool = False) -> CopPlot:
    return CopPlot(
        plate=calc.DOUBLE_PLATE if double else calc.SINGLE_PLATE,
        sensors=calc.DOUBLE_SENSORS if double else calc.SINGLE_SENSORS,
        width=WIDTH,
        pads=2 if double else 1,
    )


@pytest.mark.parametrize(
    "double, plate",
    [(False, calc.SINGLE_PLATE), (True, calc.DOUBLE_PLATE)],
)
def test_the_plot_keeps_the_plate_proportions(qtbot, double, plate):
    """40x28 for a single platform, 40x56 for a double one."""
    widget = plot(double=double)
    assert widget.width() == WIDTH
    assert widget.height() == round(WIDTH * plate[1] / plate[0])


def test_the_origin_is_the_middle_of_the_plot(qtbot):
    widget = plot()
    centre = widget.plate_rect().center()
    assert widget.point_at(0, 0) == centre


@pytest.mark.parametrize("double", [False, True])
def test_the_plate_edges_land_on_the_plot_edges(qtbot, double):
    """Proportional border: half the plate in cm is the edge of the widget.

    Within a pixel — an integer widget size cannot hold 40:28 exactly, so the
    plate is fitted to the tighter axis.
    """
    widget = plot(double=double)
    half_w, half_h = widget._plate[0] / 2, widget._plate[1] / 2
    rect = widget.plate_rect()

    assert widget.point_at(-half_w, 0).x() == pytest.approx(rect.left(), abs=1)
    assert widget.point_at(half_w, 0).x() == pytest.approx(rect.right(), abs=1)
    assert widget.point_at(0, half_h).y() == pytest.approx(rect.top(), abs=1)
    assert widget.point_at(0, -half_h).y() == pytest.approx(rect.bottom(), abs=1)


def test_the_y_axis_points_up(qtbot):
    widget = plot()
    assert widget.point_at(0, 5).y() < widget.point_at(0, -5).y()


@pytest.mark.parametrize("channel", ["ch1", "ch2", "ch4", "ch5"])
def test_full_deflection_parks_the_marker_on_that_channel(qtbot, channel):
    """A load resting on one cell puts the dot on that channel's number.

    This is the answer to "the dot does not reach the corner": the cop cannot
    leave the sensor rectangle, so the channel mark is as far as it goes.
    """
    widget = plot()
    cop = calc.single_totals({int(channel.removeprefix("ch")): 40.0})
    x, y = widget._sensors[channel]

    assert widget.point_at(cop.xcop, cop.ycop) == widget.point_at(x, y)


def test_an_unloaded_platform_parks_the_marker_at_the_origin(qtbot):
    widget = plot()
    cop = calc.single_totals({})
    assert widget.point_at(cop.xcop, cop.ycop) == widget.plate_rect().center()


def test_every_channel_mark_sits_inside_the_plate(qtbot):
    for double in (False, True):
        widget = plot(double=double)
        rect = widget.plate_rect()
        for label, (x, y) in widget._sensors.items():
            assert rect.contains(widget.label_at(x, y)), label


def test_a_double_plot_carries_both_pads_worth_of_cells(qtbot):
    assert len(plot(double=True)._sensors) == 8
    assert len(plot()._sensors) == 4


def test_only_the_fz_cells_are_drawn(qtbot):
    """ch0 and ch6 measure shear, so they are not part of the cop picture."""
    for sensors in (calc.SINGLE_SENSORS, calc.DOUBLE_SENSORS):
        drawn = {label.split("#")[0] for label in sensors}
        assert drawn == {"ch1", "ch2", "ch4", "ch5"}


def test_clearing_the_marker_hides_it(qtbot):
    widget = plot()
    widget.set_point(1.0, 1.0)
    assert widget._marker is not None
    widget.clear()
    assert widget._marker is None

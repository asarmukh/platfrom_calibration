"""Forces and centre of pressure, exactly as ТЗ section 6 defines them.

The inputs are the *scaled* channel readings — what section 5.3 puts on screen,
not the raw counts. Summing raw counts would be meaningless: each channel has
its own calibration factor, and removing it is what the factors are for.

The cop coefficients are the Fz-sensor coordinates from the ТЗ figure, in cm:
a single pad carries its sensors at (±10, ±7), and the two pads of a double
platform sit at (±10, ±21) and (±10, ±7). So cop comes out in centimetres,
measured from the centre of the platform.

Qt-free, so the arithmetic can be tested on its own.
"""

from __future__ import annotations

from typing import Mapping, NamedTuple

# Half the extent of the cop plots, in cm: the range each formula can produce.
SINGLE_COP_RANGE = (10.0, 7.0)
DOUBLE_COP_RANGE = (10.0, 28.0)

# Below this vertical load the centre of pressure is reported as 0, 0. It is a
# ratio over Fz, so near zero the noise on four load cells swings it across the
# whole plate; an empty platform would otherwise look like a moving target.
COP_MIN_LOAD = 3.0  # kg


class Forces(NamedTuple):
    """One pad's three forces."""

    fx: float
    fy: float
    fz: float


class Totals(NamedTuple):
    """What the sidebar's TOTAL block shows.

    ``xcop``/``ycop`` fall back to 0.0 under ``COP_MIN_LOAD``: with nothing on
    the platform there is no centre of pressure to report.
    """

    fx: float
    fy: float
    fz: float
    xcop: float
    ycop: float


Readings = Mapping[int, float]


def pad_forces(values: Readings) -> Forces:
    """Fx, Fy and Fz of one pad (ТЗ 6: Fx = ch6, Fy = ch0, Fz = ch1+ch2+ch4+ch5)."""
    return Forces(
        fx=values.get(6, 0.0),
        fy=values.get(0, 0.0),
        fz=sum(values.get(ch, 0.0) for ch in (1, 2, 4, 5)),
    )


def single_totals(values: Readings) -> Totals:
    """The TOTAL block of a single platform.

    xcop = 10 * (ch1 - ch2 + ch5 - ch4) / Fz
    ycop =  7 * (ch1 + ch2 - ch4 - ch5) / Fz
    """
    forces = pad_forces(values)
    ch = lambda n: values.get(n, 0.0)  # noqa: E731 — keeps the formulas readable
    return Totals(
        *forces,
        xcop=_over(10 * (ch(1) - ch(2) + ch(5) - ch(4)), forces.fz),
        ycop=_over(7 * (ch(1) + ch(2) - ch(4) - ch(5)), forces.fz),
    )


def double_totals(pad1: Readings, pad2: Readings) -> Totals:
    """The TOTAL block of a double platform.

    xcop = 10 * ((ch1-ch2+ch5-ch4)₁ + (ch1-ch2+ch5-ch4)₂) / Fz_total
    ycop = (21*(ch1+ch2)₁ + 7*(ch4+ch5)₁ - 7*(ch1+ch2)₂ - 21*(ch4+ch5)₂) / Fz_total

    The ТЗ writes ycop's denominator as "Fz"; it has to be Fz_total, since a
    load resting entirely on one pad would otherwise divide by the other pad's
    zero. Reported as a defect in the document.
    """
    first, second = pad_forces(pad1), pad_forces(pad2)
    fz_total = first.fz + second.fz
    a = lambda n: pad1.get(n, 0.0)  # noqa: E731
    b = lambda n: pad2.get(n, 0.0)  # noqa: E731

    x = (a(1) - a(2) + a(5) - a(4)) + (b(1) - b(2) + b(5) - b(4))
    y = (
        21 * (a(1) + a(2))
        + 7 * (a(4) + a(5))
        - 7 * (b(1) + b(2))
        - 21 * (b(4) + b(5))
    )
    return Totals(
        fx=first.fx + second.fx,
        fy=first.fy + second.fy,
        fz=fz_total,
        xcop=_over(10 * x, fz_total),
        ycop=_over(y, fz_total),
    )


def _over(numerator: float, fz: float) -> float:
    """Divide by Fz, or report dead centre when the platform is unloaded.

    A load below the threshold — including a negative one, which is drift on an
    empty platform rather than a real reading — is not worth a position.
    """
    return numerator / fz if fz >= COP_MIN_LOAD else 0.0

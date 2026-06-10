import numpy as np
from core import spd


def test_d65_known_value():
    # D65 is normalised to 100 at 560 nm.
    assert abs(spd.spd_at(560.0, "D65") - 100.0) < 1e-6


def test_equal_energy_is_flat():
    assert spd.spd_at(400.0, "E") == 1.0
    assert spd.spd_at(700.0, "E") == 1.0


def test_unknown_illuminant_raises():
    try:
        spd.spd_at(550.0, "nope")
    except ValueError:
        return
    raise AssertionError("expected ValueError for unknown illuminant")


def test_y_integral_positive_and_stable():
    # The white-point divisor should be positive and only weakly dependent on
    # the band count (coarse vs fine sampling differ by a few percent at most).
    coarse_wl = np.arange(385.0, 730.0, (730.0 - 380.0) / 16.0)
    fine_wl = np.arange(381.0, 730.0, (730.0 - 380.0) / 64.0)
    y_coarse = spd.y_integral("D65", coarse_wl, (730.0 - 380.0) / 16.0)
    y_fine = spd.y_integral("D65", fine_wl, (730.0 - 380.0) / 64.0)
    assert y_coarse > 0.0 and y_fine > 0.0
    assert abs(y_coarse - y_fine) / y_fine < 0.1

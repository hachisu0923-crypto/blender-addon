import numpy as np
from core import cmf, jakob_hanika, spd

_ILLUM = "D65"


def _integrate(coeffs):
    """Independent round-trip: reflectance -> XYZ -> linear sRGB on a 1 nm grid.

    Uses a finer grid than the fitter (5 nm) so this genuinely validates the
    fit rather than re-running the optimiser's own forward model.
    """
    grid = np.arange(360.0, 831.0, 1.0)
    s = jakob_hanika.reflectance(coeffs, grid)
    spd_w = spd.spd_array(grid, _ILLUM)
    cmfs = cmf.cmf_array(grid)
    xyz = np.sum(s[:, None] * spd_w[:, None] * cmfs * 1.0, axis=0)
    y_white = float(np.sum(spd_w * cmfs[:, 1] * 1.0))
    return cmf.xyz_to_linear_srgb(xyz / y_white)


def test_grey_roundtrip_tight():
    for v in (0.05, 0.18, 0.5, 0.7, 0.9):
        coeffs = jakob_hanika.rgb_to_coeffs((v, v, v), _ILLUM)
        out = _integrate(coeffs)
        assert np.max(np.abs(out - v)) < 0.02, (v, out)


def test_moderate_colours_roundtrip():
    colours = [
        (0.6, 0.3, 0.2), (0.2, 0.5, 0.3), (0.3, 0.3, 0.6),
        (0.7, 0.7, 0.2), (0.7, 0.2, 0.7), (0.2, 0.7, 0.7),
    ]
    for rgb in colours:
        out = _integrate(jakob_hanika.rgb_to_coeffs(rgb, _ILLUM))
        assert np.max(np.abs(out - np.array(rgb))) < 0.05, (rgb, out)


def test_saturated_colours_in_ballpark():
    # sRGB primaries sit on the gamut boundary -- the model can only approximate
    # them, but the result must still be the right hue, not garbage.
    for rgb in [(0.8, 0.05, 0.05), (0.05, 0.8, 0.05), (0.05, 0.05, 0.8)]:
        out = _integrate(jakob_hanika.rgb_to_coeffs(rgb, _ILLUM))
        assert np.argmax(out) == np.argmax(rgb)
        assert np.max(np.abs(out - np.array(rgb))) < 0.18, (rgb, out)


def test_random_in_gamut_colours():
    rng = np.random.default_rng(0)
    worst = 0.0
    for _ in range(20):
        rgb = tuple(rng.uniform(0.1, 0.85, size=3))
        out = _integrate(jakob_hanika.rgb_to_coeffs(rgb, _ILLUM))
        worst = max(worst, float(np.max(np.abs(out - np.array(rgb)))))
    assert worst < 0.06, worst


def test_determinism_and_clamping():
    a = jakob_hanika.rgb_to_coeffs((0.4, 0.4, 0.4), _ILLUM)
    b = jakob_hanika.rgb_to_coeffs((0.4, 0.4, 0.4), _ILLUM)
    assert a == b
    # Out-of-range inputs must not crash (clamped internally).
    jakob_hanika.rgb_to_coeffs((0.0, 0.0, 0.0), _ILLUM)
    jakob_hanika.rgb_to_coeffs((1.0, 1.0, 1.0), _ILLUM)
    jakob_hanika.rgb_to_coeffs((-0.2, 1.5, 0.5), _ILLUM)

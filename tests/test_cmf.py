import numpy as np
from core import cmf


def test_cmf_at_matches_table():
    # Tabulated CIE 1931 2-deg value at 550 nm.
    np.testing.assert_allclose(cmf.cmf_at(550.0), [0.43345, 0.99495, 0.00875], atol=1e-6)


def test_cmf_interpolates_between_samples():
    mid = cmf.cmf_at(552.5)
    lo = cmf.cmf_at(550.0)
    hi = cmf.cmf_at(555.0)
    np.testing.assert_allclose(mid, (lo + hi) / 2.0, atol=1e-9)


def test_cmf_out_of_range_clamps_to_zero():
    assert np.all(cmf.cmf_at(200.0) == 0.0)
    assert np.all(cmf.cmf_at(900.0) == 0.0)


def test_xyz_srgb_roundtrip():
    rgb = np.array([0.2, 0.5, 0.8])
    xyz = cmf.linear_srgb_to_xyz(rgb)
    np.testing.assert_allclose(cmf.xyz_to_linear_srgb(xyz), rgb, atol=1e-9)


def test_srgb_gamma_roundtrip():
    c = np.array([0.0, 0.04, 0.18, 0.5, 1.0])
    np.testing.assert_allclose(cmf.srgb_to_linear(cmf.linear_to_srgb(c)), c, atol=1e-6)


def test_d65_white_is_neutral():
    # The sRGB matrix is defined for a D65 white point, so the D65 illuminant
    # integrated and normalised to Y=1 must map to a neutral grey (R==G==B==1).
    from core import spd

    grid = np.arange(360.0, 831.0, 5.0)
    white = spd.reference_white_xyz("D65", grid, 5.0)
    rgb = cmf.xyz_to_linear_srgb(white / white[1])
    np.testing.assert_allclose(rgb, [1.0, 1.0, 1.0], atol=2e-3)

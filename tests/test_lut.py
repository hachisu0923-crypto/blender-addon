import numpy as np
from core import cmf, jakob_hanika, spd


def _integrate(coeffs):
    grid = np.arange(360.0, 831.0, 1.0)
    s = jakob_hanika.reflectance(coeffs, grid)
    spd_w = spd.spd_array(grid, "D65")
    cmfs = cmf.cmf_array(grid)
    xyz = np.sum(s[:, None] * spd_w[:, None] * cmfs, axis=0)
    y = float(np.sum(spd_w * cmfs[:, 1]))
    return cmf.xyz_to_linear_srgb(xyz / y)


def test_lut_shape_is_preserved():
    arr = np.zeros((4, 5, 3))
    out = jakob_hanika.rgb_array_to_coeffs(arr, size=9)
    assert out.shape == (4, 5, 3)


def test_lut_roundtrip_delta_e():
    rng = np.random.default_rng(0)
    rgbs = rng.uniform(0.1, 0.85, size=(60, 3))
    coeffs = jakob_hanika.rgb_array_to_coeffs(rgbs, "D65", 6500.0, size=17)
    worst = max(float(np.max(np.abs(_integrate(c) - rgb))) for rgb, c in zip(rgbs, coeffs))
    assert worst < 0.06, worst


def test_lut_matches_direct_fit():
    # At/near grid points a fine LUT should match the direct per-colour fit.
    for rgb in [(0.5, 0.5, 0.5), (0.25, 0.5, 0.75), (0.8, 0.3, 0.2)]:
        c_lut = jakob_hanika.rgb_array_to_coeffs(np.array([rgb]), size=25)[0]
        c_dir = jakob_hanika.rgb_to_coeffs(rgb)
        np.testing.assert_allclose(_integrate(c_lut), _integrate(c_dir), atol=0.03)


def test_lut_grey_preserved_spatially():
    # A grey ramp must stay neutral after uplift (R≈G≈B per texel).
    ramp = np.stack([np.linspace(0.1, 0.9, 16)] * 3, axis=-1)  # (16,3)
    coeffs = jakob_hanika.rgb_array_to_coeffs(ramp, size=17)
    for v, c in zip(ramp[:, 0], coeffs):
        out = _integrate(c)
        assert np.max(out) - np.min(out) < 0.02, (v, out)

import numpy as np
from core import cmf, jakob_hanika, sampling, spd


class _Settings:
    def __init__(self, n, mode):
        self.lambda_min = 380.0
        self.lambda_max = 730.0
        self.band_count = n
        self.illuminant = "D65"
        self.color_temperature = 6500.0
        self.sampling = mode


def _xyz(coeffs, wl, weights, white):
    grey = jakob_hanika.reflectance(coeffs, wl)
    xyz = np.sum(grey[:, None] * weights, axis=0)
    return xyz / white[1]


def test_both_modes_have_positive_white():
    for mode in ("UNIFORM", "IMPORTANCE"):
        _, _, white = sampling.get_samples(_Settings(16, mode))
        assert white[1] > 0.0


def test_white_point_neutral_both_modes():
    # Perfect reflector (S=1) must come out neutral (R≈G≈B) for either mode.
    flat = (50.0, 0.0, 0.0)  # large c0 -> sigmoid ≈ 1
    for mode in ("UNIFORM", "IMPORTANCE"):
        wl, weights, white = sampling.get_samples(_Settings(24, mode))
        rgb = cmf.xyz_to_linear_srgb(_xyz(flat, wl, weights, white))
        np.testing.assert_allclose(rgb, [1.0, 1.0, 1.0], atol=0.02)


def test_importance_matches_dense_uniform():
    # Importance sampling with few bands should track a dense uniform reference
    # in chromaticity for a smooth reflectance.
    coeffs = jakob_hanika.rgb_to_coeffs((0.3, 0.55, 0.25))
    wl_u, w_u, white_u = sampling.get_samples(_Settings(160, "UNIFORM"))
    wl_i, w_i, white_i = sampling.get_samples(_Settings(20, "IMPORTANCE"))
    ref = _xyz(coeffs, wl_u, w_u, white_u)
    est = _xyz(coeffs, wl_i, w_i, white_i)
    ref_xy = ref[:2] / ref.sum()
    est_xy = est[:2] / est.sum()
    assert np.max(np.abs(ref_xy - est_xy)) < 0.02


def test_importance_concentrates_in_visible():
    wl, _, _ = sampling.get_samples(_Settings(16, "IMPORTANCE"))
    # Samples concentrate in the visible (CMF support), away from the tails.
    assert np.mean((wl > 430) & (wl < 670)) > 0.7

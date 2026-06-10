import numpy as np
from core import fresnel, metals


def test_fresnel_dielectric_matches_4_percent():
    # n=1.5, k=0 -> ~4% reflectance (ordinary glass).
    np.testing.assert_allclose(fresnel.fresnel_normal(1.5, 0.0), 0.04, atol=1e-9)


def test_fresnel_in_unit_range():
    n = np.array([0.1, 0.5, 1.0, 2.0])
    k = np.array([3.0, 2.0, 0.0, 5.0])
    r = fresnel.fresnel_normal(n, k)
    assert np.all((r >= 0.0) & (r <= 1.0))


def test_bundled_metals_present():
    names = metals.available()
    for expected in ("gold", "silver", "copper", "aluminium"):
        assert expected in names


def test_gold_is_reddish():
    # Gold reflects red far more than blue.
    r = metals.reflectance("gold", np.array([450.0, 650.0]))
    assert r[1] > r[0] + 0.3


def test_silver_is_high_and_flat():
    r = metals.reflectance("silver", np.array([450.0, 550.0, 650.0]))
    assert np.all(r > 0.9)
    assert (r.max() - r.min()) < 0.1


def test_copper_reflects_red_over_blue():
    r = metals.reflectance("copper", np.array([450.0, 650.0]))
    assert r[1] > r[0]

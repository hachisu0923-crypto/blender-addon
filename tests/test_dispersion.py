import numpy as np
from core import dispersion as d


def test_abbe_roundtrip_recovers_nd():
    # BK7-like glass: n_d = 1.5168, V_d = 64.17.
    n_d, V_d = 1.5168, 64.17
    A, B = d.abbe_to_cauchy(n_d, V_d)
    np.testing.assert_allclose(d.cauchy_ior(d.LINE_D, A, B), n_d, atol=1e-6)


def test_abbe_matches_dispersion_definition():
    n_d, V_d = 1.5168, 64.17
    A, B = d.abbe_to_cauchy(n_d, V_d)
    n_f = d.cauchy_ior(d.LINE_F, A, B)
    n_c = d.cauchy_ior(d.LINE_C, A, B)
    np.testing.assert_allclose((n_d - 1.0) / (n_f - n_c), V_d, rtol=1e-6)


def test_normal_dispersion_is_monotonic():
    A, B = d.abbe_to_cauchy(1.5168, 64.17)
    n = d.cauchy_ior(np.array([400.0, 500.0, 600.0, 700.0]), A, B)
    assert np.all(np.diff(n) < 0.0)   # index falls as wavelength rises

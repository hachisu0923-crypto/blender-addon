import numpy as np
from core import spectrum


def test_load_and_interpolate(tmp_path):
    csv = tmp_path / "s.csv"
    csv.write_text("wavelength,reflectance\n400,0.1\n500,0.5\n600,0.9\n")
    wl, refl = spectrum.load_reflectance_csv(str(csv))
    assert list(wl) == [400.0, 500.0, 600.0]
    # Midpoint interpolation and out-of-range clamping.
    got = spectrum.reflectance_at(str(csv), [450.0, 550.0, 700.0])
    np.testing.assert_allclose(got[:2], [0.3, 0.7], atol=1e-9)
    assert 0.0 <= got[2] <= 1.0


def test_unsorted_csv_is_sorted(tmp_path):
    csv = tmp_path / "s.csv"
    csv.write_text("wavelength,reflectance\n600,0.9\n400,0.1\n500,0.5\n")
    wl, _ = spectrum.load_reflectance_csv(str(csv))
    assert list(wl) == [400.0, 500.0, 600.0]

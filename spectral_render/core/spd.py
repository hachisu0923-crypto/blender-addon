"""Illuminant spectral power distributions and white-point integrals.

Pure NumPy + stdlib only -- must NOT import ``bpy``.

Phase 1 needs only the illuminant SPD and its CIE-weighted integral so that the
spectral accumulation can be normalised to a neutral white point (see the
"normalisation" risk in the spec). Planck / measured presets arrive in Phase 2.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from . import cmf

_D65_PATH = Path(__file__).resolve().parent.parent / "data" / "d65.csv"

_D65_WL: np.ndarray | None = None
_D65_POWER: np.ndarray | None = None


def _load_d65() -> tuple[np.ndarray, np.ndarray]:
    global _D65_WL, _D65_POWER
    if _D65_POWER is None:
        raw = np.loadtxt(_D65_PATH, delimiter=",", skiprows=1)
        _D65_WL = np.ascontiguousarray(raw[:, 0], dtype=np.float64)
        _D65_POWER = np.ascontiguousarray(raw[:, 1], dtype=np.float64)
    return _D65_WL, _D65_POWER


def spd_array(wavelengths, illuminant: str = "D65") -> np.ndarray:
    """Relative spectral power at each wavelength (shape ``(N,)``).

    ``'E'`` is the equal-energy illuminant (flat 1.0). ``'D65'`` interpolates the
    bundled table.
    """
    lam = np.atleast_1d(np.asarray(wavelengths, dtype=np.float64))
    if illuminant == "E":
        return np.ones_like(lam)
    if illuminant == "D65":
        wl, power = _load_d65()
        return np.interp(lam, wl, power, left=0.0, right=0.0)
    raise ValueError(f"Unknown illuminant: {illuminant!r}")


def spd_at(lam: float, illuminant: str = "D65") -> float:
    """Relative spectral power at a single wavelength."""
    return float(spd_array([lam], illuminant)[0])


def reference_white_xyz(illuminant, wavelengths, dlam: float) -> np.ndarray:
    """``Sum( SPD(lam) * CMF(lam) * dlam )`` over the given band wavelengths.

    Computed on the *same* wavelength list the renderer accumulates over so the
    normalisation stays consistent (the white-point divisor is component Y).
    """
    lam = np.asarray(wavelengths, dtype=np.float64)
    spd = spd_array(lam, illuminant)            # (N,)
    cmfs = cmf.cmf_array(lam)                    # (N, 3)
    return np.sum(spd[:, None] * cmfs * dlam, axis=0)


def y_integral(illuminant, wavelengths, dlam: float) -> float:
    """``Sum( SPD(lam) * y_bar(lam) * dlam )`` -- the white-point divisor (scalar)."""
    return float(reference_white_xyz(illuminant, wavelengths, dlam)[1])

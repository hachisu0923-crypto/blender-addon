"""Illuminant spectral power distributions and white-point integrals.

Pure NumPy + stdlib only -- must NOT import ``bpy``.

The illuminant SPD feeds both the spectral uplift (so injected colours render
back correctly) and the compositing white-point normalisation. Presets: D65
(bundled table), equal-energy ``E``, and a Planck black body parameterised by
colour temperature.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from . import cmf

_D65_PATH = Path(__file__).resolve().parent.parent / "data" / "d65.csv"

_D65_WL: np.ndarray | None = None
_D65_POWER: np.ndarray | None = None

# Planck constants (SI).
_H = 6.62607015e-34
_C = 2.99792458e8
_KB = 1.380649e-23


def _load_d65() -> tuple[np.ndarray, np.ndarray]:
    global _D65_WL, _D65_POWER
    if _D65_POWER is None:
        raw = np.loadtxt(_D65_PATH, delimiter=",", skiprows=1)
        _D65_WL = np.ascontiguousarray(raw[:, 0], dtype=np.float64)
        _D65_POWER = np.ascontiguousarray(raw[:, 1], dtype=np.float64)
    return _D65_WL, _D65_POWER


def planck(lam_nm, temperature: float):
    """Black-body spectral radiance ``M(lam, T)`` (relative; scale cancels in norm)."""
    lam = np.asarray(lam_nm, dtype=np.float64) * 1e-9
    return (2.0 * _H * _C * _C) / (lam ** 5) / (np.expm1(_H * _C / (lam * _KB * temperature)))


def spd_array(wavelengths, illuminant: str = "D65", temperature: float = 6500.0) -> np.ndarray:
    """Relative spectral power at each wavelength (shape ``(N,)``)."""
    lam = np.atleast_1d(np.asarray(wavelengths, dtype=np.float64))
    if illuminant == "E":
        return np.ones_like(lam)
    if illuminant == "D65":
        wl, power = _load_d65()
        return np.interp(lam, wl, power, left=0.0, right=0.0)
    if illuminant == "BLACKBODY":
        return planck(lam, temperature)
    raise ValueError(f"Unknown illuminant: {illuminant!r}")


def spd_at(lam: float, illuminant: str = "D65", temperature: float = 6500.0) -> float:
    """Relative spectral power at a single wavelength."""
    return float(spd_array([lam], illuminant, temperature)[0])


def reference_white_xyz(illuminant, wavelengths, dlam: float, temperature: float = 6500.0) -> np.ndarray:
    """``Sum( SPD(lam) * CMF(lam) * dlam )`` over the given band wavelengths."""
    lam = np.asarray(wavelengths, dtype=np.float64)
    spd = spd_array(lam, illuminant, temperature)   # (N,)
    cmfs = cmf.cmf_array(lam)                        # (N, 3)
    return np.sum(spd[:, None] * cmfs * dlam, axis=0)


def y_integral(illuminant, wavelengths, dlam: float, temperature: float = 6500.0) -> float:
    """``Sum( SPD(lam) * y_bar(lam) * dlam )`` -- the white-point divisor (scalar)."""
    return float(reference_white_xyz(illuminant, wavelengths, dlam, temperature)[1])

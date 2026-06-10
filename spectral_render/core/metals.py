"""Measured complex refractive indices for metals and their reflectance.

Pure NumPy + stdlib -- must NOT import ``bpy``. Reads ``data/metals/<name>.csv``
(columns ``wavelength,n,k``). Bundled tables are approximate Johnson & Christy
values, adequate for plausible spectral metal colour.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from . import fresnel

_DIR = Path(__file__).resolve().parent.parent / "data" / "metals"
_CACHE: dict[str, np.ndarray] = {}


def available() -> list[str]:
    """Names of bundled metal datasets (CSV stem, e.g. 'gold')."""
    return sorted(p.stem for p in _DIR.glob("*.csv"))


def _load(name: str) -> np.ndarray:
    raw = _CACHE.get(name)
    if raw is None:
        raw = np.loadtxt(_DIR / f"{name}.csv", delimiter=",", skiprows=1)
        _CACHE[name] = raw
    return raw


def nk_at(name: str, wavelengths):
    """Interpolated ``(n, k)`` for a metal at the given wavelengths."""
    raw = _load(name)
    lam = np.asarray(wavelengths, dtype=np.float64)
    n = np.interp(lam, raw[:, 0], raw[:, 1])
    k = np.interp(lam, raw[:, 0], raw[:, 2])
    return n, k


def reflectance(name: str, wavelengths):
    """Normal-incidence Fresnel reflectance ``R(lam)`` for a metal."""
    n, k = nk_at(name, wavelengths)
    return fresnel.fresnel_normal(n, k)

"""Load arbitrary measured reflectance spectra from CSV.

Pure NumPy + stdlib -- must NOT import ``bpy``. CSV columns: ``wavelength,reflectance``
(reflectance in [0, 1]). Used by the per-object spectral override (Phase 4).
"""

from __future__ import annotations

import numpy as np


def load_reflectance_csv(path):
    """Return ``(wavelengths, reflectance)`` sorted by wavelength."""
    raw = np.loadtxt(path, delimiter=",", skiprows=1)
    raw = np.atleast_2d(raw)
    order = np.argsort(raw[:, 0])
    return raw[order, 0], raw[order, 1]


def reflectance_at(path, wavelengths):
    """Interpolated reflectance at ``wavelengths`` (clamped to [0, 1])."""
    wl, refl = load_reflectance_csv(path)
    return np.clip(np.interp(np.asarray(wavelengths, dtype=np.float64), wl, refl), 0.0, 1.0)

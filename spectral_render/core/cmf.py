"""CIE 1931 2-degree colour matching functions and XYZ <-> sRGB transforms.

Pure NumPy + stdlib only -- this module must NOT import ``bpy`` so it can be
unit-tested outside Blender (see tests/test_cmf.py).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# Data loading (CIE 1931 2-degree CMF, 360-830 nm @ 5 nm)
# ---------------------------------------------------------------------------

_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "cie_1931_2deg.csv"

# Lazily populated module-global cache: (wavelengths(N,), table(N,3)).
_WL: np.ndarray | None = None
_TABLE: np.ndarray | None = None


def _load() -> tuple[np.ndarray, np.ndarray]:
    """Load and cache the CMF table. Raises a clear error if the file is bad."""
    global _WL, _TABLE
    if _TABLE is None:
        raw = np.loadtxt(_DATA_PATH, delimiter=",", skiprows=1)
        _WL = np.ascontiguousarray(raw[:, 0], dtype=np.float64)
        _TABLE = np.ascontiguousarray(raw[:, 1:4], dtype=np.float64)
    return _WL, _TABLE


def cmf_array(wavelengths) -> np.ndarray:
    """Return the CMF ``[x_bar, y_bar, z_bar]`` for each wavelength.

    Linear interpolation between the 5 nm samples; values outside the tabulated
    range clamp to 0. Output shape is ``(N, 3)``.
    """
    wl, table = _load()
    lam = np.atleast_1d(np.asarray(wavelengths, dtype=np.float64))
    out = np.empty((lam.shape[0], 3), dtype=np.float64)
    for ch in range(3):
        out[:, ch] = np.interp(lam, wl, table[:, ch], left=0.0, right=0.0)
    return out


def cmf_at(lam: float) -> np.ndarray:
    """Return the CMF ``[x_bar, y_bar, z_bar]`` at a single wavelength (shape ``(3,)``)."""
    return cmf_array([lam])[0]


# ---------------------------------------------------------------------------
# XYZ <-> linear sRGB (D65)
# ---------------------------------------------------------------------------

# Standard sRGB (D65) primaries: linear-sRGB = M @ XYZ.
XYZ_TO_SRGB = np.array(
    [
        [3.2406255, -1.5372080, -0.4986286],
        [-0.9689307, 1.8757561, 0.0415175],
        [0.0557101, -0.2040211, 1.0569959],
    ],
    dtype=np.float64,
)

# Inverse: XYZ = M_inv @ linear-sRGB.
SRGB_TO_XYZ = np.linalg.inv(XYZ_TO_SRGB)


def xyz_to_linear_srgb(xyz) -> np.ndarray:
    """Convert CIE XYZ to linear sRGB. Accepts ``(3,)`` or ``(..., 3)``."""
    arr = np.asarray(xyz, dtype=np.float64)
    return arr @ XYZ_TO_SRGB.T


def linear_srgb_to_xyz(rgb) -> np.ndarray:
    """Convert linear sRGB to CIE XYZ. Accepts ``(3,)`` or ``(..., 3)``."""
    arr = np.asarray(rgb, dtype=np.float64)
    return arr @ SRGB_TO_XYZ.T


def linear_to_srgb(c) -> np.ndarray:
    """Apply the sRGB OETF (gamma) and clamp to [0, 1]."""
    arr = np.clip(np.asarray(c, dtype=np.float64), 0.0, 1.0)
    return np.where(arr <= 0.0031308, 12.92 * arr, 1.055 * np.power(arr, 1.0 / 2.4) - 0.055)


def srgb_to_linear(c) -> np.ndarray:
    """Apply the inverse sRGB OETF (display sRGB -> linear)."""
    arr = np.clip(np.asarray(c, dtype=np.float64), 0.0, 1.0)
    return np.where(arr <= 0.04045, arr / 12.92, np.power((arr + 0.055) / 1.055, 2.4))

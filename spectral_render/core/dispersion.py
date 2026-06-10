"""Wavelength-dependent refractive index n(lambda) for dispersion.

Pure NumPy + stdlib -- must NOT import ``bpy``.

Two-term Cauchy model ``n(lam) = A + B/lam^2 (+ C/lam^4)`` with lam in micrometres,
plus a helper to derive Cauchy coefficients from the catalogue ``n_d`` and Abbe
number ``V_d`` (the usual way optical glass is specified).
"""

from __future__ import annotations

import numpy as np

# Fraunhofer reference lines (nm).
LINE_F = 486.13   # blue (H)
LINE_D = 587.56   # yellow (He d)
LINE_C = 656.27   # red (H)


def cauchy_ior(lam_nm, A: float, B: float, C: float = 0.0):
    """Refractive index at ``lam_nm`` (scalar or array) for Cauchy coefficients."""
    lam_um = np.asarray(lam_nm, dtype=np.float64) / 1000.0
    inv2 = 1.0 / (lam_um * lam_um)
    return A + B * inv2 + C * inv2 * inv2


def abbe_to_cauchy(n_d: float, V_d: float) -> tuple[float, float]:
    """Two-term Cauchy ``(A, B)`` from catalogue index ``n_d`` and Abbe ``V_d``.

    ``V_d = (n_d - 1) / (n_F - n_C)`` -> solve for ``B`` (in um^2), then ``A``.
    """
    lf = LINE_F / 1000.0
    lc = LINE_C / 1000.0
    ld = LINE_D / 1000.0
    B = (n_d - 1.0) / (V_d * (1.0 / (lf * lf) - 1.0 / (lc * lc)))
    A = n_d - B / (ld * ld)
    return A, B

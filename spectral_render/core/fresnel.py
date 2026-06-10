"""Fresnel reflectance for complex refractive indices (metals).

Pure NumPy + stdlib -- must NOT import ``bpy``.
"""

from __future__ import annotations

import numpy as np


def fresnel_normal(n, k):
    """Unpolarised reflectance at normal incidence for complex IOR ``n + ik``.

    ``R = ((n-1)^2 + k^2) / ((n+1)^2 + k^2)``. Accepts scalars or arrays.
    """
    n = np.asarray(n, dtype=np.float64)
    k = np.asarray(k, dtype=np.float64)
    return ((n - 1.0) ** 2 + k * k) / ((n + 1.0) ** 2 + k * k)

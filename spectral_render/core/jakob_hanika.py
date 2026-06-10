"""Jakob-Hanika (2019) spectral uplift -- RGB -> 3 sigmoid-polynomial coeffs.

Option B from the spec: on-the-fly Levenberg-Marquardt fit using NumPy only
(Blender's bundled Python has no SciPy). Pure NumPy + stdlib -- must NOT import
``bpy``.

Reflectance model (must stay byte-for-byte identical to the shader node group)::

    lam_hat = (lam - 360) / 470          # 360..830 nm -> [0, 1]
    S(lam)  = sigmoid(c2*lam_hat^2 + c1*lam_hat + c0)
    sigmoid(x) = 0.5 + x / (2*sqrt(1 + x^2))
"""

from __future__ import annotations

import functools

import numpy as np

from . import cmf, spd

# Dense fitting grid (independent of the render band count) for accuracy.
_GRID = np.arange(360.0, 831.0, 5.0)
_DLAM = 5.0
_LAM_HAT = (_GRID - 360.0) / 470.0

# Cache of per-illuminant weight matrices W (N, 3) such that
#   XYZ_normalised = S @ W      (already divided by the illuminant's Y integral).
_WEIGHTS: dict[tuple[str, float], np.ndarray] = {}


def _weights(illuminant: str, temperature: float = 6500.0) -> np.ndarray:
    key = (illuminant, temperature)
    W = _WEIGHTS.get(key)
    if W is None:
        spd_w = spd.spd_array(_GRID, illuminant, temperature)   # (N,)
        cmfs = cmf.cmf_array(_GRID)                              # (N, 3)
        W = spd_w[:, None] * cmfs * _DLAM                       # (N, 3)
        y_white = float(np.sum(spd_w * cmfs[:, 1] * _DLAM))
        W = W / y_white
        _WEIGHTS[key] = W
    return W


def reflectance(coeffs, wavelengths) -> np.ndarray:
    """Evaluate ``S(lam)`` for given coefficients on arbitrary wavelengths.

    Shared by the fitter and the unit tests; mirrors the shader math exactly.
    """
    c0, c1, c2 = coeffs
    lam = np.asarray(wavelengths, dtype=np.float64)
    lam_hat = (lam - 360.0) / 470.0
    x = c2 * lam_hat * lam_hat + c1 * lam_hat + c0
    return 0.5 + x / (2.0 * np.sqrt(1.0 + x * x))


def _forward(c: np.ndarray, W: np.ndarray) -> np.ndarray:
    """coeffs -> predicted linear-sRGB triple."""
    x = c[2] * _LAM_HAT * _LAM_HAT + c[1] * _LAM_HAT + c[0]
    s = 0.5 + x / (2.0 * np.sqrt(1.0 + x * x))
    xyz = s @ W
    return cmf.xyz_to_linear_srgb(xyz)


def _fit(target: np.ndarray, W: np.ndarray) -> np.ndarray:
    """Levenberg-Marquardt fit of 3 coeffs to a linear-sRGB target."""
    c = np.zeros(3, dtype=np.float64)
    f = _forward(c, W)
    r = f - target
    cost = float(r @ r)
    mu = 1e-3
    best_c, best_cost = c.copy(), cost
    h = 1e-4

    for _ in range(60):
        # Finite-difference Jacobian (3x3): d rgb_pred / d c_k.
        J = np.empty((3, 3), dtype=np.float64)
        for k in range(3):
            cp = c.copy()
            cp[k] += h
            J[:, k] = (_forward(cp, W) - f) / h

        JtJ = J.T @ J
        Jtr = J.T @ r
        try:
            delta = np.linalg.solve(JtJ + mu * np.eye(3), Jtr)
        except np.linalg.LinAlgError:
            delta = np.linalg.lstsq(JtJ + mu * np.eye(3), Jtr, rcond=None)[0]

        c_new = c - delta
        f_new = _forward(c_new, W)
        r_new = f_new - target
        cost_new = float(r_new @ r_new)

        if cost_new < cost:
            c, f, r, cost = c_new, f_new, r_new, cost_new
            mu = max(mu * 0.5, 1e-9)
            if cost < best_cost:
                best_c, best_cost = c.copy(), cost
            if cost < 1e-10:
                break
        else:
            mu = min(mu * 4.0, 1e6)

    return best_c


@functools.lru_cache(maxsize=8192)
def _cached(rgb_key, illuminant: str, temperature: float) -> tuple[float, float, float]:
    target = np.clip(np.asarray(rgb_key, dtype=np.float64), 1e-4, 1.0 - 1e-4)
    c = _fit(target, _weights(illuminant, temperature))
    return (float(c[0]), float(c[1]), float(c[2]))


def rgb_to_coeffs(rgb, illuminant: str = "D65", temperature: float = 6500.0) -> tuple[float, float, float]:
    """Fit sigmoid-polynomial coefficients ``(c0, c1, c2)`` for a linear-sRGB colour.

    ``rgb`` components are linear sRGB in [0, 1]. Results are memoised on the
    rounded colour so re-injecting many identically coloured materials is cheap.
    """
    key = (round(float(rgb[0]), 5), round(float(rgb[1]), 5), round(float(rgb[2]), 5))
    return _cached(key, illuminant, float(temperature))

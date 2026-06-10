"""Wavelength band selection: uniform and luminance-importance sampling.

Pure NumPy + stdlib -- must NOT import ``bpy``.

Both strategies return ``(wavelengths, weights, white)`` where::

    XYZ          = sum_i  grey_i * weights[i]          # grey_i = rendered S(lam_i)
    XYZ_display  = XYZ / white[1]                      # normalise to a neutral white

so the renderer is agnostic to which strategy produced the bands. Importance
sampling draws wavelengths with density proportional to the luminance
contribution ``y_bar(lam)*SPD(lam)`` and divides by the pdf, keeping the estimate
unbiased while concentrating samples where the eye is sensitive.
"""

from __future__ import annotations

import numpy as np

from . import cmf, spd

_FINE = 1.0  # nm grid for the importance cdf


def uniform_bands(lo, hi, n, illuminant, temperature):
    dlam = (hi - lo) / n
    wl = np.array([lo + (i + 0.5) * dlam for i in range(n)], dtype=np.float64)
    spd_w = spd.spd_array(wl, illuminant, temperature)
    cmfs = cmf.cmf_array(wl)
    weights = spd_w[:, None] * cmfs * dlam
    return wl, weights, weights.sum(axis=0)


def importance_bands(lo, hi, n, illuminant, temperature):
    grid = np.arange(lo, hi + 1e-9, _FINE)
    spd_g = spd.spd_array(grid, illuminant, temperature)
    # Importance weight = total XYZ contribution (x_bar+y_bar+z_bar)*SPD. Using the
    # full CMF sum (not luminance alone) keeps the blue z_bar lobe sampled, which
    # luminance-only sampling would starve, biasing chromaticity.
    w = cmf.cmf_array(grid).sum(axis=1) * spd_g

    trap = 0.5 * (w[1:] + w[:-1]) * np.diff(grid)
    w_total = float(trap.sum())
    if w_total <= 0.0:                                # degenerate -> fall back
        return uniform_bands(lo, hi, n, illuminant, temperature)

    cdf = np.concatenate([[0.0], np.cumsum(trap)]) / w_total
    pdf = w / w_total                                # density per nm

    u = (np.arange(n) + 0.5) / n                      # stratified midpoints
    wl = np.interp(u, cdf, grid)
    spd_s = spd.spd_array(wl, illuminant, temperature)
    cmf_s = cmf.cmf_array(wl)
    p = np.maximum(np.interp(wl, grid, pdf), 1e-12)
    weights = (spd_s[:, None] * cmf_s) / (p[:, None] * n)
    return wl, weights, weights.sum(axis=0)


def get_samples(settings):
    """Return ``(wavelengths, weights, white)`` for the scene's sampling mode."""
    lo, hi, n = settings.lambda_min, settings.lambda_max, settings.band_count
    illum, temp = settings.illuminant, settings.color_temperature
    if getattr(settings, "sampling", "UNIFORM") == "IMPORTANCE":
        return importance_bands(lo, hi, n, illum, temp)
    return uniform_bands(lo, hi, n, illum, temp)

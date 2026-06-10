"""Per-band EXR output for post regrading.

Each band is written as its own scene-linear OpenEXR (``band_<i>_<λ>nm.exr``) so
the wavelength stack can be reloaded and regraded in Nuke/Natron/Blender. Files
are scene-linear (no view transform baked in), keeping them OCIO-consistent.
"""

from __future__ import annotations

import os

import bpy
import numpy as np


def write_band_exrs(directory: str, bands, width: int, height: int, scene) -> list[str]:
    """Write one EXR per band.

    ``bands`` is an iterable of ``(index, wavelength_nm, grey_flat)`` where
    ``grey_flat`` is the band's reflectance image as a flat ``(W*H,)`` array.
    Assumes ``scene.render.image_settings.file_format == 'OPEN_EXR'``.
    """
    directory = bpy.path.abspath(directory)
    os.makedirs(directory, exist_ok=True)
    img = bpy.data.images.new("_spectral_band_tmp", width, height, float_buffer=True)
    paths = []
    try:
        for i, lam, grey in bands:
            rgba = np.ones((grey.shape[0], 4), dtype=np.float32)
            rgba[:, 0] = grey
            rgba[:, 1] = grey
            rgba[:, 2] = grey
            img.pixels.foreach_set(rgba.ravel())
            img.update()
            path = os.path.join(directory, f"band_{i:03d}_{int(round(lam))}nm.exr")
            img.save_render(path, scene=scene)
            paths.append(path)
    finally:
        bpy.data.images.remove(img)
    return paths

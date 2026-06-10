"""Scene-level settings and shared helpers for the Spectral Render addon."""

from __future__ import annotations

import bpy
from bpy.props import EnumProperty, FloatProperty, IntProperty, PointerProperty


class SpectralSettings(bpy.types.PropertyGroup):
    lambda_min: FloatProperty(
        name="λ min (nm)", description="Lower bound of the wavelength range",
        default=380.0, min=300.0, max=800.0,
    )
    lambda_max: FloatProperty(
        name="λ max (nm)", description="Upper bound of the wavelength range",
        default=730.0, min=400.0, max=830.0,
    )
    band_count: IntProperty(
        name="Bands", description="Number of wavelength bands (N)",
        default=16, min=3, max=64,
    )
    samples_per_band: IntProperty(
        name="Samples / band", description="Cycles samples for each band render",
        default=64, min=1, max=4096,
    )
    target: EnumProperty(
        name="Target",
        items=[
            ("SELECTED", "Selected Objects", "Materials on selected objects"),
            ("ALL", "All Materials", "Every material in the file"),
        ],
        default="SELECTED",
    )
    illuminant: EnumProperty(
        name="Illuminant",
        items=[
            ("D65", "D65", "CIE D65 daylight"),
            ("E", "Equal Energy", "Flat equal-energy illuminant"),
        ],
        default="D65",
    )


def ensure_spectral_lambda(scene) -> None:
    """Create the ``scene['spectral_lambda']`` custom property if missing."""
    if "spectral_lambda" not in scene.keys():
        scene["spectral_lambda"] = 550.0


def band_wavelengths(settings) -> tuple[list[float], float]:
    """Centre wavelengths of each band and the band width ``dlam``.

    Single source of truth for the band math -- used by both the renderer and
    the white-point normalisation so they stay consistent.
    """
    n = settings.band_count
    lo, hi = settings.lambda_min, settings.lambda_max
    dlam = (hi - lo) / n
    wl = [lo + (i + 0.5) * dlam for i in range(n)]
    return wl, dlam


def register():
    bpy.utils.register_class(SpectralSettings)
    bpy.types.Scene.spectral = PointerProperty(type=SpectralSettings)


def unregister():
    del bpy.types.Scene.spectral
    bpy.utils.unregister_class(SpectralSettings)

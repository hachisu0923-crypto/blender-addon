"""Scene-level settings and shared helpers for the Spectral Render addon."""

from __future__ import annotations

import bpy
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
)


class SpectralMaterialSettings(bpy.types.PropertyGroup):
    """Per-material spectral options (Phase 2: dispersion)."""

    dispersion_enabled: BoolProperty(
        name="Dispersion",
        description="Drive this material's IOR with a wavelength-dependent n(λ)",
        default=False,
    )
    dispersion_mode: EnumProperty(
        name="Mode",
        items=[
            ("ABBE", "IOR + Abbe", "Derive Cauchy A/B from n_d and Abbe number"),
            ("CAUCHY", "Cauchy A/B/C", "Enter Cauchy coefficients directly"),
        ],
        default="ABBE",
    )
    ior_d: FloatProperty(name="IOR (n_d)", default=1.5168, min=1.0, max=3.0)
    abbe: FloatProperty(name="Abbe (V_d)", default=64.17, min=1.0, max=120.0)
    cauchy_a: FloatProperty(name="Cauchy A", default=1.5046)
    cauchy_b: FloatProperty(name="Cauchy B (µm²)", default=0.0042)
    cauchy_c: FloatProperty(name="Cauchy C (µm⁴)", default=0.0)


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
            ("BLACKBODY", "Black Body", "Planck black body at a colour temperature"),
        ],
        default="D65",
    )
    color_temperature: FloatProperty(
        name="Temperature (K)", description="Black-body colour temperature",
        default=6500.0, min=1000.0, max=12000.0,
    )


def ensure_spectral_lambda(scene) -> None:
    """Create the ``scene['spectral_lambda']`` custom property if missing."""
    if "spectral_lambda" not in scene.keys():
        scene["spectral_lambda"] = 550.0


def dispersion_coeffs(mat_settings) -> tuple[float, float, float]:
    """Cauchy ``(A, B, C)`` for a material's dispersion settings."""
    from .core import dispersion

    if mat_settings.dispersion_mode == "ABBE":
        a, b = dispersion.abbe_to_cauchy(mat_settings.ior_d, mat_settings.abbe)
        return a, b, 0.0
    return mat_settings.cauchy_a, mat_settings.cauchy_b, mat_settings.cauchy_c


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
    bpy.utils.register_class(SpectralMaterialSettings)
    bpy.utils.register_class(SpectralSettings)
    bpy.types.Scene.spectral = PointerProperty(type=SpectralSettings)
    bpy.types.Material.spectral = PointerProperty(type=SpectralMaterialSettings)


def unregister():
    del bpy.types.Material.spectral
    del bpy.types.Scene.spectral
    bpy.utils.unregister_class(SpectralSettings)
    bpy.utils.unregister_class(SpectralMaterialSettings)

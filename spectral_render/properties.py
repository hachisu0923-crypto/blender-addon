"""Scene-level settings and shared helpers for the Spectral Render addon."""

from __future__ import annotations

import bpy
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    FloatVectorProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
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

    metal_enabled: BoolProperty(
        name="Spectral Metal",
        description="Drive Base Color with measured wavelength-dependent metal reflectance "
                    "(set the Principled Metallic input to 1)",
        default=False,
    )
    metal: EnumProperty(
        name="Metal",
        items=[
            ("gold", "Gold", ""),
            ("silver", "Silver", ""),
            ("copper", "Copper", ""),
            ("aluminium", "Aluminium", ""),
        ],
        default="gold",
    )

    volume_enabled: BoolProperty(
        name="Spectral Volume",
        description="Drive Volume Absorption/Scatter density with a wavelength-dependent "
                    "absorption profile derived from the tint",
        default=False,
    )
    volume_tint: FloatVectorProperty(
        name="Transmission Tint", subtype="COLOR", size=3,
        min=0.0, max=1.0, default=(0.5, 0.7, 1.0),
    )
    volume_density: FloatProperty(name="Density", default=1.0, min=0.0)

    override_enabled: BoolProperty(
        name="Spectrum Override",
        description="Drive Base Color from a measured reflectance spectrum CSV "
                    "(wavelength,reflectance); takes precedence over uplift/metal",
        default=False,
    )
    override_csv: StringProperty(name="Spectrum CSV", subtype="FILE_PATH", default="")

    glass_preset: EnumProperty(
        name="Glass Preset",
        items=[
            ("N-BK7", "N-BK7", "n_d 1.5168 / V_d 64.17"),
            ("N-SF11", "N-SF11", "n_d 1.7847 / V_d 25.76"),
            ("N-FK51A", "N-FK51A", "n_d 1.4866 / V_d 84.47"),
            ("FUSED_SILICA", "Fused Silica", "n_d 1.4585 / V_d 67.8"),
            ("DIAMOND", "Diamond", "n_d 2.417 / V_d 55.3"),
        ],
        default="N-BK7",
    )


# Catalogue n_d / Abbe for the glass presets above.
GLASS_PRESETS = {
    "N-BK7": (1.5168, 64.17),
    "N-SF11": (1.7847, 25.76),
    "N-FK51A": (1.4866, 84.47),
    "FUSED_SILICA": (1.4585, 67.80),
    "DIAMOND": (2.4170, 55.30),
}


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
    sampling: EnumProperty(
        name="Sampling",
        items=[
            ("UNIFORM", "Uniform", "Equal-interval bands"),
            ("IMPORTANCE", "Importance", "Stratified XYZ-contribution importance sampling"),
        ],
        default="UNIFORM",
    )
    texture_spectral: BoolProperty(
        name="Uplift Textures",
        description="Spectralise image-texture Base Color per texel (keeps the pattern). "
                    "Procedural/complex Base Color falls back to a constant uplift",
        default=True,
    )
    coeff_max_res: IntProperty(
        name="Coeff Map Max Res",
        description="Cap the coefficient map resolution (0 = match source texture)",
        default=0, min=0, max=8192,
    )
    save_band_exrs: BoolProperty(
        name="Save Band EXRs",
        description="Write each band as a scene-linear EXR for post regrading",
        default=False,
    )
    exr_dir: StringProperty(
        name="EXR Folder", subtype="DIR_PATH", default="//spectral_bands/",
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

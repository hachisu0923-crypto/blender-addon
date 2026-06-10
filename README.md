# Spectral Render

A Blender 4.2+ add-on that turns Cycles into a *pseudo-spectral* renderer. RGB
materials are "uplifted" to wavelength reflectance `S(λ)` (Jakob-Hanika 2019),
rendered band-by-band, and composited in CIE XYZ for physically plausible colour
(dispersion, wavelength-dependent metals, etc.). See
[`spectral_addon_spec.md`](spectral_addon_spec.md) for the full design.

## Status

- **Phase 1 (MVP) — done.** Equal-interval bands, Base Color uplift,
  non-destructive node injection/restore, band-composited rendering.
- **Phase 2 — done.** Dispersion (Cauchy / Abbe → wavelength-driven IOR), a
  Planck black-body illuminant, spectral metals (measured complex IOR → Fresnel
  reflectance via Float Curve) and wavelength-dependent volume absorption.
- **Phase 3 — done.** Stratified XYZ-importance wavelength sampling (unbiased,
  fewer bands for the same noise), per-band scene-linear EXR output, and an
  OCIO-consistent linear result (view transform applies on display).
- **Phase 4 — done.** Per-material reflectance-spectrum override (CSV), glass
  presets, animation render (per-frame composite, with the uplift coefficient
  cache avoiding recomputation), progress/ETA logging, and Extension packaging.

All four phases of `spectral_addon_spec.md` are implemented. The pure-maths core
has 37 passing unit tests; the bpy-bound operators/UI are exercised by the
Blender integration test.

## Layout

```
spectral_render/        # the shippable Blender Extension
├── blender_manifest.toml
├── __init__.py         # register/unregister
├── properties.py       # Scene settings + band helpers
├── ui/panel.py         # "Spectral" N-panel
├── core/               # pure-NumPy maths (no bpy): cmf, spd, jakob_hanika
│   └── node_group.py   # SpectralColor shader node group (bpy)
├── ops/                # inject / restore / render operators
└── data/               # cie_1931_2deg.csv, d65.csv
tests/                  # pure-math unit tests + Blender integration test
```

## Install (development)

1. Copy or symlink `spectral_render/` into your Blender extensions/add-ons
   directory, or use **Edit ▸ Preferences ▸ Get Extensions ▸ Install from Disk**.
2. Open the **3D Viewport ▸ Sidebar (`N`) ▸ Spectral** tab.
3. Set the wavelength range / band count, then **Inject Spectral Nodes →
   Spectral Render → Restore**.

Build the Extension package with:

```
blender --command extension build --source-dir spectral_render
```

## Testing

Pure-math modules (no Blender required):

```
pip install numpy pytest
pytest tests/
```

Full end-to-end (requires Blender on PATH):

```
blender --background --python tests/integration_blender.py
```

# Spectral Render

A Blender 4.2+ add-on that turns Cycles into a *pseudo-spectral* renderer. RGB
materials are "uplifted" to wavelength reflectance `S(λ)` (Jakob-Hanika 2019),
rendered band-by-band, and composited in CIE XYZ for physically plausible colour
(dispersion, wavelength-dependent metals, etc.). See
[`spectral_addon_spec.md`](spectral_addon_spec.md) for the full design.

## Status

- **Phase 1 (MVP) — done.** Equal-interval bands, Base Color uplift,
  non-destructive node injection/restore, band-composited rendering.
- **Phase 2 (in progress).** Dispersion (Cauchy / Abbe → wavelength-driven IOR)
  and a Planck black-body illuminant are implemented. Metals (complex IOR) and
  volumes are next.
- **Phases 3–4** (importance sampling, multilayer EXR, OCIO, packaging) planned.

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

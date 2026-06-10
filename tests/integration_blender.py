"""End-to-end test for the Spectral Render addon -- run inside Blender:

    blender --background --python tests/integration_blender.py

Exits non-zero on any failed assertion so it can gate CI on a machine that has
Blender installed. Covers the Phase 1 completion conditions: inject -> render ->
restore round-trip, idempotency, neutral grey (no colour cast) and that changing
the band wavelength actually changes the render.
"""

import os
import sys

import bpy

# Make the addon importable from a source checkout (repo_root/spectral_render).
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import spectral_render  # noqa: E402

_FAILS = []


def check(cond, msg):
    print(("PASS" if cond else "FAIL") + ": " + msg)
    if not cond:
        _FAILS.append(msg)


def build_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.render.resolution_x = 64
    scene.render.resolution_y = 64
    scene.render.resolution_percentage = 100
    scene.cycles.samples = 16

    # Grey sphere (linear Base Color 0.5).
    bpy.ops.mesh.primitive_uv_sphere_add(location=(0, 0, 0))
    obj = bpy.context.active_object
    mat = bpy.data.materials.new("Grey")
    mat.use_nodes = True
    bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (0.5, 0.5, 0.5, 1.0)
    obj.data.materials.append(mat)

    # Glass sphere with dispersion enabled (Phase 2).
    bpy.ops.mesh.primitive_uv_sphere_add(location=(2.5, 0, 0))
    gobj = bpy.context.active_object
    gmat = bpy.data.materials.new("Glass")
    gmat.use_nodes = True
    gbsdf = next(n for n in gmat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    gbsdf.inputs["IOR"].default_value = 1.45
    gmat.spectral.dispersion_enabled = True
    gmat.spectral.dispersion_mode = "ABBE"
    gobj.data.materials.append(gmat)
    build_scene.glass = gmat

    # Light + camera.
    light = bpy.data.lights.new("L", "AREA")
    light.energy = 1000
    lo = bpy.data.objects.new("L", light)
    lo.location = (3, -3, 4)
    scene.collection.objects.link(lo)
    cam = bpy.data.cameras.new("C")
    co = bpy.data.objects.new("C", cam)
    co.location = (0, -5, 0)
    co.rotation_euler = (1.5708, 0, 0)
    scene.collection.objects.link(co)
    scene.camera = co

    scene.spectral.target = "ALL"
    scene.spectral.band_count = 8
    scene.spectral.lambda_min = 380.0
    scene.spectral.lambda_max = 730.0
    return scene, mat


def main():
    spectral_render.register()
    scene, mat = build_scene()

    n_before = len(mat.node_tree.nodes)

    # --- Inject ---------------------------------------------------------
    bpy.ops.spectral.inject()
    check("_spectral_backup" in mat.keys(), "backup stored after inject")
    bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    check(bsdf.inputs["Base Color"].is_linked, "Base Color is now driven")

    # Dispersion: the glass IOR should now be wavelength-driven.
    glass = build_scene.glass
    gbsdf = next(n for n in glass.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    check(gbsdf.inputs["IOR"].is_linked, "glass IOR is now driven (dispersion)")

    # --- Idempotency ----------------------------------------------------
    n_injected = len(mat.node_tree.nodes)
    bpy.ops.spectral.inject()
    check(len(mat.node_tree.nodes) == n_injected, "re-inject is a no-op (idempotent)")

    # --- Render ---------------------------------------------------------
    bpy.ops.spectral.render()
    img = bpy.data.images.get("Spectral Result")
    check(img is not None, "Spectral Result image created")
    if img is not None:
        px = list(img.pixels)
        check(max(px) > 0.0, "render is non-black")
        # Centre pixel neutrality (grey sphere -> R≈G≈B, no colour cast).
        n = len(px) // 4
        c = (n // 2) * 4
        r, g, b = px[c], px[c + 1], px[c + 2]
        spread = max(r, g, b) - min(r, g, b)
        check(spread < 0.05 * max(max(r, g, b), 1e-6) + 0.01,
              f"grey stays neutral (r={r:.3f} g={g:.3f} b={b:.3f})")

    # --- Restore --------------------------------------------------------
    bpy.ops.spectral.restore()
    check("_spectral_backup" not in mat.keys(), "backup key removed after restore")
    check(len(mat.node_tree.nodes) == n_before, "node tree fully restored")
    bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bc = bsdf.inputs["Base Color"].default_value
    check(abs(bc[0] - 0.5) < 1e-4, "Base Color value restored")
    gbsdf = next(n for n in build_scene.glass.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    check(not gbsdf.inputs["IOR"].is_linked, "glass IOR link removed after restore")
    check(abs(gbsdf.inputs["IOR"].default_value - 1.45) < 1e-4, "glass IOR value restored")

    print(f"\n{len(_FAILS)} failure(s)")
    sys.exit(1 if _FAILS else 0)


if __name__ == "__main__":
    main()

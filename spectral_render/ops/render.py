"""Spectral render: per-band monochrome renders accumulated in CIE XYZ."""

from __future__ import annotations

import os
import shutil
import tempfile

import bpy
import numpy as np

from .. import properties
from ..core import cmf, spd

RESULT_IMAGE = "Spectral Result"


def _force_lambda_update(scene, lam: float) -> None:
    """Set the global wavelength and force drivers/depsgraph to re-evaluate."""
    scene["spectral_lambda"] = float(lam)
    scene.view_layers[0].update()
    # frame_set re-evaluates animation + drivers (spec-endorsed forced update).
    scene.frame_set(scene.frame_current)


def _render_band_to_array(scene, filepath: str) -> np.ndarray:
    """Render the current state to an EXR and return its R channel as ``(n,)``."""
    scene.render.filepath = filepath
    bpy.ops.render.render(write_still=True)
    real = filepath + ".exr" if not filepath.lower().endswith(".exr") else filepath
    img = bpy.data.images.load(real)
    try:
        buf = np.empty(len(img.pixels), dtype=np.float32)
        img.pixels.foreach_get(buf)
    finally:
        bpy.data.images.remove(img)
    return buf.reshape(-1, 4)[:, 0].astype(np.float64)


def _get_result_image(width: int, height: int) -> bpy.types.Image:
    img = bpy.data.images.get(RESULT_IMAGE)
    if img is not None and tuple(img.size) != (width, height):
        bpy.data.images.remove(img)
        img = None
    if img is None:
        img = bpy.data.images.new(RESULT_IMAGE, width, height, float_buffer=True)
    return img


class SPECTRAL_OT_render(bpy.types.Operator):
    bl_idname = "spectral.render"
    bl_label = "Spectral Render"
    bl_description = "Render each wavelength band and composite to CIE XYZ -> sRGB"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        s = context.scene.spectral
        return s.lambda_min < s.lambda_max and s.band_count >= 3

    def execute(self, context):
        scene = context.scene
        settings = scene.spectral
        properties.ensure_spectral_lambda(scene)

        wavelengths, dlam = properties.band_wavelengths(settings)
        white = spd.reference_white_xyz(settings.illuminant, wavelengths, dlam)
        if white[1] <= 0.0:
            self.report({"ERROR"}, "Illuminant Y integral is zero; check λ range")
            return {"CANCELLED"}

        # Snapshot the render settings we mutate, restore them in finally.
        rs = scene.render
        img_set = rs.image_settings
        saved = {
            "filepath": rs.filepath,
            "file_format": img_set.file_format,
            "color_mode": img_set.color_mode,
            "color_depth": img_set.color_depth,
            "use_file_extension": rs.use_file_extension,
            "samples": getattr(scene.cycles, "samples", None),
            "frame": scene.frame_current,
            "lambda": scene["spectral_lambda"],
        }
        tmpdir = tempfile.mkdtemp(prefix="spectral_")
        wm = context.window_manager
        n = len(wavelengths)
        wm.progress_begin(0, n)
        try:
            img_set.file_format = "OPEN_EXR"
            img_set.color_mode = "RGB"
            img_set.color_depth = "32"
            rs.use_file_extension = True
            if saved["samples"] is not None:
                scene.cycles.samples = settings.samples_per_band

            xyz_accum = None
            for i, lam in enumerate(wavelengths):
                _force_lambda_update(scene, lam)
                grey = _render_band_to_array(
                    scene, os.path.join(tmpdir, f"band_{i:03d}")
                )
                if xyz_accum is None:
                    xyz_accum = np.zeros((grey.shape[0], 3), dtype=np.float64)
                weight = cmf.cmf_at(lam) * spd.spd_at(lam, settings.illuminant) * dlam
                xyz_accum += grey[:, None] * weight[None, :]
                wm.progress_update(i + 1)

            xyz_accum /= white[1]
            rgb = np.clip(cmf.xyz_to_linear_srgb(xyz_accum), 0.0, None)

            # Effective output resolution (matches Blender's percentage flooring).
            pct = rs.resolution_percentage
            width = (rs.resolution_x * pct) // 100
            height = (rs.resolution_y * pct) // 100
            count = rgb.shape[0]
            if width * height != count:   # metadata disagrees -> trust the buffer
                height = max(1, count // max(1, width))
            out = np.ones((count, 4), dtype=np.float32)
            out[:, :3] = rgb
            result = _get_result_image(width, height)
            result.pixels.foreach_set(out.ravel())
            result.update()
        finally:
            wm.progress_end()
            rs.filepath = saved["filepath"]
            img_set.file_format = saved["file_format"]
            img_set.color_mode = saved["color_mode"]
            img_set.color_depth = saved["color_depth"]
            rs.use_file_extension = saved["use_file_extension"]
            if saved["samples"] is not None:
                scene.cycles.samples = saved["samples"]
            scene["spectral_lambda"] = saved["lambda"]
            scene.frame_set(saved["frame"])
            shutil.rmtree(tmpdir, ignore_errors=True)

        self.report({"INFO"}, f"Spectral render done: {n} bands -> '{RESULT_IMAGE}'")
        return {"FINISHED"}


def register():
    bpy.utils.register_class(SPECTRAL_OT_render)


def unregister():
    bpy.utils.unregister_class(SPECTRAL_OT_render)

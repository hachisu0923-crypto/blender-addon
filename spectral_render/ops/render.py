"""Spectral render: per-band monochrome renders accumulated in CIE XYZ."""

from __future__ import annotations

import os
import shutil
import tempfile
import time

import bpy
import numpy as np

from .. import properties
from ..core import cmf, sampling
from ..io import exr

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


def _output_resolution(rs, count):
    pct = rs.resolution_percentage
    width = (rs.resolution_x * pct) // 100
    height = (rs.resolution_y * pct) // 100
    if width * height != count:        # metadata disagrees -> trust the buffer
        height = max(1, count // max(1, width))
    return width, height


def _composite_frame(scene, settings, wavelengths, weights, white, tmpdir, wm, progress):
    """Render all bands for the current frame and write the result image.

    ``progress`` is a callback ``(done, total, eta_seconds)`` for status. Returns
    the result :class:`bpy.types.Image`.
    """
    n = len(wavelengths)
    xyz_accum = None
    band_cache = [] if settings.save_band_exrs else None
    t0 = time.time()
    for i, lam in enumerate(wavelengths):
        _force_lambda_update(scene, lam)
        grey = _render_band_to_array(scene, os.path.join(tmpdir, f"band_{i:03d}"))
        if xyz_accum is None:
            xyz_accum = np.zeros((grey.shape[0], 3), dtype=np.float64)
        xyz_accum += grey[:, None] * weights[i][None, :]
        if band_cache is not None:
            band_cache.append((i, float(lam), grey.astype(np.float32)))
        elapsed = time.time() - t0
        eta = elapsed / (i + 1) * (n - i - 1)
        progress(i + 1, n, eta)

    xyz_accum /= white[1]
    # Scene-linear sRGB; Blender's view transform (AgX/Filmic/Standard) applies
    # on display, so the float result stays OCIO-consistent.
    rgb = np.clip(cmf.xyz_to_linear_srgb(xyz_accum), 0.0, None)

    count = rgb.shape[0]
    width, height = _output_resolution(scene.render, count)
    out = np.ones((count, 4), dtype=np.float32)
    out[:, :3] = rgb
    result = _get_result_image(width, height)
    result.pixels.foreach_set(out.ravel())
    result.update()

    if band_cache:
        exr.write_band_exrs(settings.exr_dir, band_cache, width, height, scene)
    return result


class _RenderSettingsGuard:
    """Snapshot/restore the render settings the band loop mutates."""

    def __init__(self, scene, settings):
        self.scene = scene
        self.settings = settings
        self.rs = scene.render
        self.img_set = self.rs.image_settings

    def __enter__(self):
        rs, img = self.rs, self.img_set
        self.saved = {
            "filepath": rs.filepath,
            "file_format": img.file_format,
            "color_mode": img.color_mode,
            "color_depth": img.color_depth,
            "use_file_extension": rs.use_file_extension,
            "samples": getattr(self.scene.cycles, "samples", None),
            "frame": self.scene.frame_current,
            "lambda": self.scene["spectral_lambda"],
        }
        img.file_format = "OPEN_EXR"
        img.color_mode = "RGB"
        img.color_depth = "32"
        rs.use_file_extension = True
        if self.saved["samples"] is not None:
            self.scene.cycles.samples = self.settings.samples_per_band
        return self

    def __exit__(self, *exc):
        rs, img, s = self.rs, self.img_set, self.saved
        rs.filepath = s["filepath"]
        img.file_format = s["file_format"]
        img.color_mode = s["color_mode"]
        img.color_depth = s["color_depth"]
        rs.use_file_extension = s["use_file_extension"]
        if s["samples"] is not None:
            self.scene.cycles.samples = s["samples"]
        self.scene["spectral_lambda"] = s["lambda"]
        self.scene.frame_set(s["frame"])
        return False


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

        wavelengths, weights, white = sampling.get_samples(settings)
        if white[1] <= 0.0:
            self.report({"ERROR"}, "Illuminant Y integral is zero; check λ range")
            return {"CANCELLED"}

        wm = context.window_manager
        n = len(wavelengths)
        wm.progress_begin(0, n)
        tmpdir = tempfile.mkdtemp(prefix="spectral_")

        def progress(done, total, eta):
            wm.progress_update(done)
            print(f"[spectral] band {done}/{total}  ETA {eta:5.1f}s")

        try:
            with _RenderSettingsGuard(scene, settings):
                _composite_frame(scene, settings, wavelengths, weights, white, tmpdir, wm, progress)
        finally:
            wm.progress_end()
            shutil.rmtree(tmpdir, ignore_errors=True)

        self.report({"INFO"}, f"Spectral render done: {n} bands -> '{RESULT_IMAGE}'")
        return {"FINISHED"}


class SPECTRAL_OT_render_animation(bpy.types.Operator):
    bl_idname = "spectral.render_animation"
    bl_label = "Spectral Render Animation"
    bl_description = "Spectral-composite every frame in the scene range and save to the output path"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        s = context.scene.spectral
        return s.lambda_min < s.lambda_max and s.band_count >= 3

    def execute(self, context):
        scene = context.scene
        settings = scene.spectral
        properties.ensure_spectral_lambda(scene)

        wavelengths, weights, white = sampling.get_samples(settings)
        if white[1] <= 0.0:
            self.report({"ERROR"}, "Illuminant Y integral is zero; check λ range")
            return {"CANCELLED"}

        frames = range(scene.frame_start, scene.frame_end + 1)
        wm = context.window_manager
        total = len(frames) * len(wavelengths)
        wm.progress_begin(0, total)
        tmpdir = tempfile.mkdtemp(prefix="spectral_")
        base = bpy.path.abspath(settings.exr_dir if settings.save_band_exrs else "//spectral_anim/")
        os.makedirs(base, exist_ok=True)
        saved_frame = scene.frame_current
        done_frames = 0
        try:
            with _RenderSettingsGuard(scene, settings):
                for fi, frame in enumerate(frames):
                    scene.frame_set(frame)

                    def progress(done, n, eta, _fi=fi):
                        wm.progress_update(_fi * len(wavelengths) + done)

                    result = _composite_frame(
                        scene, settings, wavelengths, weights, white, tmpdir, wm, progress
                    )
                    # Save the composited frame as a scene-linear EXR.
                    out_path = os.path.join(base, f"spectral_{frame:04d}.exr")
                    result.save_render(out_path, scene=scene)
                    done_frames += 1
        finally:
            wm.progress_end()
            scene.frame_set(saved_frame)
            shutil.rmtree(tmpdir, ignore_errors=True)

        self.report({"INFO"}, f"Spectral animation done: {done_frames} frames -> {base}")
        return {"FINISHED"}


_CLASSES = (SPECTRAL_OT_render, SPECTRAL_OT_render_animation)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)

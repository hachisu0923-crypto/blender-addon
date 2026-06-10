"""Convenience operators: apply catalogue glass presets to a material."""

from __future__ import annotations

import bpy

from .. import properties


class SPECTRAL_OT_apply_glass_preset(bpy.types.Operator):
    bl_idname = "spectral.apply_glass_preset"
    bl_label = "Apply Glass Preset"
    bl_description = "Fill IOR (n_d) and Abbe number from the selected glass preset"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.active_material is not None

    def execute(self, context):
        ms = context.object.active_material.spectral
        n_d, v_d = properties.GLASS_PRESETS[ms.glass_preset]
        ms.dispersion_enabled = True
        ms.dispersion_mode = "ABBE"
        ms.ior_d = n_d
        ms.abbe = v_d
        self.report({"INFO"}, f"Applied {ms.glass_preset}: n_d={n_d}, V_d={v_d}")
        return {"FINISHED"}


def register():
    bpy.utils.register_class(SPECTRAL_OT_apply_glass_preset)


def unregister():
    bpy.utils.unregister_class(SPECTRAL_OT_apply_glass_preset)

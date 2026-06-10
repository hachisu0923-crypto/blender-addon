"""3D viewport N-panel for the Spectral Render addon."""

from __future__ import annotations

import bpy


class VIEW3D_PT_spectral(bpy.types.Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Spectral"
    bl_label = "Spectral Render"

    def draw(self, context):
        layout = self.layout
        s = context.scene.spectral

        col = layout.column(align=True)
        col.prop(s, "lambda_min")
        col.prop(s, "lambda_max")
        col.prop(s, "band_count")
        col.prop(s, "samples_per_band")

        layout.prop(s, "illuminant")
        if s.illuminant == "BLACKBODY":
            layout.prop(s, "color_temperature")
        layout.prop(s, "target")

        col = layout.column(align=True)
        col.operator("spectral.inject", text="Inject Spectral Nodes", icon="NODETREE")
        col.operator("spectral.restore", text="Restore", icon="LOOP_BACK")
        col.operator("spectral.render", text="Spectral Render", icon="RENDER_STILL")

        lam = context.scene.get("spectral_lambda")
        if lam is not None:
            box = layout.box()
            box.label(text=f"Current λ: {lam:.1f} nm")
            if s.band_count:
                box.label(text=f"Δλ: {(s.lambda_max - s.lambda_min) / s.band_count:.1f} nm")


class VIEW3D_PT_spectral_material(bpy.types.Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Spectral"
    bl_label = "Material Dispersion"
    bl_parent_id = "VIEW3D_PT_spectral"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj is not None and obj.active_material is not None

    def draw(self, context):
        layout = self.layout
        mat = context.object.active_material
        ms = mat.spectral
        layout.label(text=mat.name, icon="MATERIAL")
        layout.prop(ms, "dispersion_enabled")

        col = layout.column()
        col.enabled = ms.dispersion_enabled
        col.prop(ms, "dispersion_mode")
        if ms.dispersion_mode == "ABBE":
            col.prop(ms, "ior_d")
            col.prop(ms, "abbe")
        else:
            col.prop(ms, "cauchy_a")
            col.prop(ms, "cauchy_b")
            col.prop(ms, "cauchy_c")


_CLASSES = (VIEW3D_PT_spectral, VIEW3D_PT_spectral_material)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)

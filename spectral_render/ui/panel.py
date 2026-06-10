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


def register():
    bpy.utils.register_class(VIEW3D_PT_spectral)


def unregister():
    bpy.utils.unregister_class(VIEW3D_PT_spectral)

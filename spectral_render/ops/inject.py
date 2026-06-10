"""Non-destructive injection of SpectralColor nodes into materials."""

from __future__ import annotations

import json

import bpy

from .. import properties
from ..core import jakob_hanika, node_group

BACKUP_KEY = "_spectral_backup"


def iter_target_materials(context):
    """Yield unique, editable materials per the scene's target mode."""
    settings = context.scene.spectral
    seen = set()
    if settings.target == "ALL":
        mats = list(bpy.data.materials)
    else:
        mats = []
        for obj in context.selected_objects:
            for slot in getattr(obj, "material_slots", []):
                if slot.material is not None:
                    mats.append(slot.material)
    for mat in mats:
        if mat is None or id(mat) in seen:
            continue
        seen.add(id(mat))
        if mat.library is not None:          # linked library data is read-only
            continue
        if not mat.use_nodes or mat.node_tree is None:
            continue
        yield mat


def _find_principled(node_tree):
    for n in node_tree.nodes:
        if n.type == "BSDF_PRINCIPLED":
            return n
    return None


def inject_material(mat, scene) -> str:
    """Inject one material. Returns 'injected', 'skipped' or 'no-bsdf'."""
    if BACKUP_KEY in mat.keys():
        return "skipped"                     # idempotent: already injected

    nt = mat.node_tree
    bsdf = _find_principled(nt)
    if bsdf is None:
        return "no-bsdf"
    socket = bsdf.inputs["Base Color"]

    backup = {
        "version": 1,
        "bsdf_node": bsdf.name,
        "socket": "Base Color",
        "linked": socket.is_linked,
        "source_node": None,
        "source_socket": None,
        "default_value": list(socket.default_value),
        "injected_nodes": [],
    }
    if socket.is_linked:
        link = socket.links[0]
        backup["source_node"] = link.from_node.name
        backup["source_socket"] = link.from_socket.identifier

    # Fit the constant Base Color (linear sRGB). Linked textures fall back to the
    # socket default in Phase 1 (only the constant colour is uplifted).
    rgb = tuple(socket.default_value[:3])
    coeffs = jakob_hanika.rgb_to_coeffs(rgb, scene.spectral.illuminant)

    inst = node_group.build_instance(
        nt, scene, coeffs, location=(bsdf.location.x - 400, bsdf.location.y)
    )
    backup["injected_nodes"] = inst["nodes"]

    for link in list(socket.links):
        nt.links.remove(link)
    nt.links.new(inst["output_socket"], socket)

    mat[BACKUP_KEY] = json.dumps(backup)
    return "injected"


class SPECTRAL_OT_inject(bpy.types.Operator):
    bl_idname = "spectral.inject"
    bl_label = "Inject Spectral Nodes"
    bl_description = "Replace Base Color with a wavelength-driven SpectralColor node (non-destructive)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        properties.ensure_spectral_lambda(scene)
        counts = {"injected": 0, "skipped": 0, "no-bsdf": 0}
        for mat in iter_target_materials(context):
            counts[inject_material(mat, scene)] += 1
        self.report(
            {"INFO"},
            f"Spectral: injected {counts['injected']}, skipped {counts['skipped']}, "
            f"no Principled BSDF {counts['no-bsdf']}",
        )
        return {"FINISHED"}


def register():
    bpy.utils.register_class(SPECTRAL_OT_inject)


def unregister():
    bpy.utils.unregister_class(SPECTRAL_OT_inject)

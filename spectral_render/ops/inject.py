"""Non-destructive injection of SpectralColor / SpectralIOR nodes."""

from __future__ import annotations

import json

import bpy

from .. import properties
from ..core import jakob_hanika, node_group

BACKUP_KEY = "_spectral_backup"

# Node types whose IOR input we drive for dispersion.
_IOR_NODE_TYPES = {"BSDF_GLASS", "BSDF_REFRACTION", "BSDF_PRINCIPLED"}


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


def _socket_default(socket):
    dv = socket.default_value
    try:
        return list(dv)
    except TypeError:
        return float(dv)


def _record(socket, injected_nodes) -> dict:
    rec = {
        "bsdf_node": socket.node.name,
        "socket": socket.identifier,
        "linked": socket.is_linked,
        "source_node": None,
        "source_socket": None,
        "default_value": _socket_default(socket),
        "injected_nodes": injected_nodes,
    }
    if socket.is_linked:
        link = socket.links[0]
        rec["source_node"] = link.from_node.name
        rec["source_socket"] = link.from_socket.identifier
    return rec


def _record_and_replace(node_tree, socket, new_output, injected_nodes) -> dict:
    """Record a socket's original state, then rewire it to ``new_output``."""
    rec = _record(socket, injected_nodes)
    for link in list(socket.links):
        node_tree.links.remove(link)
    node_tree.links.new(new_output, socket)
    return rec


def _record_and_set(node_tree, socket, new_value) -> dict:
    """Record a socket's original state, then set a constant value (no nodes)."""
    rec = _record(socket, [])
    for link in list(socket.links):
        node_tree.links.remove(link)
    socket.default_value = new_value
    return rec


def inject_material(mat, scene) -> str:
    """Inject one material. Returns 'injected', 'skipped' or 'no-target'."""
    if BACKUP_KEY in mat.keys():
        return "skipped"                     # idempotent: already injected

    nt = mat.node_tree
    sets = scene.spectral
    temp = sets.color_temperature
    records = []

    # --- Base Color: spectral metal reflectance OR RGB uplift -------------
    bsdf = _find_principled(nt)
    if bsdf is not None:
        socket = bsdf.inputs["Base Color"]
        loc = (bsdf.location.x - 400, bsdf.location.y)
        if mat.spectral.metal_enabled:
            inst = node_group.build_metal_instance(nt, scene, mat.spectral.metal, location=loc)
        else:
            rgb = tuple(socket.default_value[:3])
            coeffs = jakob_hanika.rgb_to_coeffs(rgb, sets.illuminant, temp)
            inst = node_group.build_instance(nt, scene, coeffs, location=loc)
        records.append(_record_and_replace(nt, socket, inst["output_socket"], inst["nodes"]))

    # --- Dispersion (IOR) -------------------------------------------------
    if mat.spectral.dispersion_enabled:
        abc = properties.dispersion_coeffs(mat.spectral)
        for node in list(nt.nodes):
            if node.type not in _IOR_NODE_TYPES:
                continue
            ior_in = node.inputs.get("IOR")
            if ior_in is None:
                continue
            inst = node_group.build_ior_instance(
                nt, scene, abc, location=(node.location.x - 400, node.location.y - 300)
            )
            records.append(_record_and_replace(nt, ior_in, inst["output_socket"], inst["nodes"]))

    # --- Volume absorption (tinted media) ---------------------------------
    if mat.spectral.volume_enabled:
        tint = tuple(mat.spectral.volume_tint)
        for node in list(nt.nodes):
            if node.type not in {"VOLUME_ABSORPTION", "VOLUME_SCATTER"}:
                continue
            dens = node.inputs.get("Density")
            col = node.inputs.get("Color")
            if dens is not None:
                inst = node_group.build_volume_density_instance(
                    nt, scene, tint, mat.spectral.volume_density, sets.illuminant, temp,
                    location=(node.location.x - 400, node.location.y - 200),
                )
                records.append(_record_and_replace(nt, dens, inst["output_socket"], inst["nodes"]))
            if col is not None:
                records.append(_record_and_set(nt, col, [1.0, 1.0, 1.0, 1.0]))

    if not records:
        return "no-target"

    mat[BACKUP_KEY] = json.dumps({"version": 2, "sockets": records})
    return "injected"


class SPECTRAL_OT_inject(bpy.types.Operator):
    bl_idname = "spectral.inject"
    bl_label = "Inject Spectral Nodes"
    bl_description = "Replace Base Color (and dispersion IOR) with wavelength-driven nodes"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        properties.ensure_spectral_lambda(scene)
        counts = {"injected": 0, "skipped": 0, "no-target": 0}
        for mat in iter_target_materials(context):
            counts[inject_material(mat, scene)] += 1
        self.report(
            {"INFO"},
            f"Spectral: injected {counts['injected']}, skipped {counts['skipped']}, "
            f"no target {counts['no-target']}",
        )
        return {"FINISHED"}


def register():
    bpy.utils.register_class(SPECTRAL_OT_inject)


def unregister():
    bpy.utils.unregister_class(SPECTRAL_OT_inject)

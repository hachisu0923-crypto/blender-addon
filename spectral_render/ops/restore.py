"""Restore materials to their pre-injection state."""

from __future__ import annotations

import json

import bpy

from ..core import node_group
from .inject import BACKUP_KEY, iter_target_materials


def _restore_record(nt, rec) -> None:
    node = nt.nodes.get(rec["bsdf_node"])
    socket = None
    if node is not None:
        socket = next((s for s in node.inputs if s.identifier == rec["socket"]), None)
        if socket is None:
            socket = node.inputs.get(rec["socket"])   # fallback by name (v1 backups)

    # Remove the injected link into the target socket.
    if socket is not None:
        for link in list(socket.links):
            nt.links.remove(link)

    # Delete exactly the nodes we added.
    for name in rec["injected_nodes"]:
        n = nt.nodes.get(name)
        if n is not None:
            nt.nodes.remove(n)

    # Restore the original connection / value.
    if socket is not None:
        restored_link = False
        if rec["linked"] and rec["source_node"]:
            src = nt.nodes.get(rec["source_node"])
            if src is not None:
                out = next(
                    (s for s in src.outputs if s.identifier == rec["source_socket"]), None
                )
                if out is not None:
                    nt.links.new(out, socket)
                    restored_link = True
        if not restored_link:
            socket.default_value = rec["default_value"]


def restore_material(mat) -> str:
    """Restore one material. Returns 'restored' or 'skipped'."""
    if BACKUP_KEY not in mat.keys():
        return "skipped"

    data = json.loads(mat[BACKUP_KEY])
    records = data["sockets"] if data.get("version", 1) >= 2 else [data]
    nt = mat.node_tree
    for rec in records:
        _restore_record(nt, rec)

    del mat[BACKUP_KEY]
    return "restored"


class SPECTRAL_OT_restore(bpy.types.Operator):
    bl_idname = "spectral.restore"
    bl_label = "Restore"
    bl_description = "Remove injected spectral nodes and restore the original inputs"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        counts = {"restored": 0, "skipped": 0}
        for mat in iter_target_materials(context):
            counts[restore_material(mat)] += 1
        node_group.cleanup_groups_if_unused()
        self.report(
            {"INFO"},
            f"Spectral: restored {counts['restored']}, skipped {counts['skipped']}",
        )
        return {"FINISHED"}


def register():
    bpy.utils.register_class(SPECTRAL_OT_restore)


def unregister():
    bpy.utils.unregister_class(SPECTRAL_OT_restore)

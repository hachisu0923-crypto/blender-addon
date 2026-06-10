"""Build and manage the "SpectralColor" shader node group.

The shared group computes the wavelength-dependent reflectance::

    lam_hat = (Lambda - 360) / 470
    x       = c2*lam_hat^2 + c1*lam_hat + c0        # Horner form
    Refl    = 0.5 + x / (2*sqrt(1 + x^2))           # sigmoid

``Lambda`` is driven globally by ``scene['spectral_lambda']``; ``c0/c1/c2`` are
baked per material as Value nodes from :func:`core.jakob_hanika.rgb_to_coeffs`.

This is the only ``core`` module that imports ``bpy``.
"""

from __future__ import annotations

import bpy

GROUP_NAME = "SpectralColor"
INJECT_TAG = "_spectral"  # custom prop set on every node we add (for cleanup)


def get_or_create_group() -> bpy.types.NodeTree:
    """Return the shared SpectralColor node group, building it once if needed."""
    ng = bpy.data.node_groups.get(GROUP_NAME)
    if ng is not None:
        return ng

    ng = bpy.data.node_groups.new(GROUP_NAME, "ShaderNodeTree")
    iface = ng.interface
    iface.new_socket("Lambda", in_out="INPUT", socket_type="NodeSocketFloat")
    iface.new_socket("c0", in_out="INPUT", socket_type="NodeSocketFloat")
    iface.new_socket("c1", in_out="INPUT", socket_type="NodeSocketFloat")
    iface.new_socket("c2", in_out="INPUT", socket_type="NodeSocketFloat")
    iface.new_socket("Reflectance", in_out="OUTPUT", socket_type="NodeSocketFloat")

    nodes = ng.nodes
    links = ng.links
    gin = nodes.new("NodeGroupInput")
    gin.location = (-600, 0)
    gout = nodes.new("NodeGroupOutput")
    gout.location = (600, 0)

    def math(op, x=-400, y=0):
        n = nodes.new("ShaderNodeMath")
        n.operation = op
        n.location = (x, y)
        return n

    # lam_hat = Lambda * (1/470) + (-360/470)
    lam_hat = math("MULTIPLY_ADD", -400, 200)
    lam_hat.inputs[1].default_value = 1.0 / 470.0
    lam_hat.inputs[2].default_value = -360.0 / 470.0
    links.new(gin.outputs["Lambda"], lam_hat.inputs[0])

    # p1 = lam_hat * c2 + c1
    p1 = math("MULTIPLY_ADD", -200, 100)
    links.new(lam_hat.outputs[0], p1.inputs[0])
    links.new(gin.outputs["c2"], p1.inputs[1])
    links.new(gin.outputs["c1"], p1.inputs[2])

    # x = lam_hat * p1 + c0
    x = math("MULTIPLY_ADD", 0, 100)
    links.new(lam_hat.outputs[0], x.inputs[0])
    links.new(p1.outputs[0], x.inputs[1])
    links.new(gin.outputs["c0"], x.inputs[2])

    # sigmoid(x) = 0.5 + x / (2*sqrt(1 + x^2))
    x2 = math("MULTIPLY", 0, -100)
    links.new(x.outputs[0], x2.inputs[0])
    links.new(x.outputs[0], x2.inputs[1])

    onep = math("ADD", 150, -100)
    links.new(x2.outputs[0], onep.inputs[0])
    onep.inputs[1].default_value = 1.0

    sq = math("SQRT", 300, -100)
    links.new(onep.outputs[0], sq.inputs[0])

    twos = math("MULTIPLY", 300, -250)
    links.new(sq.outputs[0], twos.inputs[0])
    twos.inputs[1].default_value = 2.0

    half = math("DIVIDE", 420, 0)
    links.new(x.outputs[0], half.inputs[0])
    links.new(twos.outputs[0], half.inputs[1])

    out = math("ADD", 540, 0)
    links.new(half.outputs[0], out.inputs[0])
    out.inputs[1].default_value = 0.5

    links.new(out.outputs[0], gout.inputs["Reflectance"])
    return ng


def add_lambda_driver(value_node: bpy.types.Node, scene: bpy.types.Scene) -> None:
    """Drive a Value node's output from ``scene['spectral_lambda']``."""
    fcurve = value_node.outputs[0].driver_add("default_value")
    drv = fcurve.driver
    drv.type = "SCRIPTED"
    var = drv.variables.new()
    var.name = "lam"
    var.type = "SINGLE_PROP"
    tgt = var.targets[0]
    tgt.id_type = "SCENE"
    tgt.id = scene
    tgt.data_path = '["spectral_lambda"]'
    drv.expression = "lam"


def build_instance(node_tree, scene, coeffs, location=(0.0, 0.0)) -> dict:
    """Insert a SpectralColor instance into ``node_tree``.

    Adds the group node, three baked coefficient Value nodes, one λ-driven Value
    node and a Combine Color node that broadcasts the scalar reflectance to RGB.
    Every added node is tagged with :data:`INJECT_TAG`.

    Returns a dict with the created node names and the ``output_socket`` to wire
    into Base Color.
    """
    nodes = node_tree.nodes
    links = node_tree.links
    bx, by = location
    created = []

    def tag(n):
        n[INJECT_TAG] = True
        created.append(n.name)
        return n

    grp = tag(nodes.new("ShaderNodeGroup"))
    grp.node_tree = get_or_create_group()
    grp.label = "Spectral Color"
    grp.location = (bx - 200, by)

    # Baked coefficients.
    for i, key in enumerate(("c0", "c1", "c2")):
        v = tag(nodes.new("ShaderNodeValue"))
        v.label = f"spectral {key}"
        v.location = (bx - 460, by - 60 - i * 120)
        v.outputs[0].default_value = float(coeffs[i])
        links.new(v.outputs[0], grp.inputs[key])

    # Globally driven wavelength.
    lam = tag(nodes.new("ShaderNodeValue"))
    lam.label = "spectral λ"
    lam.location = (bx - 460, by + 120)
    add_lambda_driver(lam, scene)
    links.new(lam.outputs[0], grp.inputs["Lambda"])

    # Scalar reflectance -> grey RGB.
    comb = tag(nodes.new("ShaderNodeCombineColor"))
    comb.mode = "RGB"
    comb.location = (bx, by)
    for ch in range(3):
        links.new(grp.outputs["Reflectance"], comb.inputs[ch])

    return {"nodes": created, "output_socket": comb.outputs[0]}


def cleanup_group_if_unused() -> None:
    """Remove the shared group datablock once nothing references it."""
    ng = bpy.data.node_groups.get(GROUP_NAME)
    if ng is not None and ng.users == 0:
        bpy.data.node_groups.remove(ng)

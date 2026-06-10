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
import numpy as np

from . import metals

GROUP_NAME = "SpectralColor"
IOR_GROUP_NAME = "SpectralIOR"
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


def get_or_create_ior_group() -> bpy.types.NodeTree:
    """Cauchy refractive index group: n = A + B/λ_um² + C/λ_um⁴."""
    ng = bpy.data.node_groups.get(IOR_GROUP_NAME)
    if ng is not None:
        return ng

    ng = bpy.data.node_groups.new(IOR_GROUP_NAME, "ShaderNodeTree")
    iface = ng.interface
    iface.new_socket("Lambda", in_out="INPUT", socket_type="NodeSocketFloat")
    iface.new_socket("A", in_out="INPUT", socket_type="NodeSocketFloat")
    iface.new_socket("B", in_out="INPUT", socket_type="NodeSocketFloat")
    iface.new_socket("C", in_out="INPUT", socket_type="NodeSocketFloat")
    iface.new_socket("IOR", in_out="OUTPUT", socket_type="NodeSocketFloat")

    nodes, links = ng.nodes, ng.links
    gin = nodes.new("NodeGroupInput"); gin.location = (-600, 0)
    gout = nodes.new("NodeGroupOutput"); gout.location = (600, 0)

    def math(op, x=0, y=0):
        n = nodes.new("ShaderNodeMath")
        n.operation = op
        n.location = (x, y)
        return n

    lam_um = math("MULTIPLY", -400, 200)        # λ_um = Lambda * 0.001
    links.new(gin.outputs["Lambda"], lam_um.inputs[0])
    lam_um.inputs[1].default_value = 0.001

    l2 = math("MULTIPLY", -200, 200)            # λ_um²
    links.new(lam_um.outputs[0], l2.inputs[0])
    links.new(lam_um.outputs[0], l2.inputs[1])

    l4 = math("MULTIPLY", -200, 40)             # λ_um⁴
    links.new(l2.outputs[0], l4.inputs[0])
    links.new(l2.outputs[0], l4.inputs[1])

    b_term = math("DIVIDE", 0, 120)             # B / λ_um²
    links.new(gin.outputs["B"], b_term.inputs[0])
    links.new(l2.outputs[0], b_term.inputs[1])

    c_term = math("DIVIDE", 0, -40)             # C / λ_um⁴
    links.new(gin.outputs["C"], c_term.inputs[0])
    links.new(l4.outputs[0], c_term.inputs[1])

    s1 = math("ADD", 250, 100)                  # A + B/λ²
    links.new(gin.outputs["A"], s1.inputs[0])
    links.new(b_term.outputs[0], s1.inputs[1])

    s2 = math("ADD", 420, 60)                   # + C/λ⁴
    links.new(s1.outputs[0], s2.inputs[0])
    links.new(c_term.outputs[0], s2.inputs[1])

    links.new(s2.outputs[0], gout.inputs["IOR"])
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


def build_ior_instance(node_tree, scene, coeffs, location=(0.0, 0.0)) -> dict:
    """Insert a SpectralIOR instance: group node + baked A/B/C + driven λ.

    Returns ``{"nodes": [...], "output_socket": <IOR scalar>}``.
    """
    nodes, links = node_tree.nodes, node_tree.links
    bx, by = location
    created = []

    def tag(n):
        n[INJECT_TAG] = True
        created.append(n.name)
        return n

    grp = tag(nodes.new("ShaderNodeGroup"))
    grp.node_tree = get_or_create_ior_group()
    grp.label = "Spectral IOR"
    grp.location = (bx - 200, by)

    for i, key in enumerate(("A", "B", "C")):
        v = tag(nodes.new("ShaderNodeValue"))
        v.label = f"spectral {key}"
        v.location = (bx - 460, by - 60 - i * 120)
        v.outputs[0].default_value = float(coeffs[i])
        links.new(v.outputs[0], grp.inputs[key])

    lam = tag(nodes.new("ShaderNodeValue"))
    lam.label = "spectral λ"
    lam.location = (bx - 460, by + 120)
    add_lambda_driver(lam, scene)
    links.new(lam.outputs[0], grp.inputs["Lambda"])

    return {"nodes": created, "output_socket": grp.outputs["IOR"]}


def _driven_lambda_norm(nodes, links, scene, bx, by, tag):
    """Driven λ Value -> normalised (λ-360)/470. Returns the normalised socket."""
    lam = tag(nodes.new("ShaderNodeValue"))
    lam.label = "spectral λ"
    lam.location = (bx - 640, by + 120)
    add_lambda_driver(lam, scene)

    nrm = tag(nodes.new("ShaderNodeMath"))
    nrm.operation = "MULTIPLY_ADD"
    nrm.location = (bx - 460, by + 120)
    nrm.inputs[1].default_value = 1.0 / 470.0
    nrm.inputs[2].default_value = -360.0 / 470.0
    links.new(lam.outputs[0], nrm.inputs[0])
    return nrm.outputs[0]


def _float_curve(nodes, links, norm_socket, lam_grid, values, label, bx, by, tag):
    """Build a Float Curve mapping normalised λ -> values (clamped to [0,1])."""
    fc = tag(nodes.new("ShaderNodeFloatCurve"))
    fc.label = label
    fc.location = (bx - 300, by)
    fc.inputs[0].default_value = 1.0           # Factor = fully curve-mapped
    links.new(norm_socket, fc.inputs[1])

    xs = (np.asarray(lam_grid, dtype=np.float64) - 360.0) / 470.0
    ys = np.clip(np.asarray(values, dtype=np.float64), 0.0, 1.0)
    points = fc.mapping.curves[0].points
    points[0].location = (float(xs[0]), float(ys[0]))
    points[1].location = (float(xs[-1]), float(ys[-1]))
    for x, y in zip(xs[1:-1], ys[1:-1]):
        points.new(float(x), float(y))
    fc.mapping.update()
    return fc.outputs[0]


def _grey_combine(nodes, links, scalar_socket, bx, by, tag):
    comb = tag(nodes.new("ShaderNodeCombineColor"))
    comb.mode = "RGB"
    comb.location = (bx, by)
    for ch in range(3):
        links.new(scalar_socket, comb.inputs[ch])
    return comb.outputs[0]


def _curve_instance(node_tree, scene, lam_grid, values, label, location):
    """Driven λ -> Float Curve -> grey RGB. Shared by metal/spectrum builders."""
    nodes, links = node_tree.nodes, node_tree.links
    bx, by = location
    created = []

    def tag(n):
        n[INJECT_TAG] = True
        created.append(n.name)
        return n

    norm = _driven_lambda_norm(nodes, links, scene, bx, by, tag)
    curve = _float_curve(nodes, links, norm, lam_grid, values, label, bx, by, tag)
    out = _grey_combine(nodes, links, curve, bx, by, tag)
    return {"nodes": created, "output_socket": out}


def build_metal_instance(node_tree, scene, metal_name, location=(0.0, 0.0)) -> dict:
    """Insert a wavelength-driven metal reflectance (Fresnel R(λ)) as grey RGB.

    The host Principled BSDF should have Metallic = 1.
    """
    grid = np.arange(380.0, 781.0, 20.0)
    refl = metals.reflectance(metal_name, grid)
    return _curve_instance(node_tree, scene, grid, refl, f"R(λ) {metal_name}", location)


def build_spectrum_instance(node_tree, scene, lam_grid, reflectance, location=(0.0, 0.0)) -> dict:
    """Insert an arbitrary measured reflectance spectrum S(λ) as grey RGB."""
    return _curve_instance(node_tree, scene, lam_grid, reflectance, "S(λ) override", location)


def build_volume_density_instance(
    node_tree, scene, tint_rgb, density, illuminant, temperature, location=(0.0, 0.0)
) -> dict:
    """Insert a λ-driven volume absorption density into ``node_tree``.

    The absorption profile is ``a(λ) = 1 - S(λ)`` where ``S`` is the spectral
    uplift of the tint colour, baked into a Float Curve and scaled by ``density``.
    High absorption at wavelengths the tint does not reflect -> that colour
    survives transmission. The host volume node's Color should be white.
    Returns the density scalar output socket.
    """
    from . import jakob_hanika

    nodes, links = node_tree.nodes, node_tree.links
    bx, by = location
    created = []

    def tag(n):
        n[INJECT_TAG] = True
        created.append(n.name)
        return n

    coeffs = jakob_hanika.rgb_to_coeffs(tint_rgb, illuminant, temperature)
    grid = np.arange(380.0, 781.0, 20.0)
    absorption = 1.0 - jakob_hanika.reflectance(coeffs, grid)

    norm = _driven_lambda_norm(nodes, links, scene, bx, by, tag)
    curve = _float_curve(nodes, links, norm, grid, absorption, "absorption(λ)", bx, by, tag)

    scale = tag(nodes.new("ShaderNodeMath"))    # density * a(λ)
    scale.operation = "MULTIPLY"
    scale.location = (bx - 100, by)
    scale.inputs[1].default_value = float(density)
    links.new(curve, scale.inputs[0])

    return {"nodes": created, "output_socket": scale.outputs[0]}


def cleanup_groups_if_unused() -> None:
    """Remove the shared group datablocks once nothing references them."""
    for name in (GROUP_NAME, IOR_GROUP_NAME):
        ng = bpy.data.node_groups.get(name)
        if ng is not None and ng.users == 0:
            bpy.data.node_groups.remove(ng)

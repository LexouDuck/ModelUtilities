# SPDX-License-Identifier: GPL-3.0-or-later
"""Model Utilities: one-click fixes for imported / ripped / low-poly models.

Blender port of the Maya shelf scripts in maya/scripts/ (01 to 17). The two screenshot scripts
(18, 19) are covered by the separate "TMR Icons" add-on.

    Maya script                     Blender operator (model_utilities.*)
    01 AlphaNodeCorrect          -> alpha_node_correct     texture Alpha -> shader Alpha
    02 TransparencyCorrect       -> transparency_correct   Alpha fed by a texture's Color -> its Alpha
    03 UnfilterAllTextures       -> unfilter_textures      Image Texture interpolation: Closest
    04 FilterAllTextures         -> filter_textures        Image Texture interpolation: Linear
    05 MirrorAllTextureUVs       -> mirror_uvs             Image Texture extension: Mirror
    06 UnMirrorAllTextureUVs     -> unmirror_uvs           Image Texture extension: Mirror -> Repeat
    07 TileAllTextureUVs         -> tile_uvs               Image Texture extension: Repeat (keeps Mirror)
    08 UnTileAllTextureUVs       -> untile_uvs             Image Texture extension: Clip
    09 ShowVertexColors          -> show_vertex_colors     multiply color attribute into the material
    10 HideVertexColors          -> hide_vertex_colors     bypass that multiply
    11 NoShade                   -> no_shade               unlit (emission) shading
    12 Incandesce                -> incandesce             Solid viewport: Flat lighting + Texture
    13 CelShade                  -> cel_shade              3-step toon ramp (EEVEE)
       (new)                     -> restore_shading        undo No Shade / Cel Shade
    14 MergeAllVertices          -> merge_vertices         merge by distance (0.001)
    15 SoftenAllEdges            -> soften_edges           smooth shading, no sharp edges
    16 HardenAllEdges            -> harden_edges           flat shading
    17 FaceCameraAlways          -> face_camera            selected faces -> billboards tracking the camera

By default the operators affect the whole scene, like the Maya scripts. Set "Affect" to
"Selected" in the sidebar to limit them to the selected objects (and their materials).

UI: 3D Viewport sidebar (N) > "Model Utils" tab, the Object menu > Model Utilities,
and the operator search (F3).
"""

from contextlib import contextmanager

import bmesh
import bpy
from bpy.props import EnumProperty, FloatProperty, BoolProperty
from mathutils import Matrix, Vector


SHADE_PREFIX = "MU_Shade"   # nodes built by No Shade / Cel Shade (deleted by Restore Shading)
VCOL_PREFIX = "MU_VCol"     # vertex colour nodes inserted by Show Vertex Colors
ALPHA_PREFIX = "MU_Alpha"   # transparency mix inserted for shaders without an Alpha input
NODE_COLOR = (0.30, 0.42, 0.55)

COLOR_INPUTS = ("Base Color", "Color")


# --------------------------------------------------------------------------- scope helpers

def scope_objects(context, types=('MESH',)):
    if context.scene.model_utilities_scope == 'SELECTED':
        objs = context.selected_objects
    else:
        objs = context.scene.objects
    return [ob for ob in objs if ob.type in types]


def editable(id_data):
    return id_data is not None and id_data.library is None


def scope_materials(context):
    """Node-based materials used by the objects in scope, each listed once."""
    mats = []
    for ob in scope_objects(context, types=('MESH', 'CURVE', 'SURFACE', 'META', 'FONT')):
        for slot in ob.material_slots:
            mat = slot.material
            if (editable(mat) and mat.node_tree is not None and getattr(mat, "use_nodes", True)
                    and mat not in mats):
                mats.append(mat)
    return mats


def scope_meshes(context):
    """(object, mesh) pairs in scope, each mesh listed once."""
    seen, pairs = set(), []
    for ob in scope_objects(context):
        me = ob.data
        if editable(me) and me.name_full not in seen:
            seen.add(me.name_full)
            pairs.append((ob, me))
    return pairs


@contextmanager
def object_mode(context):
    """Leave Edit Mode (so mesh data is up to date) for the duration, then go back."""
    mode = context.object.mode if context.object else 'OBJECT'
    if mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    try:
        yield
    finally:
        if mode != 'OBJECT' and context.object is not None:
            try:
                bpy.ops.object.mode_set(mode=mode)
            except RuntimeError:
                pass


# --------------------------------------------------------------------------- node helpers

def iter_nodes(tree, _seen=None):
    """All nodes of a node tree, including the ones inside node groups."""
    _seen = set() if _seen is None else _seen
    if tree is None or tree.name_full in _seen:
        return
    _seen.add(tree.name_full)
    for node in tree.nodes:
        yield node
        if node.bl_idname == 'ShaderNodeGroup' and editable(node.node_tree):
            yield from iter_nodes(node.node_tree, _seen)


def image_nodes(mats):
    seen = set()
    for mat in mats:
        for node in iter_nodes(mat.node_tree):
            if node.bl_idname == 'ShaderNodeTexImage' and node.as_pointer() not in seen:
                seen.add(node.as_pointer())
                yield node


def socket(sockets, identifier):
    for s in sockets:
        if s.identifier == identifier:
            return s
    return None


def source(sock):
    """The output socket linked into `sock`, or None."""
    if sock is None or not sock.is_linked:
        return None
    links = sock.links
    return links[0].from_socket if links else None


def output_node(tree):
    outputs = [n for n in tree.nodes if n.bl_idname == 'ShaderNodeOutputMaterial']
    for n in outputs:
        if n.is_active_output:
            return n
    return outputs[0] if outputs else None


def trace_shader(tree):
    """Find the material's main shader, walking down from the output through Mix/Add shaders.

    Returns (output node, shader node, alpha socket). The alpha socket is the Fac input of a
    "Mix Shader(Transparent BSDF, shader)" on the way (the usual way importers do transparency),
    or None.
    """
    out = output_node(tree)
    if out is None:
        return None, None, None
    src = source(out.inputs.get("Surface"))
    node = src.node if src else None
    alpha = None
    visited = set()
    while node is not None and node.bl_idname in ('ShaderNodeMixShader', 'ShaderNodeAddShader') \
            and node.as_pointer() not in visited:
        visited.add(node.as_pointer())
        shader_ins = [s for s in node.inputs if s.type == 'SHADER']
        nodes = [source(s).node if source(s) else None for s in shader_ins]
        if (node.bl_idname == 'ShaderNodeMixShader' and len(nodes) == 2 and nodes[0] is not None
                and nodes[0].bl_idname == 'ShaderNodeBsdfTransparent'):
            alpha = node.inputs[0]
            node = nodes[1]
            continue
        candidates = [n for n in nodes if n is not None and n.bl_idname != 'ShaderNodeBsdfTransparent']
        node = candidates[0] if candidates else None
    return out, node, alpha


def color_input(shader):
    if shader is None:
        return None
    for name in COLOR_INPUTS:
        s = shader.inputs.get(name)
        if s is not None:
            return s
    return None


def find_upstream(sock, idname, depth=12):
    """First node of type `idname` found walking upstream from an input socket."""
    stack, seen = [(sock, 0)], set()
    while stack:
        s, d = stack.pop(0)
        src = source(s)
        if src is None or d > depth:
            continue
        node = src.node
        if node.as_pointer() in seen:
            continue
        seen.add(node.as_pointer())
        if node.bl_idname == idname:
            return node
        stack.extend((i, d + 1) for i in node.inputs)
    return None


def new_node(tree, idname, name, label, location):
    node = tree.nodes.new(idname)
    node.name = name
    node.label = label
    node.location = location
    node.use_custom_color = True
    node.color = NODE_COLOR
    return node


def link_or_set(tree, value, to_sock):
    """`value` is either an output socket (linked) or a plain value (copied)."""
    if value is None:
        return
    if isinstance(value, bpy.types.NodeSocket):
        tree.links.new(value, to_sock)
    else:
        try:
            to_sock.default_value = value
        except (TypeError, ValueError, AttributeError):
            pass


def socket_value(sock):
    """Linked source socket if any, else a copy of the socket's own value."""
    src = source(sock)
    if src is not None:
        return src
    v = sock.default_value
    try:
        return tuple(v)
    except TypeError:
        return v


def set_dithered(mat):
    """Order-independent transparency (Maya's 'depth peeling' equivalent)."""
    if hasattr(mat, "surface_render_method"):
        mat.surface_render_method = 'DITHERED'
    elif hasattr(mat, "blend_method"):
        mat.blend_method = 'HASHED'


# --------------------------------------------------------------------------- shading (No Shade / Cel Shade)

def remove_shading(mat):
    tree = mat.node_tree
    for node in [n for n in tree.nodes if n.name.startswith(SHADE_PREFIX)]:
        tree.nodes.remove(node)
    surface = mat.get("mu_surface")
    out = output_node(tree)
    if surface is not None and out is not None:
        node = tree.nodes.get(surface[0])
        if node is not None:
            sock = socket(node.outputs, surface[1])
            if sock is not None:
                tree.links.new(sock, out.inputs["Surface"])
    for key in ("mu_surface", "mu_shading"):
        if key in mat:
            del mat[key]


def apply_shading(mat, mode):
    """mode: 'NOSHADE' (unlit) or 'CEL' (3-step toon ramp). Returns True if applied."""
    remove_shading(mat)
    tree = mat.node_tree
    out, shader, mix_alpha = trace_shader(tree)
    if out is None or shader is None or not out.inputs["Surface"].is_linked:
        return False
    surf_src = source(out.inputs["Surface"])
    mat["mu_surface"] = [surf_src.node.name, surf_src.identifier]
    mat["mu_shading"] = mode

    col_in = color_input(shader)
    color = socket_value(col_in) if col_in is not None else (0.8, 0.8, 0.8, 1.0)
    alpha = None
    if mix_alpha is not None:
        alpha = socket_value(mix_alpha)
    elif shader.inputs.get("Alpha") is not None:
        alpha = socket_value(shader.inputs["Alpha"])
    if isinstance(alpha, float) and alpha >= 1.0:
        alpha = None

    x, y = out.location.x - 260, out.location.y + 420
    label = "MU: No Shade" if mode == 'NOSHADE' else "MU: Cel Shade"
    emit = new_node(tree, 'ShaderNodeEmission', SHADE_PREFIX + "_Emission", label, (x - 200, y))
    emit.inputs["Strength"].default_value = 1.0

    if mode == 'CEL':
        diffuse = new_node(tree, 'ShaderNodeBsdfDiffuse', SHADE_PREFIX + "_Diffuse",
                           "MU: Cel Lighting", (x - 1000, y))
        diffuse.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
        normal = shader.inputs.get("Normal")
        if normal is not None and source(normal) is not None:
            tree.links.new(source(normal), diffuse.inputs["Normal"])
        to_rgb = new_node(tree, 'ShaderNodeShaderToRGB', SHADE_PREFIX + "_ToRGB",
                          "MU: Cel Lighting", (x - 800, y))
        tree.links.new(diffuse.outputs["BSDF"], to_rgb.inputs["Shader"])
        ramp = new_node(tree, 'ShaderNodeValToRGB', SHADE_PREFIX + "_Ramp",
                        "MU: Cel Ramp", (x - 640, y))
        cr = ramp.color_ramp
        cr.interpolation = 'CONSTANT'
        steps = [(0.05, 0.1), (0.25, 0.5), (0.50, 1.0)]   # same 3 steps as the Maya rampShader
        while len(cr.elements) > 1:
            cr.elements.remove(cr.elements[-1])
        cr.elements[0].position = steps[0][0]
        cr.elements[0].color = (steps[0][1],) * 3 + (1.0,)
        for pos, val in steps[1:]:
            cr.elements.new(pos).color = (val,) * 3 + (1.0,)
        tree.links.new(to_rgb.outputs["Color"], ramp.inputs["Fac"])
        mul = new_node(tree, 'ShaderNodeMix', SHADE_PREFIX + "_Multiply",
                       "MU: Cel x Color", (x - 380, y))
        mul.data_type = 'RGBA'
        mul.blend_type = 'MULTIPLY'
        mul.inputs[0].default_value = 1.0
        tree.links.new(ramp.outputs["Color"], socket(mul.inputs, "A_Color"))
        link_or_set(tree, color, socket(mul.inputs, "B_Color"))
        tree.links.new(socket(mul.outputs, "Result_Color"), emit.inputs["Color"])
    else:
        link_or_set(tree, color, emit.inputs["Color"])

    final = emit.outputs["Emission"]
    if alpha is not None:
        transp = new_node(tree, 'ShaderNodeBsdfTransparent', SHADE_PREFIX + "_Transparent",
                          label, (x - 200, y + 140))
        mix = new_node(tree, 'ShaderNodeMixShader', SHADE_PREFIX + "_AlphaMix", label, (x, y))
        link_or_set(tree, alpha, mix.inputs[0])
        tree.links.new(transp.outputs[0], mix.inputs[1])
        tree.links.new(final, mix.inputs[2])
        final = mix.outputs[0]
    tree.links.new(final, out.inputs["Surface"])
    return True


@contextmanager
def shading_suspended(mat):
    """Temporarily undo No Shade / Cel Shade so the original shader can be edited, then re-apply it
    (so it picks up the changes)."""
    mode = mat.get("mu_shading")
    if mode:
        remove_shading(mat)
    try:
        yield
    finally:
        if mode:
            apply_shading(mat, mode)


# --------------------------------------------------------------------------- vertex colours

def color_attribute_names():
    names = set()
    for me in bpy.data.meshes:
        names.update(ca.name for ca in me.color_attributes)
    return names


def is_vcol_node(node, names):
    if node.bl_idname == 'ShaderNodeVertexColor':
        return True
    return (node.bl_idname == 'ShaderNodeAttribute' and node.attribute_type == 'GEOMETRY'
            and node.attribute_name in names)


def mix_sockets(node):
    """(A, B, Result) colour sockets of a Multiply mix node, or None."""
    if node.bl_idname == 'ShaderNodeMix' and node.data_type == 'RGBA' and node.blend_type == 'MULTIPLY':
        return (socket(node.inputs, "A_Color"), socket(node.inputs, "B_Color"),
                socket(node.outputs, "Result_Color"))
    if node.bl_idname == 'ShaderNodeMixRGB' and node.blend_type == 'MULTIPLY':
        return node.inputs["Color1"], node.inputs["Color2"], node.outputs["Color"]
    return None


def vcol_mixes(tree, names):
    """Multiply nodes that multiply a vertex colour into something: [(node, other input, result)]."""
    found = []
    for node in tree.nodes:
        socks = mix_sockets(node)
        if socks is None:
            continue
        a, b, result = socks
        for side, other in ((a, b), (b, a)):
            src = source(side)
            if src is not None and is_vcol_node(src.node, names):
                found.append((node, other, result))
                break
    return found


def hide_vcol(tree, names):
    """Bypass the vertex colour multiplies, remembering where they were plugged."""
    count = 0
    for node, other, result in vcol_mixes(tree, names):
        if not result.is_linked:
            continue
        targets = [(l.to_node.name, l.to_socket.identifier) for l in result.links]
        node["mu_hidden"] = "\n".join(f"{n}\t{s}" for n, s in targets)
        value = socket_value(other)
        for link in list(result.links):
            to_sock = link.to_socket
            tree.links.remove(link)
            link_or_set(tree, value, to_sock)
        count += 1
    return count


def unhide_vcol(tree):
    count = 0
    for node in tree.nodes:
        if "mu_hidden" not in node:
            continue
        socks = mix_sockets(node)
        if socks is not None:
            for line in node["mu_hidden"].split("\n"):
                to_name, _, to_id = line.partition("\t")
                to_node = tree.nodes.get(to_name)
                to_sock = socket(to_node.inputs, to_id) if to_node else None
                if to_sock is not None:
                    tree.links.new(socks[2], to_sock)
            count += 1
        del node["mu_hidden"]
    return count


def insert_vcol(tree, shader):
    col_in = color_input(shader)
    if col_in is None:
        return False
    value = socket_value(col_in)
    x, y = shader.location.x - 220, shader.location.y + 60
    attr = new_node(tree, 'ShaderNodeVertexColor', VCOL_PREFIX + "_Attribute",
                    "MU: Vertex Colors", (x - 220, y - 160))
    attr.layer_name = ""   # empty = the mesh's active render color attribute
    mul = new_node(tree, 'ShaderNodeMix', VCOL_PREFIX + "_Multiply", "MU: x Vertex Colors", (x, y))
    mul.data_type = 'RGBA'
    mul.blend_type = 'MULTIPLY'
    mul.inputs[0].default_value = 1.0
    link_or_set(tree, value, socket(mul.inputs, "A_Color"))
    tree.links.new(attr.outputs["Color"], socket(mul.inputs, "B_Color"))
    tree.links.new(socket(mul.outputs, "Result_Color"), col_in)
    return True


# --------------------------------------------------------------------------- operator bases

class _MaterialOperator:
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        mats = scope_materials(context)
        if not mats:
            self.report({'WARNING'}, "No node materials found" +
                        (" on the selected objects" if context.scene.model_utilities_scope == 'SELECTED' else ""))
            return {'CANCELLED'}
        changed = sum(1 for mat in mats if self.process(context, mat))
        self.report({'INFO'}, f"{self.bl_label}: {changed} of {len(mats)} materials changed")
        return {'FINISHED'}

    def process(self, context, mat):
        raise NotImplementedError


class _ImageNodeOperator:
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        nodes = list(image_nodes(scope_materials(context)))
        if not nodes:
            self.report({'WARNING'}, "No Image Texture nodes found")
            return {'CANCELLED'}
        changed = sum(1 for node in nodes if self.process(node))
        self.report({'INFO'}, f"{self.bl_label}: {changed} of {len(nodes)} texture nodes changed")
        return {'FINISHED'}

    def process(self, node):
        raise NotImplementedError


# --------------------------------------------------------------------------- transparency (01, 02)

class MU_OT_alpha_node_correct(_MaterialOperator, bpy.types.Operator):
    bl_idname = "model_utilities.alpha_node_correct"
    bl_label = "Alpha Node Correct"
    bl_description = ("Plug each material's texture alpha into its shader's Alpha, and use dithered "
                      "transparency.\nUse this if parts of the model that should be transparent "
                      "appear opaque")

    def process(self, context, mat):
        tree = mat.node_tree
        with shading_suspended(mat):
            out, shader, mix_alpha = trace_shader(tree)
            if shader is None:
                return False
            col_in = color_input(shader)
            img = find_upstream(col_in, 'ShaderNodeTexImage') if col_in is not None else None
            if img is None:
                img = next((n for n in tree.nodes if n.bl_idname == 'ShaderNodeTexImage'
                            and n.image is not None), None)
            if img is None:
                return False
            if img.image is not None and img.image.alpha_mode == 'NONE':
                img.image.alpha_mode = 'STRAIGHT'
            alpha_out = img.outputs["Alpha"]
            if shader.inputs.get("Alpha") is not None:
                tree.links.new(alpha_out, shader.inputs["Alpha"])
            elif mix_alpha is not None:
                tree.links.new(alpha_out, mix_alpha)
            else:
                # shader without an Alpha input (Diffuse, Emission...): mix it with Transparent
                surface = out.inputs["Surface"]
                shader_out = source(surface)
                transp = new_node(tree, 'ShaderNodeBsdfTransparent', ALPHA_PREFIX + "_Transparent",
                                  "MU: Alpha", (out.location.x - 200, out.location.y - 160))
                mix = new_node(tree, 'ShaderNodeMixShader', ALPHA_PREFIX + "_Mix", "MU: Alpha",
                               (out.location.x - 20, out.location.y - 160))
                out.location.x += 180
                tree.links.new(alpha_out, mix.inputs[0])
                tree.links.new(transp.outputs[0], mix.inputs[1])
                tree.links.new(shader_out, mix.inputs[2])
                tree.links.new(mix.outputs[0], surface)
            set_dithered(mat)
        return True


class MU_OT_transparency_correct(_MaterialOperator, bpy.types.Operator):
    bl_idname = "model_utilities.transparency_correct"
    bl_label = "Transparency Correct"
    bl_description = ("Take transparency from the textures' alpha channel instead of their color "
                      "(Maya's 'alpha is luminance' off), and use dithered transparency so faces sort "
                      "correctly.\nUse this when the whole model looks more or less see-through")

    def process(self, context, mat):
        tree = mat.node_tree
        changed = False
        with shading_suspended(mat):
            out, shader, mix_alpha = trace_shader(tree)
            alpha_inputs = [mix_alpha] + ([shader.inputs.get("Alpha")] if shader is not None else [])
            for sock in alpha_inputs:
                src = source(sock)
                if src is not None and src.node.bl_idname == 'ShaderNodeTexImage' and src.identifier == "Color":
                    tree.links.new(src.node.outputs["Alpha"], sock)
                    changed = True
        if getattr(mat, "surface_render_method", 'DITHERED') != 'DITHERED':
            changed = True
        set_dithered(mat)
        return changed


# --------------------------------------------------------------------------- filtering (03, 04)

class MU_OT_unfilter_textures(_ImageNodeOperator, bpy.types.Operator):
    bl_idname = "model_utilities.unfilter_textures"
    bl_label = "Unfilter All Textures"
    bl_description = "Make every texture unfiltered (Closest: pixelated, like the original console)"

    def process(self, node):
        changed = node.interpolation != 'Closest'
        node.interpolation = 'Closest'
        return changed


class MU_OT_filter_textures(_ImageNodeOperator, bpy.types.Operator):
    bl_idname = "model_utilities.filter_textures"
    bl_label = "Filter All Textures"
    bl_description = "Make every texture filtered (smooth)"

    interpolation: EnumProperty(
        name="Interpolation",
        items=[('Linear', "Linear", "Bilinear filtering"),
               ('Cubic', "Cubic", "Smoother, blurrier filtering"),
               ('Smart', "Smart", "Bicubic when magnifying, otherwise bilinear (EEVEE: linear)")],
        default='Linear')

    def process(self, node):
        changed = node.interpolation != self.interpolation
        node.interpolation = self.interpolation
        return changed


# --------------------------------------------------------------------------- UV wrapping (05 - 08)

class MU_OT_mirror_uvs(_ImageNodeOperator, bpy.types.Operator):
    bl_idname = "model_utilities.mirror_uvs"
    bl_label = "Mirror All Texture UVs"
    bl_description = "Make every texture repeat mirrored outside the 0-1 UV square (Extension: Mirror)"

    def process(self, node):
        changed = node.extension != 'MIRROR'
        node.extension = 'MIRROR'
        return changed


class MU_OT_unmirror_uvs(_ImageNodeOperator, bpy.types.Operator):
    bl_idname = "model_utilities.unmirror_uvs"
    bl_label = "UnMirror All Texture UVs"
    bl_description = "Turn off mirroring: mirrored textures go back to plain repeating (Extension: Repeat)"

    def process(self, node):
        if node.extension != 'MIRROR':
            return False
        node.extension = 'REPEAT'
        return True


class MU_OT_tile_uvs(_ImageNodeOperator, bpy.types.Operator):
    bl_idname = "model_utilities.tile_uvs"
    bl_label = "Tile All Texture UVs"
    bl_description = "Make every texture repeat outside the 0-1 UV square (Extension: Repeat; mirrored ones stay mirrored)"

    def process(self, node):
        if node.extension in {'REPEAT', 'MIRROR'}:
            return False
        node.extension = 'REPEAT'
        return True


class MU_OT_untile_uvs(_ImageNodeOperator, bpy.types.Operator):
    bl_idname = "model_utilities.untile_uvs"
    bl_label = "UnTile All Texture UVs"
    bl_description = "Show every texture only once, inside the 0-1 UV square"

    extension: EnumProperty(
        name="Outside",
        items=[('CLIP', "Clip", "Transparent black outside the 0-1 square (like Maya's default color)"),
               ('EXTEND', "Extend", "Stretch the edge pixels outward")],
        default='CLIP')

    def process(self, node):
        changed = node.extension != self.extension
        node.extension = self.extension
        return changed


# --------------------------------------------------------------------------- vertex colours (09, 10)

def materials_with_color_attributes(context):
    mats = []
    for ob in scope_objects(context):
        if not ob.data.color_attributes:
            continue
        for slot in ob.material_slots:
            mat = slot.material
            if (editable(mat) and mat.node_tree is not None and getattr(mat, "use_nodes", True)
                    and mat not in mats):
                mats.append(mat)
    return mats


class MU_OT_show_vertex_colors(bpy.types.Operator):
    bl_idname = "model_utilities.show_vertex_colors"
    bl_label = "Show Vertex Colors"
    bl_description = ("Multiply each mesh's vertex colors (color attribute) into its materials.\n"
                      "Re-enables vertex colors hidden with Hide Vertex Colors")
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        mats = materials_with_color_attributes(context)
        if not mats:
            self.report({'WARNING'}, "No meshes with vertex colors (color attributes) found")
            return {'CANCELLED'}
        names = color_attribute_names()
        changed = 0
        for mat in mats:
            tree = mat.node_tree
            with shading_suspended(mat):
                if unhide_vcol(tree):
                    changed += 1
                elif not any(r.is_linked for _, _, r in vcol_mixes(tree, names)):
                    _, shader, _ = trace_shader(tree)
                    if shader is not None and insert_vcol(tree, shader):
                        changed += 1
        self.report({'INFO'}, f"Vertex colors shown in {changed} of {len(mats)} materials")
        return {'FINISHED'}


class MU_OT_hide_vertex_colors(bpy.types.Operator):
    bl_idname = "model_utilities.hide_vertex_colors"
    bl_label = "Hide Vertex Colors"
    bl_description = ("Stop multiplying vertex colors into the materials (including the ones the glTF "
                      "importer wires in). Show Vertex Colors puts them back")
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        mats = scope_materials(context)
        names = color_attribute_names()
        changed = 0
        for mat in mats:
            with shading_suspended(mat):
                if hide_vcol(mat.node_tree, names):
                    changed += 1
        self.report({'INFO'}, f"Vertex colors hidden in {changed} of {len(mats)} materials")
        return {'FINISHED'}


# --------------------------------------------------------------------------- shading (11, 12, 13)

class MU_OT_no_shade(_MaterialOperator, bpy.types.Operator):
    bl_idname = "model_utilities.no_shade"
    bl_label = "No Shade"
    bl_description = ("Make every material full-lit: shows the texture / vertex colors exactly, with "
                      "no lighting (keeps transparency). Restore Shading undoes it")

    def process(self, context, mat):
        return apply_shading(mat, 'NOSHADE')


class MU_OT_cel_shade(_MaterialOperator, bpy.types.Operator):
    bl_idname = "model_utilities.cel_shade"
    bl_label = "Cel Shade"
    bl_description = ("Give every material simple 3-step toon lighting (EEVEE / Material Preview only). "
                      "Restore Shading undoes it")

    def process(self, context, mat):
        return apply_shading(mat, 'CEL')


class MU_OT_restore_shading(_MaterialOperator, bpy.types.Operator):
    bl_idname = "model_utilities.restore_shading"
    bl_label = "Restore Shading"
    bl_description = "Undo No Shade / Cel Shade: reconnect the materials' original shaders"

    def process(self, context, mat):
        if not mat.get("mu_shading"):
            return False
        remove_shading(mat)
        return True


def view3d_shadings(context):
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        yield space.shading


def incandesce_on(context):
    shading = context.space_data.shading if context.space_data and context.space_data.type == 'VIEW_3D' \
        else next(view3d_shadings(context), None)
    return shading is not None and shading.light == 'FLAT'


class MU_OT_incandesce(bpy.types.Operator):
    bl_idname = "model_utilities.incandesce"
    bl_label = "Incandesce"
    bl_description = ("Toggle the full-lit look in Solid viewport mode: Flat lighting, showing textures.\n"
                      "(Maya's Incandesce faked this in the legacy viewport; for Material Preview and "
                      "renders use No Shade)")
    bl_options = {'REGISTER'}

    def execute(self, context):
        turn_on = not incandesce_on(context)
        for shading in view3d_shadings(context):
            if turn_on:
                shading.light = 'FLAT'
                if shading.color_type == 'MATERIAL':
                    shading.color_type = 'TEXTURE'
            else:
                shading.light = 'STUDIO'
        self.report({'INFO'}, "Solid viewport: " + ("flat, full-lit" if turn_on else "studio lighting"))
        return {'FINISHED'}


# --------------------------------------------------------------------------- mesh (14, 15, 16)

class MU_OT_merge_vertices(bpy.types.Operator):
    bl_idname = "model_utilities.merge_vertices"
    bl_label = "Merge All Vertices"
    bl_description = "Merge together the vertices of each mesh that are within 0.001 of each other"
    bl_options = {'REGISTER', 'UNDO'}

    distance: FloatProperty(name="Distance", default=0.001, min=0.0, soft_max=0.1, precision=4,
                            subtype='DISTANCE')

    def execute(self, context):
        removed, meshes = 0, 0
        with object_mode(context):
            for ob, me in scope_meshes(context):
                bm = bmesh.new()
                bm.from_mesh(me)
                before = len(bm.verts)
                bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=self.distance)
                if len(bm.verts) != before:
                    bm.to_mesh(me)
                    me.update()
                    removed += before - len(bm.verts)
                    meshes += 1
                bm.free()
        self.report({'INFO'}, f"Merged {removed} vertices in {meshes} meshes")
        return {'FINISHED'}


def clear_custom_normals(context, ob):
    if not ob.data.has_custom_normals:
        return
    with context.temp_override(object=ob, active_object=ob, selected_objects=[ob],
                               selected_editable_objects=[ob]):
        bpy.ops.mesh.customdata_custom_splitnormals_clear()


class _ShadeEdgesOperator:
    bl_options = {'REGISTER', 'UNDO'}

    clear_custom: BoolProperty(
        name="Clear Custom Normals", default=True,
        description="Remove the normals imported from the file (glTF, FBX...), which otherwise "
                    "override smooth/flat shading")

    def execute(self, context):
        count = 0
        with object_mode(context):
            for ob, me in scope_meshes(context):
                if self.clear_custom:
                    clear_custom_normals(context, ob)
                me.polygons.foreach_set("use_smooth", [self.smooth] * len(me.polygons))
                if self.smooth:
                    me.edges.foreach_set("use_edge_sharp", [False] * len(me.edges))
                me.update()
                count += 1
        self.report({'INFO'}, f"{self.bl_label}: {count} meshes")
        return {'FINISHED'}


class MU_OT_soften_edges(_ShadeEdgesOperator, bpy.types.Operator):
    bl_idname = "model_utilities.soften_edges"
    bl_label = "Soften All Edges"
    bl_description = "Give every edge of every mesh soft (smooth) normal shading"
    smooth = True


class MU_OT_harden_edges(_ShadeEdgesOperator, bpy.types.Operator):
    bl_idname = "model_utilities.harden_edges"
    bl_label = "Harden All Edges"
    bl_description = "Give every edge of every mesh hard (flat, faceted) normal shading"
    smooth = False


# --------------------------------------------------------------------------- billboards (17)

def newell_normal(points):
    """Area-weighted normal of a polygon (length = 2 x area)."""
    n = Vector()
    for i, a in enumerate(points):
        b = points[(i + 1) % len(points)]
        n.x += (a.y - b.y) * (a.z + b.z)
        n.y += (a.z - b.z) * (a.x + b.x)
        n.z += (a.x - b.x) * (a.y + b.y)
    return n


def make_billboard(ob, camera):
    """Move the object's origin to its centre, rotate it so local +Z is the faces' normal and local +Y
    points up, then add a Track To constraint aiming +Z at the camera."""
    me = ob.data
    mw = ob.matrix_world.copy()
    verts = [mw @ v.co for v in me.vertices]
    if not verts:
        return
    center = sum(verts, Vector()) / len(verts)
    normal = Vector()
    for poly in me.polygons:
        normal += newell_normal([verts[i] for i in poly.vertices])
    if normal.length < 1e-12:
        normal = camera.matrix_world.translation - center
    z = normal.normalized()
    up = Vector((0.0, 0.0, 1.0)) if abs(z.z) < 0.999 else Vector((0.0, 1.0, 0.0))
    x = up.cross(z).normalized()
    y = z.cross(x)
    frame = Matrix.Translation(center) @ Matrix((x, y, z)).transposed().to_4x4()
    me.transform(frame.inverted() @ mw, shape_keys=True)
    me.update()
    ob.matrix_world = frame
    con = ob.constraints.new('TRACK_TO')
    con.name = "Face Camera"
    con.target = camera
    con.track_axis = 'TRACK_Z'
    con.up_axis = 'UP_Y'


def separate(context, kind):
    """Run mesh.separate on the objects in Edit Mode; return the objects it created."""
    before = set(context.scene.objects)
    bpy.ops.mesh.separate(type=kind)
    return [ob for ob in context.scene.objects if ob not in before]


class MU_OT_face_camera(bpy.types.Operator):
    bl_idname = "model_utilities.face_camera"
    bl_label = "Face Camera Always"
    bl_description = ("Separate the selected faces into billboard objects that always face the scene "
                      "camera (Track To constraint)")
    bl_options = {'REGISTER', 'UNDO'}

    group: EnumProperty(
        name="Billboards",
        items=[('ISLAND', "Per Connected Group",
                "Each group of connected selected faces becomes one billboard (e.g. a quad made of 2 triangles)"),
               ('FACE', "Per Face", "Each selected face becomes its own billboard, like the Maya script")],
        default='ISLAND')

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def execute(self, context):
        camera = context.scene.camera
        if camera is None:
            self.report({'ERROR'}, "The scene has no camera: add one (or set the scene camera) first")
            return {'CANCELLED'}
        edit_objects = [ob for ob in context.objects_in_mode if ob.type == 'MESH']
        for ob in edit_objects:
            ob.update_from_editmode()
        if not any(ob.data.total_face_sel for ob in edit_objects):
            self.report({'ERROR'}, "Select the faces to turn into billboards")
            return {'CANCELLED'}

        parts = separate(context, 'SELECTED')
        bpy.ops.object.mode_set(mode='OBJECT')
        if self.group == 'FACE':
            for ob in parts:
                bm = bmesh.new()
                bm.from_mesh(ob.data)
                bmesh.ops.split_edges(bm, edges=bm.edges[:])
                bm.to_mesh(ob.data)
                bm.free()
        view_layer = context.view_layer
        for ob in view_layer.objects:
            ob.select_set(ob in parts)
        view_layer.objects.active = parts[0]
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        parts += separate(context, 'LOOSE')
        bpy.ops.object.mode_set(mode='OBJECT')

        skinned = False
        for ob in parts:
            base = ob.name.rsplit(".", 1)[0] if ob.name[-4:-3] == "." else ob.name
            ob.name = base + "_Billboard"
            make_billboard(ob, camera)
            skinned |= any(m.type == 'ARMATURE' for m in ob.modifiers)
            ob.select_set(True)
        view_layer.objects.active = parts[0]
        msg = f"Made {len(parts)} billboard(s) facing '{camera.name}'"
        if skinned:
            self.report({'WARNING'}, msg + " (they use an Armature modifier, which may deform them oddly)")
        else:
            self.report({'INFO'}, msg)
        return {'FINISHED'}


# --------------------------------------------------------------------------- UI

def draw_buttons(layout, context, compact=False):
    col = layout.column(align=True)
    col.label(text="Transparency")
    col.operator(MU_OT_alpha_node_correct.bl_idname, text="Alpha Node Correct", icon='IMAGE_ALPHA')
    col.operator(MU_OT_transparency_correct.bl_idname, text="Transparency Correct", icon='IMAGE_RGB_ALPHA')

    col = layout.column(align=True)
    col.label(text="Textures")
    row = col.row(align=True)
    row.operator(MU_OT_unfilter_textures.bl_idname, text="Unfilter", icon='TEXTURE')
    row.operator(MU_OT_filter_textures.bl_idname, text="Filter")
    row = col.row(align=True)
    row.operator(MU_OT_mirror_uvs.bl_idname, text="Mirror", icon='MOD_MIRROR')
    row.operator(MU_OT_unmirror_uvs.bl_idname, text="UnMirror")
    row = col.row(align=True)
    row.operator(MU_OT_tile_uvs.bl_idname, text="Tile", icon='TEXTURE_DATA')
    row.operator(MU_OT_untile_uvs.bl_idname, text="UnTile")

    col = layout.column(align=True)
    col.label(text="Vertex Colors")
    row = col.row(align=True)
    row.operator(MU_OT_show_vertex_colors.bl_idname, text="Show", icon='GROUP_VCOL')
    row.operator(MU_OT_hide_vertex_colors.bl_idname, text="Hide")

    col = layout.column(align=True)
    col.label(text="Shading")
    row = col.row(align=True)
    row.operator(MU_OT_no_shade.bl_idname, text="No Shade", icon='LIGHT_SUN')
    row.operator(MU_OT_cel_shade.bl_idname, text="Cel Shade", icon='SHADING_RENDERED')
    col.operator(MU_OT_restore_shading.bl_idname, text="Restore Shading", icon='LOOP_BACK')
    col.operator(MU_OT_incandesce.bl_idname, text="Incandesce (Solid View)", icon='SHADING_SOLID',
                 depress=incandesce_on(context))

    col = layout.column(align=True)
    col.label(text="Mesh")
    col.operator(MU_OT_merge_vertices.bl_idname, text="Merge All Vertices", icon='AUTOMERGE_ON')
    row = col.row(align=True)
    row.operator(MU_OT_soften_edges.bl_idname, text="Soften Edges", icon='MOD_SMOOTH')
    row.operator(MU_OT_harden_edges.bl_idname, text="Harden Edges", icon='MESH_CUBE')

    col = layout.column(align=True)
    col.label(text="Billboards")
    col.operator(MU_OT_face_camera.bl_idname, text="Face Camera Always", icon='CAMERA_DATA')
    if not compact:
        cam = context.scene.camera
        sub = col.row()
        sub.active = False
        if context.mode != 'EDIT_MESH':
            sub.label(text="Edit Mode: select faces first")
        else:
            sub.label(text=f"Camera: {cam.name}" if cam else "No scene camera", icon='NONE' if cam else 'ERROR')


class MU_PT_panel(bpy.types.Panel):
    bl_label = "Model Utilities"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Model Utils"

    def draw(self, context):
        layout = self.layout
        row = layout.row()
        row.prop(context.scene, "model_utilities_scope", expand=True)
        draw_buttons(layout, context)


class MU_MT_menu(bpy.types.Menu):
    bl_label = "Model Utilities"
    bl_idname = "MU_MT_menu"

    def draw(self, context):
        layout = self.layout
        layout.prop(context.scene, "model_utilities_scope", expand=True)
        layout.separator()
        for cls in operator_classes:
            layout.operator(cls.bl_idname)


def draw_menu(self, context):
    self.layout.separator()
    self.layout.menu(MU_MT_menu.bl_idname)


operator_classes = (
    MU_OT_alpha_node_correct,
    MU_OT_transparency_correct,
    MU_OT_unfilter_textures,
    MU_OT_filter_textures,
    MU_OT_mirror_uvs,
    MU_OT_unmirror_uvs,
    MU_OT_tile_uvs,
    MU_OT_untile_uvs,
    MU_OT_show_vertex_colors,
    MU_OT_hide_vertex_colors,
    MU_OT_no_shade,
    MU_OT_incandesce,
    MU_OT_cel_shade,
    MU_OT_restore_shading,
    MU_OT_merge_vertices,
    MU_OT_soften_edges,
    MU_OT_harden_edges,
    MU_OT_face_camera,
)

classes = operator_classes + (MU_PT_panel, MU_MT_menu)


def register():
    bpy.types.Scene.model_utilities_scope = EnumProperty(
        name="Affect",
        description="Which objects (and their materials) the Model Utilities buttons change",
        items=[('ALL', "Whole Scene", "Every object in the scene, like the Maya scripts"),
               ('SELECTED', "Selected", "Only the selected objects")],
        default='ALL')
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.VIEW3D_MT_object.append(draw_menu)
    bpy.types.VIEW3D_MT_edit_mesh_faces.append(draw_menu)


def unregister():
    bpy.types.VIEW3D_MT_edit_mesh_faces.remove(draw_menu)
    bpy.types.VIEW3D_MT_object.remove(draw_menu)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.model_utilities_scope

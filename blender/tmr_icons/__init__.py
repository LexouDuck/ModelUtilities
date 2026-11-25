# SPDX-License-Identifier: GPL-3.0-or-later
"""TMR Icons: one-click icon renders for The Models Resource submissions.

Blender equivalent of the Maya scripts 18-SmallScreenshot.mel / 19-LargeScreenshot.mel:
captures the current 3D Viewport (what you see, with its current shading mode) at the exact
icon size, showing the viewport's full height (the sides are cropped to the icon's shape),
without overlays (grid, bones, outlines, gizmos...), on a transparent background, and saves it
as a PNG named after the model folder:

    <...>/Pylon/Pylon_Diffuse.png   (first texture of the model)
    -> <...>/Pylon_icon-small.png   (148 x 125)
    -> <...>/Pylon_icon-large.png   (750 x 650)

The icons are written next to the model folder (not inside it), so they don't end up in the
submission zip.

Buttons: 3D Viewport header ("Small" / "Large"), the sidebar "TMR" tab (N key), the View menu,
and the operator search (F3: "TMR icon").
"""

import os
import shutil
import tempfile

import bpy
import numpy as np
from bpy.props import BoolProperty, EnumProperty, IntProperty, StringProperty


SIZES = {
    'SMALL': ('Small', 'Submission icon'),
    'LARGE': ('Large', 'Large preview icon'),
}


# --------------------------------------------------------------------------- preferences

class TMRICONS_Preferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    small_width: IntProperty(name="Width", default=148, min=1, max=16384, subtype='PIXEL')
    small_height: IntProperty(name="Height", default=125, min=1, max=16384, subtype='PIXEL')
    small_suffix: StringProperty(name="Suffix", default="_icon-small.png")

    large_width: IntProperty(name="Width", default=750, min=1, max=16384, subtype='PIXEL')
    large_height: IntProperty(name="Height", default=650, min=1, max=16384, subtype='PIXEL')
    large_suffix: StringProperty(name="Suffix", default="_icon-large.png")

    transparent: BoolProperty(
        name="Transparent Background", default=True,
        description="Render the background as transparent (as required by The Models Resource). "
                    "When off, the viewport background (world / theme colour) is kept")
    keep_glows: BoolProperty(
        name="Keep Glows", default=True,
        description="On a transparent background, keep additive glows that aren't over the model "
                    "(halos, beams...) by turning their brightness into opacity. Without this they "
                    "vanish from the PNG, since they add light but have no opacity")
    name_from: EnumProperty(
        name="Name Icons After",
        items=[
            ('TEXTURE', "Texture Folder",
             "Folder of the first texture used by the model, like the Maya scripts "
             "(falls back to the .blend file's folder)"),
            ('BLEND', ".blend Folder",
             "Folder of the saved .blend file (falls back to the texture folder)"),
        ],
        default='TEXTURE')
    fit: EnumProperty(
        name="Fit Icon To",
        items=[
            ('HEIGHT', "Viewport Height",
             "The icon shows the viewport's full height; the sides are cropped to the icon's shape"),
            ('WIDTH', "Viewport Width",
             "The icon shows the viewport's full width; space is added or cropped above and below"),
        ],
        default='HEIGHT')
    show_header_buttons: BoolProperty(
        name="Buttons in the 3D Viewport Header", default=True,
        description="Show the Small / Large icon buttons in the 3D Viewport header")

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        col = layout.column(heading="Small Icon")
        col.prop(self, "small_width")
        col.prop(self, "small_height")
        col.prop(self, "small_suffix")
        col = layout.column(heading="Large Icon")
        col.prop(self, "large_width")
        col.prop(self, "large_height")
        col.prop(self, "large_suffix")
        layout.separator()
        layout.prop(self, "transparent")
        row = layout.row()
        row.active = self.transparent
        row.prop(self, "keep_glows")
        layout.prop(self, "fit")
        layout.prop(self, "name_from")
        layout.prop(self, "show_header_buttons")


def get_prefs(context=None):
    context = context or bpy.context
    addon = context.preferences.addons.get(__package__)
    return addon.preferences if addon else None


def size_settings(prefs, size):
    if size == 'LARGE':
        return prefs.large_width, prefs.large_height, prefs.large_suffix
    return prefs.small_width, prefs.small_height, prefs.small_suffix


# --------------------------------------------------------------------------- output path

def _image_nodes(node_tree, seen):
    if node_tree is None or node_tree in seen:
        return
    seen.add(node_tree)
    for node in node_tree.nodes:
        if node.type == 'TEX_IMAGE':
            yield node.image
        elif node.type == 'GROUP':
            yield from _image_nodes(node.node_tree, seen)


def _image_path(image):
    if image is None or image.source not in {'FILE', 'SEQUENCE', 'TILED'} or not image.filepath:
        return None
    return os.path.normpath(bpy.path.abspath(image.filepath, library=image.library))


def first_texture_path(context):
    """Path of the first image texture used by the scene's models (visible models first)."""
    objects = sorted(context.scene.objects,
                     key=lambda ob: (not ob.visible_get(), ob.type != 'MESH', ob.name))
    seen = set()
    for ob in objects:
        for slot in getattr(ob, "material_slots", ()):
            mat = slot.material
            if mat is None or not getattr(mat, "use_nodes", True):
                continue
            for image in _image_nodes(mat.node_tree, seen):
                path = _image_path(image)
                if path:
                    return path
    for image in bpy.data.images:  # textures not (or not yet) used by a material
        path = _image_path(image)
        if path:
            return path
    return None


def icon_path(context, suffix, name_from='TEXTURE'):
    """'<model folder><suffix>', next to the model folder, as the Maya scripts did:
    the model folder is the folder of the first texture (or of the .blend file)."""
    candidates = []
    tex = first_texture_path(context)
    blend = bpy.data.filepath
    if name_from == 'BLEND':
        candidates = [blend, tex]
    else:
        candidates = [tex, blend]
    for path in candidates:
        if not path:
            continue
        folder = os.path.dirname(os.path.abspath(path))
        if os.path.dirname(folder) == folder:  # a filesystem root: no folder name to use
            continue
        return folder + suffix
    return None


# --------------------------------------------------------------------------- rendering

def find_view3d(context):
    """The 3D Viewport the operator was called from, or the largest one in the window."""
    window = context.window
    area = context.area
    if area is None or area.type != 'VIEW_3D':
        screen = window.screen if window else None
        areas = [a for a in screen.areas if a.type == 'VIEW_3D'] if screen else []
        area = max(areas, key=lambda a: a.width * a.height) if areas else None
    if area is None:
        return None, None, None
    region = next((r for r in area.regions if r.type == 'WINDOW'), None)
    return window, area, region


class _Saved:
    """Set attributes temporarily, restoring them (in reverse order) afterwards."""

    def __init__(self):
        self._stack = []

    def set(self, owner, attr, value):
        if not hasattr(owner, attr):
            return
        old = getattr(owner, attr)
        if old == value:
            return
        try:
            setattr(owner, attr, value)
        except (AttributeError, TypeError, ValueError):
            return
        self._stack.append((owner, attr, old))

    def restore(self):
        # second pass for values that depend on each other (e.g. a video file format can
        # only be set back once the media type is restored)
        failed = []
        for _ in range(2):
            while self._stack:
                owner, attr, old = self._stack.pop()
                try:
                    setattr(owner, attr, old)
                except (AttributeError, TypeError, ValueError):
                    failed.append((owner, attr, old))
            self._stack, failed = failed, []
        self._stack = []


def _srgb_encode(x):
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1.0 / 2.4) - 0.055)


def _srgb_decode(x):
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.04045, x / 12.92, np.power((x + 0.055) / 1.055, 2.4))


def glow_to_alpha(pixels):
    """Make additive light over the transparent background visible in a straight-alpha PNG.

    pixels: (N, 4) premultiplied linear RGBA. Where the light is brighter than the coverage
    (glows, which add colour but no alpha), alpha becomes the glow's displayed brightness, so the
    icon over a black background looks exactly like the render, and over other backgrounds the
    glow still shows (the same trick as the '_Additive' textures of the export)."""
    rgb, alpha = pixels[:, :3], pixels[:, 3]
    disp = _srgb_encode(rgb)                      # over black, as displayed (Standard view)
    new_alpha = disp.max(axis=1)
    sel = new_alpha > alpha + 1e-4
    if not sel.any():
        return 0
    a = new_alpha[sel, None]
    pixels[sel, :3] = _srgb_decode(disp[sel] / a) * a
    pixels[sel, 3] = a[:, 0]
    return int(sel.sum())


def save_icon_png(scene, src_exr, filepath, transparent=True, keep_glows=True):
    """Convert the float render src_exr to an 8-bit PNG with the scene's colour management.
    Must be called with the scene's output settings already set to PNG."""
    image = bpy.data.images.load(src_exr, check_existing=False)
    try:
        if transparent and keep_glows:
            w, h = image.size
            px = np.empty(w * h * 4, dtype=np.float32)
            image.pixels.foreach_get(px)
            px = px.reshape(-1, 4)
            if glow_to_alpha(px):
                image.pixels.foreach_set(px.ravel())
                image.update()
        fd, tmp = tempfile.mkstemp(prefix="tmr_icon_", suffix=".png")
        os.close(fd)
        try:
            image.save_render(tmp, scene=scene)
            if os.path.getsize(tmp) == 0:
                raise OSError("could not write the PNG")
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            shutil.move(tmp, filepath)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
    finally:
        bpy.data.images.remove(image)


def _extent(fit, sensor_fit, x, y):
    """Height (fit 'HEIGHT') or width (fit 'WIDTH') of the view seen by a frame of x * y
    pixels, relative to the sensor size, as Blender computes it (BKE_camera_params_compute_viewplane):
    the sensor spans the width (HORIZONTAL), the height (VERTICAL), or the larger one (AUTO)."""
    if sensor_fit == 'AUTO':
        sensor_fit = 'HORIZONTAL' if x >= y else 'VERTICAL'
    along = y if fit == 'HEIGHT' else x
    return along / (x if sensor_fit == 'HORIZONTAL' else y)


def fit_view(saved, scene, space, region, width, height, fit):
    """Zoom the view (temporarily) so that the icon shows the same height (or width) as the
    viewport. Must be called before the scene resolution is changed."""
    rv3d = region.data
    if rv3d is None or region.width <= 0 or region.height <= 0:
        return
    if rv3d.view_perspective == 'CAMERA':
        # camera view: match the camera frame, as framed with the scene's own resolution
        cam_ob = space.camera if (space.use_local_camera and space.camera) else scene.camera
        cam = cam_ob.data if cam_ob is not None and cam_ob.type == 'CAMERA' else None
        if cam is None or cam.type == 'PANO':
            return
        rd = scene.render
        frame_w = rd.resolution_x * rd.pixel_aspect_x
        frame_h = rd.resolution_y * rd.pixel_aspect_y
        ratio = (_extent(fit, cam.sensor_fit, width, height) /
                 _extent(fit, cam.sensor_fit, frame_w, frame_h))
        if cam.type == 'ORTHO':
            saved.set(cam, "ortho_scale", cam.ortho_scale / ratio)
        else:
            saved.set(cam, "lens", cam.lens * ratio)
    else:
        # free view (perspective or orthographic): the view's lens sets the zoom
        ratio = (_extent(fit, 'AUTO', width, height) /
                 _extent(fit, 'AUTO', region.width, region.height))
        saved.set(space, "lens", space.lens * ratio)


def render_viewport_png(context, filepath, width, height, transparent=True, keep_glows=True,
                        fit='HEIGHT'):
    """Viewport-render the 3D View at width x height and save a PNG to filepath.
    Returns None on success, or an error message."""
    window, area, region = find_view3d(context)
    if area is None or region is None:
        return "No 3D Viewport found"

    scene = context.scene
    rd = scene.render
    im = rd.image_settings
    space = area.spaces.active

    # float intermediate (keeps the light of additive glows, which have no alpha); no '#' in
    # the name, which Blender would replace with the frame number
    fd, tmp = tempfile.mkstemp(prefix="tmr_icon_", suffix=".exr")
    os.close(fd)
    os.remove(tmp)

    saved = _Saved()
    try:
        # same height (or width) as the viewport
        fit_view(saved, scene, space, region, width, height, fit)
        # exact size, no scaling / cropping / stamping
        saved.set(rd, "resolution_x", width)
        saved.set(rd, "resolution_y", height)
        saved.set(rd, "resolution_percentage", 100)
        saved.set(rd, "pixel_aspect_x", 1.0)
        saved.set(rd, "pixel_aspect_y", 1.0)
        saved.set(rd, "use_border", False)
        saved.set(rd, "use_stamp", False)
        saved.set(rd, "use_multiview", False)
        saved.set(rd, "film_transparent", bool(transparent))
        saved.set(rd, "filepath", tmp)
        saved.set(rd, "use_file_extension", False)
        saved.set(im, "media_type", 'IMAGE')  # Blender 5.0+
        saved.set(im, "file_format", 'OPEN_EXR')
        saved.set(im, "color_mode", 'RGBA')
        saved.set(im, "color_depth", '32')
        # no grid, bones, outlines, origins, ... (viewport renders include overlays)
        saved.set(space.overlay, "show_overlays", False)

        with context.temp_override(window=window, area=area, region=region):
            bpy.ops.render.opengl(write_still=True, view_context=True)
        if not os.path.isfile(tmp) or os.path.getsize(tmp) == 0:
            return "The viewport render did not produce an image"

        # final file: 8-bit PNG
        saved.set(im, "file_format", 'PNG')
        saved.set(im, "color_mode", 'RGBA' if transparent else 'RGB')
        saved.set(im, "color_depth", '8')
        saved.set(im, "compression", 15)
        save_icon_png(scene, tmp, filepath, transparent, keep_glows)
        return None
    except (RuntimeError, OSError) as ex:
        return str(ex).strip() or ex.__class__.__name__
    finally:
        saved.restore()
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


# --------------------------------------------------------------------------- operator

class TMRICONS_OT_render_icon(bpy.types.Operator):
    bl_idname = "tmr_icons.render_icon"
    bl_label = "Render TMR Icon"
    bl_description = "Save the current 3D Viewport as a Models Resource icon PNG"
    bl_options = {'REGISTER'}

    size: EnumProperty(
        name="Size",
        items=[(k, v[0], v[1]) for k, v in SIZES.items()],
        default='SMALL')

    @classmethod
    def poll(cls, context):
        return context.window is not None

    @classmethod
    def description(cls, context, properties):
        prefs = get_prefs(context)
        if prefs is None:
            return cls.bl_description
        w, h, suffix = size_settings(prefs, properties.size)
        path = icon_path(context, suffix, prefs.name_from)
        where = path if path else "(save the .blend file or load textures first)"
        return (f"Save the current 3D Viewport as a {w}x{h} PNG "
                f"({SIZES[properties.size][1].lower()}).\nSaves to: {where}")

    def execute(self, context):
        prefs = get_prefs(context)
        if prefs is None:
            self.report({'ERROR'}, "TMR Icons add-on preferences not found")
            return {'CANCELLED'}
        w, h, suffix = size_settings(prefs, self.size)
        path = icon_path(context, suffix, prefs.name_from)
        if path is None:
            self.report({'ERROR'}, "Can't name the icon: the model has no texture files "
                                   "and the .blend file is not saved")
            return {'CANCELLED'}
        err = render_viewport_png(context, path, w, h, prefs.transparent, prefs.keep_glows,
                                  prefs.fit)
        if err:
            self.report({'ERROR'}, f"Icon not saved: {err}")
            return {'CANCELLED'}
        print(f"Saved image as {path}")
        self.report({'INFO'}, f"Saved image as {path}")
        return {'FINISHED'}


# --------------------------------------------------------------------------- UI

def draw_buttons(layout, compact=False):
    row = layout.row(align=True)
    op = row.operator(TMRICONS_OT_render_icon.bl_idname,
                      text="Small" if compact else "Small Icon", icon='RESTRICT_RENDER_OFF')
    op.size = 'SMALL'
    op = row.operator(TMRICONS_OT_render_icon.bl_idname,
                      text="Large" if compact else "Large Icon")
    op.size = 'LARGE'


def draw_header(self, context):
    prefs = get_prefs(context)
    if prefs is None or not prefs.show_header_buttons:
        return
    self.layout.separator()
    draw_buttons(self.layout, compact=True)


def draw_view_menu(self, context):
    layout = self.layout
    layout.separator()
    op = layout.operator(TMRICONS_OT_render_icon.bl_idname, text="TMR Small Icon",
                         icon='RESTRICT_RENDER_OFF')
    op.size = 'SMALL'
    op = layout.operator(TMRICONS_OT_render_icon.bl_idname, text="TMR Large Icon")
    op.size = 'LARGE'


class TMRICONS_PT_panel(bpy.types.Panel):
    bl_label = "TMR Icons"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "TMR"

    def draw(self, context):
        layout = self.layout
        prefs = get_prefs(context)
        col = layout.column()
        col.scale_y = 1.4
        draw_buttons(col)
        if prefs is None:
            return
        path = icon_path(context, "", prefs.name_from)
        box = layout.box()
        col = box.column(align=True)
        col.label(text="Saves in:")
        if path:
            col.label(text=os.path.dirname(path), icon='FILE_FOLDER')
            for suffix in (prefs.small_suffix, prefs.large_suffix):
                col.label(text=os.path.basename(path) + suffix, icon='FILE_IMAGE')
        else:
            col.label(text="(no texture / unsaved .blend)", icon='ERROR')
        col = layout.column(align=True)
        col.prop(prefs, "transparent")
        sub = col.row()
        sub.active = prefs.transparent
        sub.prop(prefs, "keep_glows")
        col.prop(prefs, "fit", text="Fit")
        col.prop(prefs, "show_header_buttons", text="Header Buttons")
        layout.label(text=f"Small {prefs.small_width}x{prefs.small_height}, "
                          f"Large {prefs.large_width}x{prefs.large_height}")


classes = (
    TMRICONS_Preferences,
    TMRICONS_OT_render_icon,
    TMRICONS_PT_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.VIEW3D_HT_header.append(draw_header)
    bpy.types.VIEW3D_MT_view.append(draw_view_menu)


def unregister():
    bpy.types.VIEW3D_MT_view.remove(draw_view_menu)
    bpy.types.VIEW3D_HT_header.remove(draw_header)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

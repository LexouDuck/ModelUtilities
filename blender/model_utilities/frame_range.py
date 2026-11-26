# SPDX-License-Identifier: GPL-3.0-or-later
"""Frame range from action: make the timeline's frame range match the length of the current animation.

- Automatically, whenever the active object's action changes (picking another action in the Action
  Editor or Shape Key Editor, NLA tweak mode, scripts...). Can be turned off: Timeline > Playback
  popover, the Dope Sheet's View menu, the Model Utils sidebar, or the add-on's preferences.
- Manually: "Frame Range from Action" (Ctrl+Shift+P, or the View menu of the Timeline / Dope Sheet /
  Graph Editor / NLA, or the Model Utils sidebar).

The scene's frame range is set, or the preview range if it is turned on (since that is then what
playback uses).
"""

import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty


# --------------------------------------------------------------------------- helpers

def addon_prefs():
    addon = bpy.context.preferences.addons.get(__package__)
    return addon.preferences if addon is not None else None


def auto_enabled():
    prefs = addon_prefs()
    return True if prefs is None else prefs.auto_frame_range


def animated_ids(ob):
    """The object, and its shape keys (whose action is the one shown by the Shape Key Editor).
    (Since Blender 5.0, shape key animation is stored in the object's action, as another slot.)"""
    ids = [ob]
    shape_keys = getattr(ob.data, "shape_keys", None) if ob.data is not None else None
    if shape_keys is not None:
        ids.append(shape_keys)
    return ids


def id_action(id_data):
    anim = id_data.animation_data
    return anim.action if anim is not None else None


def current_action(context):
    """The action shown in the Action / Shape Key Editor: that of the active object or its shape keys."""
    ob = context.active_object
    if ob is None:
        return None
    ids = animated_ids(ob)
    space = context.space_data
    if space is not None and space.type == 'DOPESHEET_EDITOR' and space.ui_mode == 'SHAPEKEY':
        ids.reverse()
    for id_data in ids:
        action = id_action(id_data)
        if action is not None:
            return action
    return None


def action_range(action):
    start, end = action.frame_range
    start, end = int(round(start)), int(round(end))
    return start, max(start, end)


def set_frame_range(scene, start, end):
    """Set the scene range, or the preview range when it's on. Returns which one was set."""
    if scene.use_preview_range:
        attrs, which = ("frame_preview_start", "frame_preview_end"), "preview range"
    else:
        attrs, which = ("frame_start", "frame_end"), "frame range"
    # set them in an order that never has start > end (Blender would push the other one)
    if start > getattr(scene, attrs[1]):
        setattr(scene, attrs[1], end)
        setattr(scene, attrs[0], start)
    else:
        setattr(scene, attrs[0], start)
        setattr(scene, attrs[1], end)
    if not start <= scene.frame_current <= end:
        scene.frame_current = start
    return which


# --------------------------------------------------------------------------- automatic update

_last_actions = {}   # session_uid of the object / shape keys -> session_uid of its action (or None)


@persistent
def on_depsgraph_update(scene, depsgraph):
    if not auto_enabled():
        return
    ob = depsgraph.view_layer.objects.active
    if ob is None:
        return
    changed_to = None
    for id_data in animated_ids(ob):
        action = id_action(id_data)
        current = action.session_uid if action is not None else None
        key = id_data.session_uid
        previous = _last_actions.get(key, current)   # first time we see it: nothing changed
        _last_actions[key] = current
        if current != previous and action is not None:
            changed_to = action
    if changed_to is not None:
        start, end = action_range(changed_to)
        # a 1-frame action is most likely one that was just created by inserting a first keyframe:
        # don't collapse the frame range to it
        if end > start:
            set_frame_range(scene, start, end)


@persistent
def on_load_post(*_args):
    _last_actions.clear()


# --------------------------------------------------------------------------- operator, preferences, UI

class MU_OT_frame_range_from_action(bpy.types.Operator):
    bl_idname = "model_utilities.frame_range_from_action"
    bl_label = "Frame Range from Action"
    bl_description = ("Set the frame range (or the preview range, when it's on) to the length of the active "
                      "object's current action")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        if current_action(context) is None:
            cls.poll_message_set("The active object has no action")
            return False
        return True

    def execute(self, context):
        action = current_action(context)
        start, end = action_range(action)
        which = set_frame_range(context.scene, start, end)
        self.report({'INFO'}, f"{which.capitalize()}: {start} - {end} ('{action.name}')")
        return {'FINISHED'}


class MU_AddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    auto_frame_range: BoolProperty(
        name="Auto Frame Range from Action",
        description="When the active object's action changes (e.g. picking another one in the Action Editor), "
                    "set the frame range (or the preview range, when it's on) to the length of that action",
        default=True)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "auto_frame_range")
        layout.label(text="Frame Range from Action, manually: Ctrl+Shift+P, or the View menu of the animation editors")


def draw_toggle(layout):
    prefs = addon_prefs()
    if prefs is not None:
        layout.prop(prefs, "auto_frame_range", text="Auto Frame Range from Action")


def draw_view_menu(self, context):
    layout = self.layout
    layout.separator()
    layout.operator(MU_OT_frame_range_from_action.bl_idname, icon='ACTION')
    if self.bl_idname in ("TIME_MT_view", "DOPESHEET_MT_view"):
        draw_toggle(layout)


def draw_playback_popover(self, context):
    layout = self.layout
    layout.separator()
    draw_toggle(layout)


def draw_sidebar(layout, context):
    col = layout.column(align=True)
    col.label(text="Animation")
    col.operator(MU_OT_frame_range_from_action.bl_idname, text="Frame Range from Action", icon='ACTION')
    draw_toggle(col)


VIEW_MENUS = ("TIME_MT_view", "DOPESHEET_MT_view", "GRAPH_MT_view", "NLA_MT_view")
classes = (MU_OT_frame_range_from_action, MU_AddonPreferences)
addon_keymaps = []


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    for name in VIEW_MENUS:
        menu = getattr(bpy.types, name, None)
        if menu is not None:
            menu.append(draw_view_menu)
    if hasattr(bpy.types, "TIME_PT_playback"):
        bpy.types.TIME_PT_playback.append(draw_playback_popover)
    bpy.app.handlers.depsgraph_update_post.append(on_depsgraph_update)
    bpy.app.handlers.load_post.append(on_load_post)
    keyconfig = bpy.context.window_manager.keyconfigs.addon
    if keyconfig is not None:
        # "Frames" is active in every editor (like Shift+Left/Right to jump to the start/end frame)
        keymap = keyconfig.keymaps.new(name="Frames", space_type='EMPTY', region_type='WINDOW')
        item = keymap.keymap_items.new(MU_OT_frame_range_from_action.bl_idname, 'P', 'PRESS', ctrl=True, shift=True)
        addon_keymaps.append((keymap, item))


def unregister():
    for keymap, item in addon_keymaps:
        keymap.keymap_items.remove(item)
    addon_keymaps.clear()
    for handlers, func in ((bpy.app.handlers.depsgraph_update_post, on_depsgraph_update),
                           (bpy.app.handlers.load_post, on_load_post)):
        if func in handlers:
            handlers.remove(func)
    if hasattr(bpy.types, "TIME_PT_playback"):
        bpy.types.TIME_PT_playback.remove(draw_playback_popover)
    for name in VIEW_MENUS:
        menu = getattr(bpy.types, name, None)
        if menu is not None:
            menu.remove(draw_view_menu)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    _last_actions.clear()

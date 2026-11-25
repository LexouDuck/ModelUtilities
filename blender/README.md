## Model Utilities (Blender add-on)

`model_utilities-1.0.0.zip` is the Blender port of the Maya shelf scripts 01 to 17 (Blender 4.2 or newer, including 5.x).
The two screenshot scripts (18, 19) are the separate **TMR Icons** add-on below.

### Installing it (once)

In Blender: **Edit › Preferences › Get Extensions**, click the **⌄** menu in the top-right corner,
choose **Install from Disk…** and pick `model_utilities-1.0.0.zip`. (Dragging the zip onto the Blender window does the same.)

### Using it

* **Sidebar**: press **N** in the 3D Viewport and open the **Model Utils** tab: all the buttons, grouped like the Maya shelf.
* **Object menu** › *Model Utilities* (also in Edit Mode › **Face** menu), and the search (**F3**, type the script name).
* **Affect**: *Whole Scene* (the default, like the Maya scripts) or *Selected* objects only.
* Some buttons have options (Filter, UnTile, Merge, Soften/Harden, Face Camera): after clicking, open the **Adjust Last Operation** panel (bottom-left of the viewport, or **F9**).
* Everything can be undone with **Ctrl+Z**.

| Maya script         | Blender button         | What it does in Blender |
|---------------------|------------------------|-------------------------|
| AlphaNodeCorrect    | Alpha Node Correct     | Plugs each material's texture **Alpha** output into the shader's **Alpha**, and sets the material to *Dithered* (order-independent) transparency |
| TransparencyCorrect | Transparency Correct   | Where the shader's Alpha is fed by a texture's **Color** (the "alpha is luminance" problem), feeds it from the texture's **Alpha** instead; sets *Dithered* transparency so faces sort correctly |
| UnfilterAllTextures | Textures › Unfilter    | Image Texture nodes › Interpolation: **Closest** (pixelated) |
| FilterAllTextures   | Textures › Filter      | Interpolation: **Linear** (option: Cubic, Smart) |
| MirrorAllTextureUVs | Textures › Mirror      | Image Texture nodes › Extension: **Mirror** |
| UnMirrorAllTextureUVs | Textures › UnMirror  | Mirror › **Repeat** |
| TileAllTextureUVs   | Textures › Tile        | Extension: **Repeat** (mirrored textures stay mirrored) |
| UnTileAllTextureUVs | Textures › UnTile      | Extension: **Clip** (nothing outside the 0-1 UV square; option: Extend) |
| ShowVertexColors    | Vertex Colors › Show   | Multiplies each mesh's color attribute into its materials (or re-enables the ones hidden with *Hide*) |
| HideVertexColors    | Vertex Colors › Hide   | Bypasses that multiply, including the one the glTF importer creates. *Show* puts it back |
| NoShade             | Shading › No Shade     | Unlit materials: the texture × vertex colors as an Emission shader, transparency kept |
| CelShade            | Shading › Cel Shade    | The same 3-step ramp (0.1 / 0.5 / 1.0) as toon lighting × the texture. EEVEE / Material Preview only (Cycles can't do it) |
| *(new)*             | Shading › Restore Shading | Undoes No Shade / Cel Shade: the original shaders are kept in the materials and reconnected |
| Incandesce          | Incandesce (Solid View) | Toggles the full-lit look in **Solid** mode (Flat lighting, textures shown) in every 3D Viewport |
| MergeAllVertices    | Merge All Vertices     | Merge by distance, 0.001 (adjustable) |
| SoftenAllEdges      | Soften Edges           | Smooth shading, no sharp edges |
| HardenAllEdges      | Harden Edges           | Flat shading |
| FaceCameraAlways    | Face Camera Always     | In Edit Mode: separates the selected faces into billboard objects (origin at their center) with a **Track To** constraint aimed at the scene camera |

Notes:

* **Soften / Harden** also clear the *custom normals* that importers (glTF, FBX...) bring in from the file by default,
  since those override smooth/flat shading. Untick *Clear Custom Normals* in the operation panel to keep them.
* **Face Camera Always**: by default each group of *connected* selected faces becomes one billboard
  (so a sprite quad made of 2 triangles stays together); choose *Per Face* in the operation panel for the Maya behaviour.
  Blender constraints can't target the viewport itself (Maya's `persp`), so the billboards face the **scene camera**:
  look through it with **Numpad 0** to see them face you.
* No Shade, Cel Shade and the vertex colour / alpha fixes work together in any order: e.g. running *Alpha Node Correct*
  after *No Shade* updates the unlit material too.

---

## Icons for The Models Resource (Blender add-on)

`blender/tmr_icons/` is a small Blender add-on (Blender 4.2 or newer, including 5.x) that saves the submission icons in one click:

| Button    | Size      | Saved as                        |
|-----------|-----------|---------------------------------|
| **Small** | 148 × 125 | `<model folder>_icon-small.png` |
| **Large** | 750 × 650 | `<model folder>_icon-large.png` |

The model folder is the folder of the model's first texture (falling back to the folder of the `.blend` file),
and the icon is written **next to** that folder, not inside it, so it doesn't end up in the submission zip:

```
Buildings/Melee/Protoss/Pylon/pylon.blend
Buildings/Melee/Protoss/Pylon/Pylon_Diffuse.png
Buildings/Melee/Protoss/Pylon_icon-small.png    <- Small
Buildings/Melee/Protoss/Pylon_icon-large.png    <- Large
```

An existing icon is overwritten.

### Installing it (once)

Locate the extension zip file `tmr_icons-1.1.0.zip` in this folder.

Then, in Blender: **Edit › Preferences › Get Extensions**, click the **⌄** menu in the top-right corner,
choose **Install from Disk…** and pick the zip. (Dragging the zip onto the Blender window does the same.)

It is enabled straight away and stays installed for every future session.

### Using it

* **3D Viewport header** (top-right of the viewport, after the shading buttons): **Small** and **Large** buttons.
  One click saves the icon. Hovering a button shows the exact file it will write.
* **Sidebar**: press **N** in the viewport and open the **TMR** tab.
  Same buttons, plus where the icons will go and the transparency switch.
* **View menu** › *TMR Small Icon* / *TMR Large Icon*, and the search (**F3**, type "TMR").

The result shows in the status bar ("Saved image as …"). If it can't save, the error shows there instead.

What gets captured:

* the current view, in the current shading mode. Use **Material Preview** (the default in the `.blend` files) for the SC2 look;
* the current frame, so you can pick a pose by moving the timeline first;
* no overlays (grid, bones, outlines, origins, gizmos), on a **transparent** background (switch **Transparent Background** off to keep the viewport background instead);
* rendered off-screen at exactly 148 × 125 / 750 × 650, not a resized screenshot. The viewport's size and your screen resolution don't matter.

Framing: the icon shows the viewport's full height. The icon shapes are squarer than a typical viewport,
so the left and right edges of the viewport are cropped off.
Frame the model so it fills the viewport's height and stays away from its left and right edges, and it will fill the icon.
This also works in camera view (**Numpad 0**): the icon then shows the full height of the camera frame.
To get the previous behaviour (full width, with extra space above and below), set **Fit Icon To** to *Viewport Width*.

Settings (sizes, file name suffixes, transparency, fitting to the viewport height or width, naming the icon after the texture folder or the `.blend` folder, hiding the header buttons): **Edit › Preferences › Add-ons › TMR Icons**.

Other ways to use it, if you prefer:

* **Keyboard shortcut**: right-click either button › **Assign Shortcut**, then press the keys.
* **Quick Favorites**: right-click either button › **Add to Quick Favorites**. Then **Q** in the viewport opens a menu with it.

Additive glows over an empty background (for example halo effects or such) add light but have no opacity,
so on a transparent background they would vanish from the PNG.
To this end, the **Keep Glows** option (on by default, in the sidebar and the preferences) turns their brightness into opacity:
over a black background the icon looks exactly like the viewport, and over a lighter one the glow still shows.

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

Locate the extension zip file `tmr_icons-1.0.0.zip` in this folder.

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

Framing: the icon keeps the viewport's left-to-right view. The icon shapes are squarer than a typical viewport,
so the icon shows a bit more above and below than the viewport does.
Frame the model so it fills the viewport's width and it will fill the icon.

Settings (sizes, file name suffixes, transparency, naming the icon after the texture folder or the `.blend` folder, hiding the header buttons): **Edit › Preferences › Add-ons › TMR Icons**.

Other ways to use it, if you prefer:

* **Keyboard shortcut**: right-click either button › **Assign Shortcut**, then press the keys.
* **Quick Favorites**: right-click either button › **Add to Quick Favorites**. Then **Q** in the viewport opens a menu with it.

Additive glows over an empty background (for example halo effects or such) add light but have no opacity,
so on a transparent background they would vanish from the PNG.
To this end, the **Keep Glows** option (on by default, in the sidebar and the preferences) turns their brightness into opacity:
over a black background the icon looks exactly like the viewport, and over a lighter one the glow still shows.

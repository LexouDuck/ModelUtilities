"""Rebuilds shelf_Utilities.mel from the scripts in scripts/.

Each button runs its script (without the leading comment lines); its tooltip is the script's leading
comment lines. Run this after changing a script:  python build_shelf.py
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))

# (script file, button icon); "|" is a separator
BUTTONS = [
    ("00-Options", "commandButton.png"),
    "|",
    ("01-AlphaNodeCorrect", "commandButton.png"),
    ("02-TransparencyCorrect", "commandButton.png"),
    "|",
    ("03-UnfilterAllTextures", "texturePlacement.png"),
    ("04-FilterAllTextures", "texturePlacement.png"),
    "|",
    ("05-MirrorAllTextureUVs", "UVEditorUV.png"),
    ("06-UnMirrorAllTextureUVs", "UVEditorUV.png"),
    "|",
    ("07-TileAllTextureUVs", "UVEditorShell.png"),
    ("08-UnTileAllTextureUVs", "UVEditorShell.png"),
    "|",
    ("09-ShowVertexColors", "polyColorMaterialAmbient.png"),
    ("10-HideVertexColors", "polyColorMaterialAmbientDiffuse.png"),
    ("11-NoShade", "toonBrightness2.png"),
    ("12-Incandesce", "toonSolid.png"),
    ("13-CelShade", "toonBrightness3.png"),
    ("14-RestoreShading", "commandButton.png"),
    "|",
    ("15-MergeAllVertices", "polyMergeVertex.png"),
    ("16-SoftenAllEdges", "polySoftEdge.png"),
    ("17-HardenAllEdges", "polyHardEdge.png"),
    "|",
    ("18-FaceCameraAlways", "cameraAim.png"),
    "|",
    ("19-SmallScreenshot", "viewStereoEditor.png"),
    ("20-LargeScreenshot", "viewStereoEditor.png"),
]

HEADER = """global proc shelf_Utilities () {
    global string $gBuffStr;
    global string $gBuffStr0;
    global string $gBuffStr1;

"""

BUTTON = """
    shelfButton
        -enableCommandRepeat 1
        -enable 1
        -width 35
        -height 35
        -manage 1
        -visible 1
        -preventOverride 0
        -annotation "{annotation}"
        -enableBackground 0
        -backgroundColor 0 0 0
        -highlightColor 0.321569 0.521569 0.65098
        -align "center"
        -label "{label}"
        -labelOffset 0
        -rotation 0
        -flipX 0
        -flipY 0
        -useAlpha 1
        -font "plainLabelFont"
        -imageOverlayLabel "{label}"
        -overlayLabelColor 0.8 0.8 0.8
        -overlayLabelBackColor 0 0 0 0.5
        -image "{image}"
        -image1 "{image}"
        -style "iconOnly"
        -marginWidth 1
        -marginHeight 1
        -command "{command}"
        -sourceType "mel"
        -commandRepeatable 1
        -flat 1
    ;"""

SEPARATOR = """
    separator
        -enable 1
        -width 12
        -height 35
        -manage 1
        -visible 1
        -preventOverride 0
        -enableBackground 0
        -backgroundColor 0 0 0
        -highlightColor 0.321569 0.521569 0.65098
        -style "shelf"
        -horizontal 0
    ;"""


def mel_string(text):
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\t", "\\t").replace("\n", "\\n")


def read_script(name):
    with open(os.path.join(HERE, "scripts", name + ".mel"), encoding="utf-8") as f:
        lines = f.read().replace("\r\n", "\n").split("\n")
    comments = []
    while lines and lines[0].startswith("//"):
        comments.append(lines.pop(0)[2:].strip())
    label = comments[0]
    annotation = label + ": " + "\n".join(comments[1:])
    return label, annotation, "\n".join(lines).strip("\n")


def build():
    out = [HEADER]
    for entry in BUTTONS:
        if entry == "|":
            out.append(SEPARATOR)
            continue
        name, image = entry
        label, annotation, command = read_script(name)
        out.append(BUTTON.format(annotation=mel_string(annotation), label=label, image=image,
                                 command=mel_string(command)))
    out.append("\n\n} \n")
    with open(os.path.join(HERE, "shelf_Utilities.mel"), "w", encoding="utf-8", newline="\n") as f:
        f.write("".join(out))


if __name__ == "__main__":
    build()
    print("shelf_Utilities.mel rebuilt")

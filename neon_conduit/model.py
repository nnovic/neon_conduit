"""Low-poly 3D models: reading Wavefront OBJ files and the colours of their materials.

Only what the game needs is read: vertices (v), faces (f, any number of corners,
v / v/vt / v/vt/vn forms), lines (l) and material switches (usemtl). Texture coordinates,
normals and .mtl files are ignored; each material name maps to a flat colour
here, and faces are shaded by the renderer.
"""
import os

ASSETS = os.path.join(os.path.dirname(__file__), "assets")

# Material name -> (colour, lit). Unlit materials glow at full colour whatever the light.
MATERIALS = {
    "body": ((205, 210, 225), True),
    "dark": ((55, 60, 85), True),
    "accent": ((255, 60, 150), True),
    "trim": ((40, 210, 255), True),
    "glass": ((20, 40, 80), True),
    "glow": ((90, 180, 255), False),        # engine exhausts; the renderer recolours them on boost
    "neon": ((255, 80, 160), False),        # glowing edge lines
}
DEFAULT = ((200, 200, 200), True)


class Model:
    """Vertices, faces and lines of a model; face normals are worked out by the renderer."""

    def __init__(self, verts, faces, lines):
        self.verts = verts          # [(x, y, z)]
        self.faces = faces          # [(vertex indices, material name)]
        self.lines = lines          # [(vertex indices, material name)], polylines


def load_obj(name):
    """Read assets/<name>, an OBJ file."""
    verts, faces, lines, mat = [], [], [], None
    with open(os.path.join(ASSETS, name)) as f:
        for line in f:
            parts = line.split()
            if not parts:
                continue
            if parts[0] == "v":
                verts.append(tuple(float(c) for c in parts[1:4]))
            elif parts[0] in ("f", "l"):
                idx = []
                for p in parts[1:]:
                    i = int(p.split("/")[0])
                    idx.append(i - 1 if i > 0 else len(verts) + i)   # OBJ allows negative indices
                (faces if parts[0] == "f" else lines).append((idx, mat))
            elif parts[0] == "usemtl":
                mat = parts[1] if len(parts) > 1 else None
    return Model(verts, faces, lines)

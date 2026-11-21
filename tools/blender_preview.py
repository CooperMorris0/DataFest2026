"""Headless Blender previews of the Roblox world, built from the SAME primitive lists the Roblox
builder uses (data/processed/roblox/styled/*, landmark spec files).

  /Applications/Blender.app/Contents/MacOS/Blender -b -P tools/blender_preview.py -- \\
      --window 4300 -1100 5200 -300 --street 4816 -749 --out data/processed/previews/jack_london \\
      [--landmark roblox/landmarks/oakland_city_hall.json ...]

window / street are local meters (x east, z = -north). Renders aerial.png, street.png, close.png.
Conventions match Roblox: WedgePart high edge on local +Z; cylinder axis = local X; CFrame.Angles
order R = Rx * Ry * Rz; Roblox (X, Y, Z) -> Blender (X, -Z, Y). Previews are approximate (box-
projected textures, no Roblox lighting), for checking massing, colors, roofs, overlap and placement.
"""
import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, n=1, default=None):
    if name in args:
        i = args.index(name)
        vals = args[i + 1:i + 1 + n]
        return vals if n > 1 else vals[0]
    return default


WIN = [float(v) for v in arg("--window", 4, ["4300", "-1100", "5200", "-300"])]
STREET = [float(v) for v in arg("--street", 2, ["4816", "-749"])]
OUT = Path(arg("--out", 1, str(ROOT / "data/processed/previews/preview")))
OUT.mkdir(parents=True, exist_ok=True)
LANDMARKS = [args[i + 1] for i, a in enumerate(args) if a == "--landmark"]
S = 1 / 0.28
STY = ROOT / "data/processed/roblox/styled"
TEX = ROOT / "roblox/textures"
man = json.loads((ROOT / "data/processed/roblox/manifest.json").read_text())
LOOKS = man["styled"]["looks"]

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

# ------------------------------------------------------------------ math
C = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]], float)  # roblox -> blender


def rot(rx, ry, rz):
    rx, ry, rz = map(math.radians, (rx, ry, rz))
    Rx = np.array([[1, 0, 0], [0, math.cos(rx), -math.sin(rx)], [0, math.sin(rx), math.cos(rx)]])
    Ry = np.array([[math.cos(ry), 0, math.sin(ry)], [0, 1, 0], [-math.sin(ry), 0, math.cos(ry)]])
    Rz = np.array([[math.cos(rz), -math.sin(rz), 0], [math.sin(rz), math.cos(rz), 0], [0, 0, 1]])
    return Rx @ Ry @ Rz


def shape_local(s, sx, sy, sz):
    """vertices (roblox local) + faces for a unit shape scaled to size."""
    hx, hy, hz = sx / 2, sy / 2, sz / 2
    if s in ("B", "K"):
        v = [(-hx, -hy, -hz), (hx, -hy, -hz), (hx, hy, -hz), (-hx, hy, -hz),
             (-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz)]
        f = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (2, 3, 7, 6), (1, 2, 6, 5), (0, 4, 7, 3)]
        return v, f
    if s == "W":  # high edge at +Z (measured in Studio)
        v = [(-hx, -hy, -hz), (hx, -hy, -hz), (hx, -hy, hz), (-hx, -hy, hz), (-hx, hy, hz), (hx, hy, hz)]
        f = [(0, 1, 2, 3), (3, 2, 5, 4), (0, 4, 5, 1), (0, 3, 4), (1, 5, 2)]
        return v, f
    if s == "C":  # axis along local X
        n = 10
        v, f = [], []
        for x in (-hx, hx):
            for k in range(n):
                a = 2 * math.pi * k / n
                v.append((x, hy * math.cos(a), hz * math.sin(a)))
        for k in range(n):
            f.append((k, (k + 1) % n, n + (k + 1) % n, n + k))
        f.append(tuple(range(n))[::-1])
        f.append(tuple(range(n, 2 * n)))
        return v, f
    raise ValueError(s)


# ------------------------------------------------------------------ materials
mats = {}


def tex_material(key, color, tile_studs=None, image=None, alpha=False):
    name = f"{key}_{tuple(color)}"
    if name in mats:
        return mats[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    rgb = [c / 255 for c in color] + [1]
    if image:
        img = bpy.data.images.load(str(image), check_existing=True)
        tn = nt.nodes.new("ShaderNodeTexImage")
        tn.image = img
        if tile_studs:  # box projection in object (= world) coordinates, tile size in studs
            tc = nt.nodes.new("ShaderNodeTexCoord")
            mp = nt.nodes.new("ShaderNodeMapping")
            mp.inputs["Scale"].default_value = (1 / tile_studs,) * 3
            nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
            nt.links.new(mp.outputs["Vector"], tn.inputs["Vector"])
            tn.projection = "BOX"
            tn.projection_blend = 0.05
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.blend_type = "MULTIPLY"
        mix.inputs["Factor"].default_value = 1.0
        mix.inputs[6].default_value = rgb
        nt.links.new(tn.outputs["Color"], mix.inputs[7])
        nt.links.new(mix.outputs[2], bsdf.inputs["Base Color"])
        if alpha:
            nt.links.new(tn.outputs["Alpha"], bsdf.inputs["Alpha"])
            m.blend_method = "HASHED" if hasattr(m, "blend_method") else None
    else:
        bsdf.inputs["Base Color"].default_value = rgb
    bsdf.inputs["Roughness"].default_value = 0.85
    mats[name] = m
    return m


def material_for(p):
    look = p["m"]
    if look in LOOKS:
        lk = LOOKS[look]
        return tex_material(look, p["c"], lk["tile_m"] * S, TEX / f"{lk['texture']}.png")
    return tex_material(look, p["c"])


# ------------------------------------------------------------------ geometry batching
batches = {}   # material -> (verts, faces)
cards = []     # (verts, color)
marks = []     # (verts, uv, key)


def add_prim(p):
    s, (px, py, pz), (sx, sy, sz) = p["s"], p["p"], p["z"]
    R = rot(*p["r"])
    v, f = shape_local(s, sx, sy, sz)
    V = (np.array(v) @ R.T + np.array([px, py, pz])) @ C.T
    if s == "K":  # leaf card = quad in local XY plane, both faces textured
        q = (np.array([(-sx / 2, -sy / 2, 0), (sx / 2, -sy / 2, 0), (sx / 2, sy / 2, 0), (-sx / 2, sy / 2, 0)]) @ R.T
             + np.array([px, py, pz])) @ C.T
        cards.append((q, p["c"]))
        return
    mat = material_for(p)
    vs, fs = batches.setdefault(mat.name, ([], []))
    base = len(vs)
    vs.extend(V.tolist())
    fs.extend([tuple(base + i for i in face) for face in f])
    if p.get("mk"):  # road marking overlay on the top face
        q = (np.array([(-sx / 2, sy / 2 + 0.05, -sz / 2), (sx / 2, sy / 2 + 0.05, -sz / 2),
                       (sx / 2, sy / 2 + 0.05, sz / 2), (-sx / 2, sy / 2 + 0.05, sz / 2)]) @ R.T
             + np.array([px, py, pz])) @ C.T
        rep = sz / 12.0
        marks.append((q, [(0, 0), (1, 0), (1, rep), (0, rep)], p["mk"]))


def inside(p, pad=40):
    x, z = p["p"][0] / S, p["p"][2] / S
    return WIN[0] - pad <= x <= WIN[2] + pad and WIN[1] - pad <= z <= WIN[3] + pad


n = 0
for kind in ("buildings", "roads"):
    for f in sorted((STY / kind).glob("*.json")):
        for e in json.loads(f.read_text()):
            if inside(e["p"][0]):
                for p in e["p"]:
                    add_prim(p); n += 1
for f in sorted((STY / "trees").glob("*.json")):
    for p in json.loads(f.read_text()):
        if inside(p):
            add_prim(p); n += 1
removed = set()
for lm in LANDMARKS:
    spec = json.loads(Path(lm).read_text())
    for p in spec["prims"]:
        add_prim(p); n += 1
print(f"prims in window: {n}")


def make_obj(name, verts, faces, mat, uvs=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    if uvs is not None:
        uv = me.uv_layers.new()
        for li, loop in enumerate(me.loops):
            uv.data[li].uv = uvs[loop.vertex_index]
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    scene.collection.objects.link(ob)
    return ob


for mname, (vs, fs) in batches.items():
    make_obj(mname, vs, fs, bpy.data.materials[mname])
for i, (q, col) in enumerate(cards):
    make_obj(f"leaf{i}", q.tolist(), [(0, 1, 2, 3)], tex_material("leaf", col, image=TEX / "foliage.png", alpha=True),
             uvs=[(0, 0), (1, 0), (1, 1), (0, 1)])
for i, (q, uv, key) in enumerate(marks):
    mat = tex_material(f"mark{key}", [255, 255, 255], image=TEX / f"road_{key}lane.png", alpha=True)
    make_obj(f"mark{i}", q.tolist(), [(0, 1, 2, 3)], mat, uvs=uv)

# ------------------------------------------------------------------ terrain + water (from the DEM)
# Blender's Python can't import the venv's rasterio, so the DEM is pre-exported as .npy:
#   .venv/bin/python -c "import numpy as np, rasterio; np.save('data/processed/previews_dem_1m.npy',
#        rasterio.open('data/processed/hazard/dem_filled.tif').read(1).astype('float32'))"
Z = np.load(ROOT / "data/processed/previews_dem_1m.npy")
x0, top = 558520, 4187215
step = 4
c0, c1 = int(WIN[0] - 80), int(WIN[2] + 80)
r0, r1 = int(-(WIN[3] + 80) + (top - 4182723) - (top - 4182723)), 0
ys = np.arange(int(4492 + WIN[1] - 80), int(4492 + WIN[3] + 80), step)  # rows from top
xs = np.arange(c0, c1, step)
ys = ys[(ys >= 0) & (ys < Z.shape[0])]
xs = xs[(xs >= 0) & (xs < Z.shape[1])]
verts, faces = [], []
for j, r in enumerate(ys):
    for i, c in enumerate(xs):
        zl = -(4492 - r)  # local z (meters)
        verts.append((c * S, -zl * S, float(Z[r, c]) * S - 0.2))
nx = len(xs)
for j in range(len(ys) - 1):
    for i in range(nx - 1):
        a = j * nx + i
        faces.append((a, a + 1, a + nx + 1, a + nx))
make_obj("terrain", verts, faces, tex_material("ground", [122, 120, 112]))
wl = 1.941 * S
make_obj("water", [(c0 * S, -(WIN[1] - 200) * S, wl), (c1 * S, -(WIN[1] - 200) * S, wl),
                   (c1 * S, -(WIN[3] + 200) * S, wl), (c0 * S, -(WIN[3] + 200) * S, wl)],
         [(0, 1, 2, 3)], tex_material("water", [40, 96, 120]))

# ------------------------------------------------------------------ lights, camera, render
world = bpy.data.worlds.new("w")
scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes["Background"]
bg.inputs["Color"].default_value = (0.45, 0.6, 0.85, 1)
bg.inputs["Strength"].default_value = 0.55
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
sun.data.energy = 4.5
sun.data.angle = math.radians(1.5)
sun.rotation_euler = (math.radians(58), 0, math.radians(235))  # late afternoon, from the WSW
scene.collection.objects.link(sun)

cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
cam.data.clip_end = 60000
scene.collection.objects.link(cam)
scene.camera = cam
try:
    scene.render.engine = "BLENDER_EEVEE_NEXT"
except TypeError:
    scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x, scene.render.resolution_y = 1600, 900
scene.view_settings.look = "AgX - Medium High Contrast" if False else scene.view_settings.look
scene.view_settings.view_transform = "AgX" if "AgX" in [i.identifier for i in scene.view_settings.bl_rna.properties["view_transform"].enum_items] else "Filmic"


def look(eye, target, lens=28):
    from mathutils import Vector
    e, t = Vector(eye), Vector(target)
    cam.location = e
    cam.rotation_euler = (t - e).to_track_quat("-Z", "Y").to_euler()
    cam.data.lens = lens


def gz(xm, zm):
    r = int(4492 + zm); c = int(xm)
    return float(Z[min(max(r, 0), Z.shape[0] - 1), min(max(c, 0), Z.shape[1] - 1)])


cx, cz = (WIN[0] + WIN[2]) / 2, (WIN[1] + WIN[3]) / 2
span = max(WIN[2] - WIN[0], WIN[3] - WIN[1])
views = {
    "aerial": ((cx - 0.35 * span) * S, -(cz + 0.55 * span) * S, (gz(cx, cz) + 0.55 * span) * S, (cx * S, -cz * S, gz(cx, cz) * S), 26),
    "street": (STREET[0] * S, -STREET[1] * S, (gz(*STREET) + 1.7) * S,
               ((STREET[0] + 60) * S, -(STREET[1] - 25) * S, (gz(*STREET) + 6) * S), 22),
    "close": ((STREET[0] - 70) * S, -(STREET[1] + 70) * S, (gz(*STREET) + 45) * S, (STREET[0] * S, -STREET[1] * S, gz(*STREET) * S), 30),
}
for name, (ex, ey, ez, tgt, lens) in views.items():
    look((ex, ey, ez), tgt, lens)
    scene.render.filepath = str(OUT / f"{name}.png")
    bpy.ops.render.render(write_still=True)
    print("rendered", scene.render.filepath)

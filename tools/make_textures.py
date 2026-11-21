"""Procedural textures for the Roblox viewer (MaterialVariants, road markings, foliage).

Facade tiles = one window bay x one floor (3.2 m x 3.2 m -> StudsPerTile 11.43). They are drawn
near-white so the part Color tints them (map modes recolor buildings), with darker glass.
Each surface texture also gets a normal map derived from a height map.
Output: roblox/textures/<name>.png (+ <name>_n.png), 512 px (road markings 256 x 512, alpha).
"""
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

OUT = Path(__file__).resolve().parent.parent / "roblox" / "textures"
OUT.mkdir(parents=True, exist_ok=True)
N = 512
rng = np.random.default_rng(7)  # fixed seed: deterministic textures
PX_PER_M = N / 3.2


def m(v):
    return int(round(v * PX_PER_M))


def noise(scale=1.0, blur=1.5):
    a = rng.normal(0, 1, (N, N)).astype(np.float32)
    img = Image.fromarray(((a - a.min()) / (a.max() - a.min()) * 255).astype(np.uint8))
    return np.asarray(img.filter(ImageFilter.GaussianBlur(blur)), np.float32) / 255 * scale


def save(name, rgb, height=None, alpha=None):
    rgb = np.clip(rgb, 0, 255).astype(np.uint8)
    if alpha is not None:
        Image.fromarray(np.dstack([rgb, np.clip(alpha, 0, 255).astype(np.uint8)]), "RGBA").save(OUT / f"{name}.png")
    else:
        Image.fromarray(rgb, "RGB").save(OUT / f"{name}.png")
    if height is not None:  # normal map (OpenGL style, +Y up), strength tuned for subtle relief
        gy, gx = np.gradient(height.astype(np.float32))
        k = 6.0
        nx, ny, nz = -gx * k, gy * k, np.ones_like(gx)
        ln = np.sqrt(nx ** 2 + ny ** 2 + nz ** 2)
        nm = np.dstack([nx / ln, ny / ln, nz / ln]) * 127.5 + 127.5
        Image.fromarray(nm.astype(np.uint8), "RGB").save(OUT / f"{name}_n.png")


def window(rgb, h, x0, y0, w, hh, frame=(70, 70, 72), trim=None, trim_w=0.08, mullion=True):
    """Glass with a sky-reflection gradient, optional trim, frame and mullions; recessed in h."""
    X0, Y0, W, HH = m(x0), m(y0), m(w), m(hh)
    if trim:
        t = m(trim_w)
        rgb[Y0 - t:Y0 + HH + t, X0 - t:X0 + W + t] = trim
        h[Y0 - t:Y0 + HH + t, X0 - t:X0 + W + t] = 0.9
    grad = np.linspace(0, 1, HH)[:, None]
    glass = np.dstack([60 + 50 * grad, 78 + 50 * grad, 98 + 45 * grad]) * np.ones((HH, W, 1))
    glass += rng.normal(0, 3, glass.shape)
    rgb[Y0:Y0 + HH, X0:X0 + W] = glass
    h[Y0:Y0 + HH, X0:X0 + W] = 0.2
    f = max(3, m(0.04))
    rgb[Y0:Y0 + f, X0:X0 + W] = frame
    rgb[Y0 + HH - f:Y0 + HH, X0:X0 + W] = frame
    rgb[Y0:Y0 + HH, X0:X0 + f] = frame
    rgb[Y0:Y0 + HH, X0 + W - f:X0 + W] = frame
    if mullion:
        mx = X0 + W // 2
        rgb[Y0:Y0 + HH, mx - f // 2:mx + f // 2 + 1] = frame
    return rgb, h


def base(level, var=6):
    rgb = np.full((N, N, 3), level, np.float32) + (noise(var * 2) - var)[..., None]
    return rgb, np.full((N, N), 0.6, np.float32) + noise(0.05)


# --- facades ------------------------------------------------------------------------------
# 1. lap siding (Victorians / houses): horizontal boards with shadow lines, white trim window
rgb, h = base(232)
for y in range(0, N, m(0.18)):
    rgb[y:y + 3] -= 45
    h[y:y + 4] = 0.35
rgb, h = window(rgb, h, 1.05, 0.75, 1.1, 1.65, trim=(250, 250, 248), trim_w=0.12)
rgb[m(2.48):m(2.56), m(0.9):m(2.3)] = 245  # sill
save("facade_siding", rgb, h)

# 2. stucco (houses / apartments): plaster noise, dark-framed window
rgb, h = base(228, 10)
h += noise(0.25, 3)
rgb, h = window(rgb, h, 0.95, 0.8, 1.3, 1.5, frame=(55, 55, 58))
save("facade_stucco", rgb, h)

# 3. brick (older apartments / commercial / civic): running bond + light lintel
rgb, h = base(222, 4)
bw, bh = m(0.215), m(0.075)
for r, y in enumerate(range(0, N, bh)):
    rgb[y:y + 2] = 170
    h[y:y + 2] = 0.3
    off = (bw // 2) * (r % 2)
    for x in range(-off, N, bw):
        if 0 <= x < N:
            rgb[y:y + bh, x:x + 2] = 170
            h[y:y + bh, x:x + 2] = 0.3
    rgb[y:y + bh] += rng.normal(0, 7)  # per-course variation
rgb, h = window(rgb, h, 1.0, 0.85, 1.2, 1.6, frame=(60, 55, 52))
rgb[m(0.70):m(0.85), m(0.92):m(2.28)] = 240  # stone lintel
h[m(0.70):m(0.85), m(0.92):m(2.28)] = 0.95
save("facade_brick", rgb, h)

# 4. concrete office: panel seams + ribbon window band
rgb, h = base(215, 5)
rgb[:, ::m(1.6)] -= 25
h[:, ::m(1.6)] = 0.4
rgb[0:3] -= 30
rgb, h = window(rgb, h, 0.0, 0.9, 3.2, 1.45, frame=(80, 82, 86), mullion=False)
for x in range(0, N, m(1.6)):
    rgb[m(0.9):m(2.35), x:x + 5] = (80, 82, 86)
save("facade_concrete", rgb, h)

# 5. glass curtain wall (towers): two panes per tile, spandrel at the floor line
rgb = np.zeros((N, N, 3), np.float32)
h = np.full((N, N), 0.5, np.float32)
grad = np.linspace(0, 1, N)[:, None]
rgb[:] = np.dstack([95 + 60 * grad, 120 + 55 * grad, 150 + 50 * grad]) * np.ones((N, N, 1))
rgb[m(2.75):, :] = (150, 158, 168)  # spandrel
for x in (0, N // 2):
    rgb[:, x:x + 6] = (190, 195, 200)
    h[:, x:x + 6] = 0.9
rgb[m(2.75):m(2.75) + 6] = (190, 195, 200)
save("facade_glass", rgb, h)

# 6. corrugated metal (industrial / Port sheds): vertical ribs, no windows
rgb, h = base(220, 4)
x = np.arange(N)
rib = (np.sin(x / m(0.15) * 2 * np.pi) * 0.5 + 0.5)[None, :]
rgb += (rib[..., None] * 28 - 14)
h = np.tile(rib, (N, 1)).astype(np.float32)
rgb[m(1.6):m(1.6) + 3] -= 35
save("facade_metal", rgb, h)

# 7. storefront (ground floor of commercial blocks): big display window, transom, sign band
rgb, h = base(226, 4)
rgb[0:m(0.55)] = 70                       # dark sign / awning band (tinted by building color)
h[0:m(0.55)] = 0.95
rgb, h = window(rgb, h, 0.18, 0.75, 2.84, 2.25, frame=(48, 48, 50))
rgb[m(3.0):] = 150                        # base / kick plate
save("facade_storefront", rgb, h)

# --- roofs --------------------------------------------------------------------------------
rgb, h = base(200, 8)
for r, y in enumerate(range(0, N, m(0.14))):
    rgb[y:y + 3] -= 50
    h[y:y + 3] = 0.2
    off = (m(0.33) // 2) * (r % 2)
    for xx in range(-off, N, m(0.33)):
        if 0 <= xx < N:
            rgb[y:y + m(0.14), xx:xx + 2] -= 30
    rgb[y:y + m(0.14)] += rng.normal(0, 10)
save("roof_shingle", rgb, h)

rgb, h = base(190, 14)
h = noise(1.0, 0.8)
rgb += (noise(30, 0.6) - 15)[..., None]
rgb[:, ::m(1.0)] -= 18  # membrane seams
save("roof_flat", rgb, h)

# --- sidewalk -----------------------------------------------------------------------------
rgb, h = base(205, 6)
rgb[:, ::m(1.6)] -= 40
rgb[::m(1.6), :] -= 40
h[:, ::m(1.6)] = 0.2
h[::m(1.6), :] = 0.2
save("sidewalk", rgb, h)

# --- road markings (Texture on the road part's top face; alpha = paint only) ----------------
# U = across the road (one tile = road width), V = along the road (one tile = 12 studs ~ 3.4 m;
# dashes 1/3 of the period). Image x = across, y = along.
W, L = 256, 512


def markings(lanes):
    a = np.zeros((L, W), np.float32)
    rgb = np.zeros((L, W, 3), np.float32)
    def stripe(xc, w, color, dashed=False):
        x0, x1 = int(xc - w / 2), int(xc + w / 2) + 1
        ys = slice(0, L // 3) if dashed else slice(0, L)
        a[ys, x0:x1] = 235
        rgb[ys, x0:x1] = color
    yellow, white = (235, 190, 40), (240, 240, 240)
    stripe(W / 2 - 4, 3, yellow); stripe(W / 2 + 4, 3, yellow)      # double yellow center
    stripe(6, 3, white); stripe(W - 7, 3, white)                      # edge lines
    if lanes >= 4:
        stripe(W / 4, 3, white, dashed=True); stripe(3 * W / 4, 3, white, dashed=True)
    a *= (0.85 + 0.15 * rng.random((L, W)))                          # worn paint
    return rgb, a


for lanes in (2, 4):
    rgb, a = markings(lanes)
    Image.fromarray(np.dstack([rgb.astype(np.uint8), a.astype(np.uint8)]), "RGBA").save(OUT / f"road_{lanes}lane.png")

# --- foliage (tree leaf cards: alpha cut-out) -----------------------------------------------
F = 512
a = np.zeros((F, F), np.float32)
rgb = np.zeros((F, F, 3), np.float32)
yy, xx = np.mgrid[0:F, 0:F]
cx, cy = F / 2, F / 2
lobes = [(cx + F * 0.18 * np.cos(a), cy - F * 0.05 + F * 0.16 * np.sin(a), F * rng.uniform(0.17, 0.24))
         for a in np.linspace(0, 2 * np.pi, 7, endpoint=False)] + [(cx, cy - F * 0.08, F * 0.26)]
for _ in range(3400):  # leaf clusters inside an irregular, lobed crown silhouette
    lx, ly, lr = lobes[rng.integers(len(lobes))]
    r = lr * np.sqrt(rng.random())
    t = rng.random() * 2 * np.pi
    x, y = lx + r * np.cos(t), ly + r * np.sin(t)
    s = rng.uniform(5, 13)
    g = rng.uniform(0.75, 1.15)
    sl = (slice(max(0, int(y - s)), min(F, int(y + s))), slice(max(0, int(x - s)), min(F, int(x + s))))
    d = ((xx[sl] - x) ** 2 + ((yy[sl] - y) * 1.6) ** 2) < s * s
    a[sl][d] = 255
    shade = (0.45 + 0.55 * (1 - y / F)) * rng.uniform(0.8, 1.1)  # lighter on top, mottled
    rgb[sl][d] = np.array([62, 104, 48]) * g * shade
Image.fromarray(np.dstack([np.clip(rgb, 0, 255).astype(np.uint8), a.astype(np.uint8)]), "RGBA").save(OUT / "foliage.png")

print("wrote", sorted(p.name for p in OUT.glob("*.png")))

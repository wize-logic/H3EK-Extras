"""A stock map's ground, from its structure BSP's collision geometry.

The shipped cache keeps no pathfinding mesh, so this reads the collision BSP
from the BSP's tag resources (cache_resources.py), plus every collidable piece of
instanced geometry (rocks, ice, bases) placed by the BSP. Surfaces that face
up are rasterized into a height map the layout uses to put things on the
ground instead of guessing.

    python3 -m h3kit.bsp_terrain [map] [out.png]
"""

import struct
import sys

import numpy as np

from . import cache as h3cache
from . import env
from .cache_resources import ADDRESS_DATA, Resources

FLOOR_NORMAL_Z = 0.3
SURFACE_TWO_SIDED = 1 << 0
SURFACE_INVISIBLE = 1 << 1

SBSP_INSTANCES = 0x1C0
INSTANCE_SIZE = 0x78
INSTANCE_RENDER_ONLY = 1 << 1
# structure_bsp_tag_resources: collision bsps, large collision bsps, instanced geometry
TAG_RESOURCES_COLLISION = 0x0
TAG_RESOURCES_INSTANCES = 0x18
INSTANCE_DEFINITION_SIZE = 0xC4
INSTANCE_COLLISION = 0x14
COLLISION_BSP_SIZE = 0x60
# blocks of a collision bsp
PLANES, SURFACES, EDGES, VERTICES = 0xC, 0x3C, 0x48, 0x54

SURFACE = np.dtype([("plane", "<u2"), ("edge", "<u2"), ("material", "<i2"), ("set", "<i2"),
                    ("breakable", "<i2"), ("flags", "u1"), ("best", "u1")])
EDGE = np.dtype([("v", "<u2", 2), ("forward", "<u2"), ("reverse", "<u2"), ("left", "<u2"), ("right", "<u2")])
VERTEX = np.dtype([("p", "<f4", 3), ("edge", "<u2"), ("sink", "<u2")])


def _array(resource, data, offset, dtype):
    n, kind, at = resource.block(offset)
    if n <= 0 or kind != ADDRESS_DATA:
        return np.zeros(0, dtype)
    return np.frombuffer(data, dtype=dtype, count=n, offset=at)


def floor_triangles(resource, data, offset):
    """Upward-facing triangles of the collision bsp at `offset` in the definition, as an (n, 3, 3) array."""
    surfaces = _array(resource, data, offset + SURFACES, SURFACE)
    edges = _array(resource, data, offset + EDGES, EDGE)
    points = _array(resource, data, offset + VERTICES, VERTEX)["p"].astype(np.float64)
    if not len(surfaces):
        return np.zeros((0, 3, 3))
    v, fwd, rev, left = edges["v"], edges["forward"], edges["reverse"], edges["left"]
    tris = []
    for s, (first, flags) in enumerate(zip(surfaces["edge"], surfaces["flags"])):
        if flags & SURFACE_INVISIBLE:
            continue
        poly, e = [], first
        for _ in range(64):
            if left[e] == s:
                poly.append(v[e][0])
                e = fwd[e]
            else:
                poly.append(v[e][1])
                e = rev[e]
            if e == first:
                break
        if len(poly) < 3:
            continue
        p = points[poly]
        n = np.cross(p[1:-1] - p[0], p[2:] - p[0]).sum(axis=0)
        length = np.linalg.norm(n)
        if length < 1e-9:
            continue
        nz = n[2] / length
        if nz > FLOOR_NORMAL_Z or (flags & SURFACE_TWO_SIDED and nz < -FLOOR_NORMAL_Z):
            for k in range(1, len(p) - 1):
                tris.append((p[0], p[k], p[k + 1]))
    return np.array(tris).reshape(-1, 3, 3)


class Terrain:
    def __init__(self, path, cell=1.0):
        cache = h3cache.Cache(path)
        resources = Resources(cache)
        tris = []
        for bsp in (t for t in cache.tags if t and t.group == "sbsp"):
            res = next(r for r in resources.owned_by(bsp) if r.kind == "structure_bsp_tag_resources")
            data = res.data
            n, _, at = res.block(res.base + TAG_RESOURCES_COLLISION)
            for i in range(max(n, 0)):
                tris.append(floor_triangles(res, data, at + i * COLLISION_BSP_SIZE))
            n, _, at = res.block(res.base + TAG_RESOURCES_INSTANCES)
            definitions = [floor_triangles(res, data, at + i * INSTANCE_DEFINITION_SIZE + INSTANCE_COLLISION)
                           for i in range(max(n, 0))]
            tris.extend(self._instances(cache, bsp, definitions))
        cache.close()
        self.triangles = np.concatenate([t for t in tris if len(t)])
        self.cell = cell
        self._rasterize()

    @staticmethod
    def _instances(cache, bsp, definitions):
        count, base = cache.block(bsp.offset, SBSP_INSTANCES)
        for i in range(count):
            e = cache.read(base + i * INSTANCE_SIZE, INSTANCE_SIZE)
            scale, = struct.unpack_from("<f", e, 0)
            axes = np.array(struct.unpack_from("<9f", e, 0x4)).reshape(3, 3)  # forward, left, up
            position = np.array(struct.unpack_from("<3f", e, 0x28))
            index, flags = struct.unpack_from("<hH", e, 0x34)
            if flags & INSTANCE_RENDER_ONLY or not 0 <= index < len(definitions) or not len(definitions[index]):
                continue
            yield definitions[index] @ (scale * axes) + position

    def _rasterize(self):
        t = self.triangles
        cs = self.cell
        self.x0 = float(np.floor(t[:, :, 0].min()))
        self.y0 = float(np.floor(t[:, :, 1].min()))
        self.w = int((t[:, :, 0].max() - self.x0) / cs) + 2
        self.h = int((t[:, :, 1].max() - self.y0) / cs) + 2
        top = np.full(self.h * self.w, -np.inf)
        bottom = np.full(self.h * self.w, np.inf)

        a, b, c = t[:, 0], t[:, 1], t[:, 2]
        det = (b[:, 1] - c[:, 1]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (a[:, 1] - c[:, 1])
        keep = np.abs(det) > 1e-9
        a, b, c, det = a[keep], b[keep], c[keep], det[keep]
        lo = np.floor((np.minimum(np.minimum(a, b), c)[:, :2] - (self.x0, self.y0)) / cs).astype(int)
        hi = np.ceil((np.maximum(np.maximum(a, b), c)[:, :2] - (self.x0, self.y0)) / cs).astype(int)
        span = (hi - lo).max(axis=1)
        # small triangles all at once over a fixed window, big ones one by one
        for group in (np.flatnonzero(span <= 3), np.flatnonzero(span > 3)):
            if not len(group):
                continue
            windows = [(group, 4)] if span[group].max() <= 3 else [(np.array([g]), span[g] + 1) for g in group]
            for ids, size in windows:
                di, dj = np.meshgrid(np.arange(size), np.arange(size))
                i = lo[ids, 0][:, None] + di.ravel()
                j = lo[ids, 1][:, None] + dj.ravel()
                x = self.x0 + i * cs
                y = self.y0 + j * cs
                A, B, C, D = a[ids][:, None], b[ids][:, None], c[ids][:, None], det[ids][:, None]
                l1 = ((B[..., 1] - C[..., 1]) * (x - C[..., 0]) + (C[..., 0] - B[..., 0]) * (y - C[..., 1])) / D
                l2 = ((C[..., 1] - A[..., 1]) * (x - C[..., 0]) + (A[..., 0] - C[..., 0]) * (y - C[..., 1])) / D
                l3 = 1 - l1 - l2
                z = l1 * A[..., 2] + l2 * B[..., 2] + l3 * C[..., 2]
                inside = (np.minimum(np.minimum(l1, l2), l3) >= -0.02) & (i >= 0) & (i < self.w) & (j >= 0) & (j < self.h)
                cells = (j * self.w + i)[inside]
                np.maximum.at(top, cells, z[inside])
                np.minimum.at(bottom, cells, z[inside])
        top[np.isinf(top)] = np.nan
        bottom[np.isinf(bottom)] = np.nan
        self.top = top.reshape(self.h, self.w)
        self.bottom = bottom.reshape(self.h, self.w)

    def _window(self, grid, x, y, radius):
        r = int(radius / self.cell)
        i = int(round((x - self.x0) / self.cell))
        j = int(round((y - self.y0) / self.cell))
        if not (-r <= i < self.w + r and -r <= j < self.h + r):
            return None
        w = grid[max(0, j - r):max(0, j + r + 1), max(0, i - r):max(0, i + r + 1)]
        return w if w.size and not np.all(np.isnan(w)) else None

    def height(self, x, y, radius=0):
        """Highest walkable surface at (x, y), searching `radius` cells around; None off the ground."""
        w = self._window(self.top, x, y, radius)
        return None if w is None else float(np.nanmax(w))

    def ground(self, x, y, radius=0):
        """Lowest walkable surface at (x, y): the terrain under any bridge or roof."""
        w = self._window(self.bottom, x, y, radius)
        return None if w is None else float(np.nanmin(w))

    def slope(self, x, y, d=3.0):
        """Rise over run of the ground across (x, y), worst axis."""
        h = self.ground(x, y)
        worst = 0.0
        for dx, dy in ((d, 0), (-d, 0), (0, d), (0, -d)):
            n = self.ground(x + dx, y + dy)
            if h is None or n is None:
                return None
            worst = max(worst, abs(n - h) / d)
        return worst

    def image(self, scale=3, marks=()):
        from PIL import Image, ImageDraw
        z = self.bottom[::-1]
        lo, hi = float(np.nanmin(z)), float(np.nanmax(z))
        t = np.nan_to_num((z - lo) / (hi - lo), nan=-1)
        rgb = np.stack([40 + 215 * t, 90 + 140 * t, 160 + 95 * t], axis=-1)
        rgb[t < 0] = (20, 20, 30)
        img = Image.fromarray(rgb.clip(0, 255).astype(np.uint8)).resize((self.w * scale, self.h * scale), Image.NEAREST)
        d = ImageDraw.Draw(img)
        for x in range(-250, 300, 50):
            px = (x - self.x0) / self.cell * scale
            d.line([(px, 0), (px, img.height)], fill=(80, 80, 80))
            d.text((px + 2, 2), str(x), fill=(255, 255, 0))
        for y in range(-300, 250, 50):
            py = (self.h - 1 - (y - self.y0) / self.cell) * scale
            d.line([(0, py), (img.width, py)], fill=(80, 80, 80))
            d.text((2, py + 2), str(y), fill=(255, 255, 0))
        for x, y, col in marks:
            px = (x - self.x0) / self.cell * scale
            py = (self.h - 1 - (y - self.y0) / self.cell) * scale
            d.ellipse([px - 3, py - 3, px + 3, py + 3], fill=col)
        return img, (lo, hi)


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else str(env.MCC_MAPS / "sidewinder.map")
    t = Terrain(path)
    print(f"{len(t.triangles)} floor triangles, x {t.x0:.0f}..{t.x0 + t.w * t.cell:.0f}, "
          f"y {t.y0:.0f}..{t.y0 + t.h * t.cell:.0f}")
    if len(sys.argv) > 2:
        img, (lo, hi) = t.image()
        img.save(sys.argv[2])
        print(f"height {lo:.1f}..{hi:.1f} -> {sys.argv[2]}")

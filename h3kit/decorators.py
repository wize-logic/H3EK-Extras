"""Decorations (trees, rocks, bushes, snow clumps) through Halo 3's decorator
system, which costs no object slots at all.

A map scatters placements per decorator set with a Scatter, then
resource_lines() turns them into mbedit lines for a copy of the base map's
scenario_decorators_resource (the build saves it as the new map's own), and
tag_script() makes the map's own decorator sets (stock ones with longer
fades, say).

How the tag stores decorators (from tool export-tag-to-xml of the stock
resource and of other maps'):
  * decorators[0] holds a palette (the editor's brush), "decorator count"
    (the total of all placements; tool asserts it matches) and "sets": one
    element per decorator_set tag, each with its own "placements" block.
  * A placement is plain world data: position, type index (into the set's
    "decorator types"), rotation as an (i, j, k, w) quaternion that turns the
    model's +z onto the ground normal, scale, tint colour, motion scale and
    ground tint. Nothing is compressed in the tag.
  * The per-BSP and per-cluster fields (runtime bsp index, cluster index,
    cluster decorator set index, block x/y) are filled by build-cache-file
    into the BSP's clusters (decorator groups) and its decorator sets.
  * Decorators have no collision: players and vehicles pass through them,
    so keep them off drivable lanes and out of objects and buildings.
  * The build drops placements whose origin sits more than ~0.15 under the
    collision surface (Scatter.sink).

A set is (key, decorator_set tag, number of decorator types, (scale min, max)).
"""

import math
import random

SETS_PATH = "decorators[0]/sets"


def tag_script(own_dir, tags):
    """mbedit lines that make a map's own decorator sets: tags = [(name, copied
    from, {field: value})], saved as own_dir\\<name>."""
    lines = []
    for name, src, edits in tags:
        lines.append(f"load\t{src}\tdecorator_set")
        lines += [f"set\t{field}\t{value}" for field, value in edits.items()]
        lines.append(f"saveas\t{own_dir}\\{name}\tdecorator_set")
    return lines


class Noise:
    """Smooth value noise in 0..1 on a lattice `scale` units apart."""

    def __init__(self, scale, seed):
        self.scale = scale
        rng = random.Random(seed)
        self.lattice = [[rng.random() for _ in range(64)] for _ in range(64)]

    def __call__(self, x, y):
        gx, gy = x / self.scale + 1000.0, y / self.scale + 1000.0
        ix, iy = int(gx), int(gy)
        fx, fy = gx - ix, gy - iy
        sx, sy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
        L = self.lattice
        a, b = L[ix % 64][iy % 64], L[(ix + 1) % 64][iy % 64]
        c, d = L[ix % 64][(iy + 1) % 64], L[(ix + 1) % 64][(iy + 1) % 64]
        return (a * (1 - sx) + b * sx) * (1 - sy) + (c * (1 - sx) + d * sx) * sy


def smooth(e0, e1, v):
    t = min(1.0, max(0.0, (v - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


def seg_dist(p, a, b):
    ax, ay = a
    dx, dy = b[0] - ax, b[1] - ay
    t = ((p[0] - ax) * dx + (p[1] - ay) * dy) / (dx * dx + dy * dy)
    t = min(1.0, max(0.0, t))
    return math.hypot(p[0] - ax - t * dx, p[1] - ay - t * dy)


def poly_dist(p, pts):
    return min(seg_dist(p, a, b) for a, b in zip(pts, pts[1:]))


def normal(terrain, x, y, d=1.5):
    hx = (terrain.ground(x + d, y) - terrain.ground(x - d, y)) / (2 * d)
    hy = (terrain.ground(x, y + d) - terrain.ground(x, y - d)) / (2 * d)
    n = (-hx, -hy, 1.0)
    k = math.sqrt(n[0] ** 2 + n[1] ** 2 + 1.0)
    return n[0] / k, n[1] / k, n[2] / k


def quat(n, yaw):
    """(i, j, k, w): spin `yaw` radians about +z, then tip +z onto normal n."""
    nx, ny, nz = n
    ang = math.acos(max(-1.0, min(1.0, nz)))
    s = math.hypot(nx, ny)
    ax, ay = (-ny / s, nx / s) if s > 1e-6 else (1.0, 0.0)   # axis z x n
    sa, ca = math.sin(ang / 2), math.cos(ang / 2)
    a = (ax * sa, ay * sa, 0.0, ca)
    b = (0.0, 0.0, math.sin(yaw / 2), math.cos(yaw / 2))
    # Hamilton product a * b
    return (a[3] * b[0] + a[0] * b[3] + a[1] * b[2] - a[2] * b[1],
            a[3] * b[1] - a[0] * b[2] + a[1] * b[3] + a[2] * b[0],
            a[3] * b[2] + a[0] * b[1] - a[1] * b[0] + a[2] * b[3],
            a[3] * b[3] - a[0] * b[0] - a[1] * b[1] - a[2] * b[2])


def lean(n, amount):
    """The normal blended toward straight up: 0 = upright, 1 = on the ground."""
    v = (n[0] * amount, n[1] * amount, 1 - amount + n[2] * amount)
    k = math.sqrt(sum(c * c for c in v))
    return tuple(c / k for c in v)


class Scatter:
    """Collects placements per set on a point-symmetric map: each is made on the
    red half (x > 0) and twinned, turned 180 degrees about the origin.
    keep.blocked(x, y, ...) says where nothing may go."""

    def __init__(self, terrain, keep, sets, seed, sink=0.08, edge=490.0):
        self.terrain = terrain
        self.keep = keep
        self.sets = {key: (tag, types, scale) for key, tag, types, scale in sets}
        self.sink = sink        # how far below the ground an origin may sit (the build drops deeper ones)
        self.edge = edge        # jitter_grid's extent (the ground's half size, less a margin)
        self.rng = random.Random(seed)
        self.placed = {key: [] for key, _, _, _ in sets}
        self._bucket = {}

    def put(self, key, x, y, upright=1.0, scale=None, tint=1.0, kind=None):
        """Place one decoration at (x, y) on the ground (and its twin at
        (-x, -y)). upright: 1 stands straight up, 0 lies along the ground's
        slope. The origin sits `sink` under the ground: never deeper, or the
        build drops it."""
        if x < 0.6:
            return False    # the twin line: the twin would stand on top of it
        _, types, (lo, hi) = self.sets[key]
        rng = self.rng
        n = normal(self.terrain, x, y)
        up = lean(n, 1 - upright)
        if upright >= 1:   # a few degrees of random tilt, like the stock brush
            t, a = math.radians(rng.uniform(0, 3)), rng.uniform(0, 2 * math.pi)
            up = (math.sin(t) * math.cos(a), math.sin(t) * math.sin(a), math.cos(t))
        yaw = rng.uniform(0, 2 * math.pi)
        s = scale if scale is not None else rng.uniform(lo, hi)
        kind = rng.randrange(types) if kind is None else kind
        for side in (1, -1):
            px, py = side * x, side * y
            z = self.terrain.ground(px, py) - self.sink
            # turning 180 degrees about z: the normal's x and y flip, the spin goes half a turn on
            q = quat((side * up[0], side * up[1], up[2]), yaw + (0.0 if side == 1 else math.pi))
            m = (side * n[0], side * n[1], n[2])
            self.placed[key].append(((px, py, z), kind, q, s, tint, m))
        return True

    def remember(self, x, y):
        """Note a point (a tree) for near()."""
        self._bucket.setdefault((int(x // 8), int(y // 8)), []).append((x, y))

    def near(self, x, y):
        i, j = int(x // 8), int(y // 8)
        for a in (i - 1, i, i + 1):
            for b in (j - 1, j, j + 1):
                yield from self._bucket.get((a, b), ())

    def jitter_grid(self, step, x0=1.0, x1=None, y0=None, y1=None):
        """Jittered grid points over the red half (x > 0), one per cell."""
        x1 = self.edge if x1 is None else x1
        y0 = -self.edge if y0 is None else y0
        y1 = self.edge if y1 is None else y1
        rng = self.rng
        nx = int((x1 - x0) / step)
        ny = int((y1 - y0) / step)
        for i in range(nx):
            for j in range(ny):
                yield (x0 + (i + rng.uniform(0.1, 0.9)) * step,
                       y0 + (j + rng.uniform(0.1, 0.9)) * step)


def mirrored(placed):
    """The placements made mirror-symmetric about y = 0, like a mirrored ground:
    those on red's left flank and blue's matching one (x * y >= 0) are kept, each
    with its mirror image (rotation reflected: (i, j, k, w) -> (-i, j, -k, w));
    the rest are dropped. Ones on the centre line stay single."""
    out = {}
    for key, items in placed.items():
        keep = []
        for (x, y, z), kind, (qi, qj, qk, qw), scale, tint, (nx, ny, nz) in items:
            if x * y < 0.0 and abs(y) >= 1.5:
                continue
            keep.append(((x, y, z), kind, (qi, qj, qk, qw), scale, tint, (nx, ny, nz)))
            if abs(y) >= 1.5:
                keep.append(((x, -y, z), kind, (-qi, qj, -qk, qw), scale, tint, (nx, -ny, nz)))
        out[key] = keep
    return out


def fmt(v):
    return ",".join(f"{c:.4f}" for c in v)


def resource_lines(placed, sets, stock_sets):
    """mbedit lines that turn a copy of the stock decorators resource (which has
    `stock_sets` sets) into the map's: every set repointed, `sets` in order, their
    placements ({set key: [((x, y, z), type, quaternion, scale, tint, normal)]})."""
    lines = []
    for i in range(stock_sets):
        lines.append(f"clear\t{SETS_PATH}[{i}]/placements")
    for i, (_, tag, _, _) in enumerate(sets):
        if i >= stock_sets:
            lines.append(f"add\t{SETS_PATH}")
        lines.append(f"set\t{SETS_PATH}[{i}]/decorator set\t{tag},decorator_set")
    total = 0
    for i, (key, _, _, _) in enumerate(sets):
        block = f"{SETS_PATH}[{i}]/placements"
        for k, (pos, kind, q, s, tint, n) in enumerate(placed.get(key, [])):
            el = f"{block}[{k}]"
            lines += [f"add\t{block}",
                      f"set\t{el}/position\t{fmt(pos)}",
                      f"set\t{el}/type index\t{kind}",
                      f"set\t{el}/rotation\t{fmt(q)}",
                      f"set\t{el}/scale\t{s:.4f}",
                      f"set\t{el}/tint color\t{fmt((tint, tint, tint))}",
                      f"set\t{el}/original point\t{fmt(pos)}",
                      f"set\t{el}/original normal\t{fmt(n)}",
                      f"set\t{el}/cluster index\t-1"]
            total += 1
    lines.append(f"set\tdecorators[0]/decorator count\t{total}")
    lines.append(f"set\tdecorators[0]/current bsp count\t{total}")
    return lines


def counts(placed):
    return {key: len(v) for key, v in placed.items() if v}

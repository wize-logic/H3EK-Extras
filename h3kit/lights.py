"""Point lights in front of every light fixture, for the lightmapper.

Why. A light material's emissive glow (a look's LIGHTING, written into the .ASS
materials) only lights what is very close to it: a ceiling panel of
1.2 x 0.3 at power 24 per square unit gives off ~9 units of light in all,
spread over a hemisphere, and the room under it stays nearly black. Halo 3's
own levels light their rooms with placed lights: Avalanche's structure
lighting info holds 79 "generic light instances" (66 omni, 13 spot) of 13
definitions, omni intensity 0.5-35 with far attenuation ending 1-11 units
away, colour matched to the fixture next to it. The .ASS carries such lights
as GENERIC_LIGHT objects (OMNI_LGT, SPOT_LGT, DIRECT_LGT, AMBIENT_LGT; the
Halo Blender toolset's file_ass/build_asset.py writes them), with one
instance each; tool structure turns them into those generic lights, and the
faux lightmapper bakes them into every surface around them, instanced
geometry included.

How. lights(objects, fixtures) finds the faces of the fixture materials in
each object, drops faces buried in solid parts of that object or of the
objects next to it (a panel's top inside the ceiling slab, which for a
storey is the next storey's floor), and puts one omni light OFFSET in front
of each fixture (each closed shell of fixture faces; a long strip gets one
per SPACING units). Lights under a roof come first, lights in the open are
left out, and the total is capped at MAX_LIGHTS. ass.write writes them.

fixtures: {material key: (intensity, attenuation reach in world units)}, one
light per fixture of those materials; a map's look module holds them
(FIXTURES) next to the materials' emissive strings, which give each light
its colour.

Units: positions and attenuation distances are world units here and x 100
in the .ASS (tool divides by 100, as for the vertices); hotspot angles are
degrees in the .ASS and radians in the tag; intensity passes through as is.
"""

import math

import numpy as np

# draft bakes no bounce light; medium does, and lights the same room ~3.3x
# brighter (room 0.21 -> 0.68, corridor 0.66 -> 2.3 at intensity 20). Set
# QUALITY to the calc_lm_farm_local.py quality before write_ass so rooms come
# out alike (build.py sets lights.QUALITY to the bake's quality). low/high: untested.
QUALITY = "draft"
QUALITY_SCALE = {"draft": 1.0, "direct_only": 1.0, "low": 0.35, "medium": 0.35, "high": 0.35, "super_slow": 0.35}
FADE_START = 0.35       # attenuation starts fading at this fraction of the reach
SPACING = 8.0           # a long fixture gets one light per SPACING units of its length
OFFSET = 0.35           # light sits this far in front of the fixture face
MIN_AREA = 0.05         # a cell with less exposed fixture area than this (square units) gets no light
MAX_LIGHTS = 400        # cap on the generic lights of the level (~360 are indoors)
SAMPLE = 0.4            # fixture faces are sampled this far apart
COVER = 40.0            # a light with geometry within COVER above it is indoors (placed first)


class Light:
    """One generic light: world position, colour 0..1, intensity, attenuation."""

    def __init__(self, pos, color, intensity, reach, kind="OMNI_LGT", near=0.3):
        self.pos = tuple(float(c) for c in pos)
        self.color = tuple(float(c) for c in color)
        self.intensity = float(intensity)
        self.reach = float(reach)
        self.kind = kind
        self.near = near

    def definition(self):
        """The .ASS GENERIC_LIGHT object body after its class line (rounded,
        so lights with the same look share one object/definition)."""
        r, g, b = self.color
        far0 = self.reach * FADE_START
        return (f"\"{self.kind}\"\n{r:.6f}\t{g:.6f}\t{b:.6f}\n{self.intensity:.6f}\n"
                # hotspot falloff size, hotspot size (degrees; -1 = none, as Avalanche's omnis)
                "-1.0000000000\n-1.0000000000\n"
                # near attenuation (fades in from 0 to `near`, as Avalanche's 0..0.2-0.43),
                # far attenuation (full to far0, nothing at reach), shape, aspect
                f"1\n0.0000\n{self.near * 100:.4f}\n"
                f"1\n{far0 * 100:.4f}\n{self.reach * 100:.4f}\n"
                "1\n1.0000000000\n")   # shape 1 = circle (as Avalanche's omnis)

    def __repr__(self):
        x, y, z = self.pos
        return f"Light({x:.1f},{y:.1f},{z:.1f} i={self.intensity:.1f} r={self.reach:.1f})"


def emissive_color(strings):
    """The colour in a material's .ASS emissive strings (look.emissive), or white."""
    for s in strings or []:
        if s.startswith("BM_LIGHTING_BASIC"):
            p = s.split()
            return float(p[2]), float(p[3]), float(p[4])
    return (1.0, 1.0, 1.0)


def colors_of(lighting):
    """{material key: colour} from a look's LIGHTING (key -> emissive strings)."""
    return {k: emissive_color(v) for k, v in lighting.items()}


class _Solids:
    """Point-in-solid and ray-up tests against one object's closed shells."""

    def __init__(self, verts, tris):
        P = np.array([v[0] for v in verts], dtype=float)
        T = np.array([t[1:] for t in tris], dtype=int)
        self.A, self.B, self.C = P[T[:, 0]], P[T[:, 1]], P[T[:, 2]]
        # shells: triangles joined through vertex positions (each polygon has
        # its own vertices, but a shell's polygons meet at the same points)
        key = {}
        parent = list(range(len(T)))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i
        for ti, t in enumerate(T):
            for vi in t:
                k = tuple(np.round(P[vi], 3))
                if k in key:
                    a, b = find(ti), find(key[k])
                    if a != b:
                        parent[a] = b
                else:
                    key[k] = ti
        roots = np.array([find(i) for i in range(len(T))])
        _, self.shell = np.unique(roots, return_inverse=True)
        self.lo = np.minimum(np.minimum(self.A, self.B), self.C)
        self.hi = np.maximum(np.maximum(self.A, self.B), self.C)

    def _up(self, Q):
        """For points Q (n x 3): per point, the shells a vertical ray up from it
        crosses an odd number of times (inside), and the nearest hit above."""
        Q = np.asarray(Q, dtype=float).reshape(-1, 3)
        inside = np.zeros(len(Q), dtype=bool)
        above = np.full(len(Q), np.inf)
        if not len(self.A):
            return inside, above
        nshell = int(self.shell.max()) + 1
        for s in range(0, len(Q), 32):
            q = Q[s:s + 32]
            x = q[:, 0:1] + 1.37e-4     # nudged off shared edges
            y = q[:, 1:2] + 2.91e-4
            z = q[:, 2:3]
            m = (self.lo[:, 0] <= x) & (self.hi[:, 0] >= x) & (self.lo[:, 1] <= y) & \
                (self.hi[:, 1] >= y) & (self.hi[:, 2] > z)
            pi, ti = np.nonzero(m)
            if not len(ti):
                continue
            A, B, C = self.A[ti], self.B[ti], self.C[ti]
            px, py, pz = x[pi, 0], y[pi, 0], z[pi, 0]
            d = (B[:, 1] - C[:, 1]) * (A[:, 0] - C[:, 0]) + (C[:, 0] - B[:, 0]) * (A[:, 1] - C[:, 1])
            ok = np.abs(d) > 1e-12
            d = np.where(ok, d, 1.0)
            l1 = ((B[:, 1] - C[:, 1]) * (px - C[:, 0]) + (C[:, 0] - B[:, 0]) * (py - C[:, 1])) / d
            l2 = ((C[:, 1] - A[:, 1]) * (px - C[:, 0]) + (A[:, 0] - C[:, 0]) * (py - C[:, 1])) / d
            l3 = 1 - l1 - l2
            zh = l1 * A[:, 2] + l2 * B[:, 2] + l3 * C[:, 2]
            hit = ok & (l1 >= 0) & (l2 >= 0) & (l3 >= 0) & (zh > pz)
            pi, ti, zh = pi[hit], ti[hit], zh[hit]
            counts = np.zeros((len(q), nshell), dtype=np.int32)
            np.add.at(counts, (pi, self.shell[ti]), 1)
            inside[s:s + len(q)] = np.any(counts % 2 == 1, axis=1)
            np.minimum.at(above[s:s + len(q)], pi, zh)
        return inside, above

    def inside(self, Q):
        return self._up(Q)[0]

    def roofed(self, Q, reach=COVER):
        Q = np.asarray(Q, dtype=float).reshape(-1, 3)
        return self._up(Q)[1] - Q[:, 2] < reach


class _Group:
    """The same tests against several objects' solids (shells never span
    objects, so inside any one of them is inside)."""

    def __init__(self, solids):
        self.solids = solids

    def inside(self, Q):
        return np.any([s.inside(Q) for s in self.solids], axis=0)

    def roofed(self, Q, reach=COVER):
        return np.any([s.roofed(Q, reach) for s in self.solids], axis=0)


def _box(verts, pad=0.0):
    P = np.array([v[0] for v in verts], dtype=float)
    return P.min(axis=0) - pad, P.max(axis=0) + pad


def _fixture_samples(verts, tris, keys, step=SAMPLE):
    """(keys, points, normals, weights, triangles): points spread over every
    fixture triangle about `step` apart, each carrying its share of the area
    and the index of its triangle."""
    ks, ps, ns, ws, ts = [], [], [], [], []
    for ti, (key, a, b, c) in enumerate(tris):
        if key not in keys:
            continue
        pa, pb, pc = (np.array(verts[i][0], dtype=float) for i in (a, b, c))
        n = np.cross(pb - pa, pc - pa)
        area = np.linalg.norm(n) / 2
        if area < 1e-9:
            continue
        k = int(min(24, max(1, math.ceil(max(np.linalg.norm(pb - pa), np.linalg.norm(pc - pb),
                                                np.linalg.norm(pa - pc)) / step))))
        # centroids of the k*k sub-triangles of a regular subdivision
        pts = []
        for i in range(k):
            for j in range(k - i):
                pts.append(((i + 1 / 3) / k, (j + 1 / 3) / k))
                if i + j < k - 1:
                    pts.append(((i + 2 / 3) / k, (j + 2 / 3) / k))
        uv = np.array(pts)
        P = pa + uv[:, :1] * (pb - pa) + uv[:, 1:] * (pc - pa)
        ks += [key] * len(P)
        ps.append(P)
        ns.append(np.repeat((n / (2 * area))[None], len(P), axis=0))
        ws.append(np.full(len(P), area / len(P)))
        ts.append(np.full(len(P), ti))
    if not ks:
        return [], np.zeros((0, 3)), np.zeros((0, 3)), np.zeros(0), np.zeros(0, dtype=int)
    return ks, np.vstack(ps), np.vstack(ns), np.concatenate(ws), np.concatenate(ts)


def object_lights(name, verts, tris, fixtures, solids=None, colors=None):
    """[(indoor, area, Light)] for one (name, verts, tris) object; `solids`
    (default: the object's own) is what buries a face or roofs a light;
    colors: {key: rgb} (default white)."""
    ks, P, N, W, T = _fixture_samples(verts, tris, fixtures)
    if not ks:
        return []
    solids = solids or _Solids(verts, tris)
    own = solids.solids[0] if isinstance(solids, _Group) else solids
    exposed = ~solids.inside(P + N * 0.03)     # not buried in a slab or wall (of any object near)
    ks, P, N, W, T = np.array(ks)[exposed], P[exposed], N[exposed], W[exposed], T[exposed]
    # one light per fixture (a closed shell: a panel, a strip), never pooled
    # with another, which may be behind a wall; a long strip gets one per
    # SPACING along it
    shell = own.shell[T]
    bins = {}
    for s in np.unique(shell):
        m = shell == s
        lo, hi = P[m].min(axis=0), P[m].max(axis=0)
        axis = int(np.argmax((hi - lo)[:2]))
        length = (hi - lo)[axis]
        nseg = max(1, math.ceil(length / SPACING))
        seg = np.minimum((P[m][:, axis] - lo[axis]) / max(length, 1e-9) * nseg, nseg - 1).astype(int)
        for key, p, n, w, g in zip(ks[m], P[m], N[m], W[m], seg):
            b = bins.setdefault((key, s, g), [np.zeros(3), np.zeros(3), 0.0])
            b[0] += p * w
            b[1] += n * w
            b[2] += w
    merged = [[key, sp / area, sn / max(np.linalg.norm(sn), 1e-9), area]
              for (key, _, _), (sp, sn, area) in bins.items() if area >= MIN_AREA]
    if not merged:
        return []
    # each light OFFSET in front of its fixture, closer if that is inside geometry
    out = []
    cands = np.array([[m[1] + m[2] * off for off in (OFFSET, OFFSET / 2, 0.08)] for m in merged])
    bad = solids.inside(cands.reshape(-1, 3)).reshape(len(merged), 3)
    pos = [c[list(b).index(False)] if not b.all() else None for c, b in zip(cands, bad)]
    keep = [(m, p) for m, p in zip(merged, pos) if p is not None]
    if not keep:
        return []
    roof = solids.roofed(np.array([p for _, p in keep]))
    for r, ((key, cen, n, area), p) in zip(roof, keep):
        intensity, reach = fixtures[key]
        intensity *= QUALITY_SCALE.get(QUALITY, 1.0)
        out.append((bool(r), area, Light(p, (colors or {}).get(key, (1.0, 1.0, 1.0)), intensity, reach)))
    return out


def lights(objects, fixtures, colors=None, cap=MAX_LIGHTS, outdoor=False):
    """Generic lights for a level: objects = [(name, verts, tris)]. Lights
    under a roof first (they are the ones that matter; outdoor=False drops
    the others), then by fixture area."""
    objects = list(objects)
    boxes = [_box(v) if v else None for _, v, _ in objects]
    cache = {}

    def solids(i):
        if i not in cache:
            cache[i] = _Solids(objects[i][1], objects[i][2])
        return cache[i]
    found = []
    for i, (name, verts, tris) in enumerate(objects):
        if not any(t[0] in fixtures for t in tris):
            continue
        # this object's solids and those of every object whose box meets its
        # own (grown by the roof reach upward)
        lo, hi = _box(verts, 0.5)
        hi = hi + np.array([0.0, 0.0, COVER])
        near = [j for j, b in enumerate(boxes) if b is not None and j != i
                and np.all(b[0] <= hi) and np.all(b[1] >= lo)]
        group = _Group([solids(i)] + [solids(j) for j in near])
        # each object's lights take turns, biggest fixture first, so the cap
        # leaves every building its main lights instead of filling up with
        # the long ramps' strips
        own = sorted(object_lights(name, verts, tris, fixtures, group, colors), key=_order)
        found += [(indoor, turn, area, light) for turn, (indoor, area, light) in enumerate(own)]
    if outdoor is False:
        found = [t for t in found if t[0]]
    # rank: indoor first, then each object's turn, then bigger fixtures; a
    # light and its rotated twin (-x, -y) get the same rank, and the cap
    # never splits a rank, so both teams keep the same lights
    def rank(t):
        return (not t[0], t[1]) + _order((t[0], t[2], t[3]))[1:]
    found.sort(key=rank)
    if len(found) > cap:
        cut = rank(found[cap])
        found = [t for t in found[:cap] if rank(t) != cut]
    return [t[3] for t in found]


def _order(t):
    """(indoor, area, light) -> sort key: indoor, bigger, nearer the middle, lower."""
    x, y, z = t[-1].pos
    return (not t[0], -round(t[-2], 2), round(math.hypot(x, y), 0), round(z, 0))


def ass_blocks(lights_, first_object, first_id):
    """(object strings, instance strings) for write_ass: one GENERIC_LIGHT
    object per distinct light definition, one instance per light."""
    defs, objs, insts = {}, [], []
    for k, light in enumerate(lights_):
        body = light.definition()
        if body not in defs:
            defs[body] = first_object + len(objs)
            objs.append(f"\n;OBJECT {defs[body]}\n\"GENERIC_LIGHT\"\n\"\"\n\"\"\n" + body)
        x, y, z = light.pos
        insts.append((defs[body], f"light_{k}", first_id + k,
                      "0.0000000000\t0.0000000000\t0.0000000000\t1.0000000000\n"
                      f"{x * 100:.4f}\t{y * 100:.4f}\t{z * 100:.4f}\n1.0000000000\n"))
    return objs, insts


def summary(lights_):
    if not lights_:
        return "no lights"
    I = [l.intensity for l in lights_]
    return f"{len(lights_)} lights (intensity {min(I):.1f}..{max(I):.1f})"


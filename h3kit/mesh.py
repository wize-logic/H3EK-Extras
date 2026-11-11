"""A small toolkit of closed, watertight meshes for level geometry.

Every shape here is a closed shell: a prism between two rings of points (a box,
a rotated box, a ramp, an octagon...) or a loft through a run of rings (a
tunnel roof, a bridge deck). Shells are oriented by their signed volume, so
triangles always wind counterclockwise seen from outside, whatever mirroring
or rotation produced the points.

A Part collects shells into one instanced-geometry object. Shells in a Part
may overlap each other (a lintel pushed into the walls beside it), but never
just touch: tool welds coincident vertices, and two shells sharing a corner or
an edge would become one non-manifold mesh. Pieces that meet are therefore
always pushed a little way into each other (see OVERLAP).
"""

import math

import numpy as np

UV_SCALE = 1.0       # UVs in world units; ass.write scales them per material
OVERLAP = 0.05       # how far meeting pieces push into each other


class Frame:
    """Local (a, b, z) coordinates of a building -> world (x, y, z).

    a and b are unit vectors in the world's xy plane; they need not be
    right-handed, so a mirrored frame builds the blue twin of a red building.
    s scales local units (a, b and z alike) about the origin."""

    def __init__(self, ox, oy, oz, a=(1.0, 0.0), b=(0.0, 1.0), s=1.0):
        self.o = (ox, oy, oz)
        self.a, self.b = a, b
        self.s = s

    def __call__(self, a, b, z=0.0):
        ox, oy, oz = self.o
        a, b, z = a * self.s, b * self.s, z * self.s
        return (ox + a * self.a[0] + b * self.b[0], oy + a * self.a[1] + b * self.b[1], oz + z)

    def rotated(self, deg, da=0.0, db=0.0, dz=0.0):
        """A frame turned by deg (counterclockwise in local terms) about a
        new origin at local (da, db, dz)."""
        c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
        x, y, z = self(da, db, dz)
        a = (c * self.a[0] + s * self.b[0], c * self.a[1] + s * self.b[1])
        b = (-s * self.a[0] + c * self.b[0], -s * self.a[1] + c * self.b[1])
        return Frame(x, y, z, a, b, self.s)


class Part:
    """One instanced-geometry object: a list of closed shells."""

    def __init__(self, name):
        self.name = name
        self.verts, self.tris = [], []
        self.faces = []     # (shell number, polygon) for check()
        self.shells = 0
        self.vrange = []    # per shell: (first vertex, end), for move()

    def __len__(self):
        return len(self.tris)

    def result(self):
        return self.name, self.verts, self.tris

    def move(self, shell, d):
        """Shift one shell by the vector d."""
        v0, v1 = self.vrange[shell]
        for i in range(v0, v1):
            (x, y, z), n, uv = self.verts[i]
            self.verts[i] = ((x + d[0], y + d[1], z + d[2]), n, uv)
        self.faces = [(s, [p + d for p in pts]) if s == shell else (s, pts) for s, pts in self.faces]

    # -- shells -----------------------------------------------------------------

    def shell(self, faces):
        """faces: [(key, [p0, p1, ...]), ...] polygons (convex, any winding
        consistent across the shell) that together close a volume."""
        v0 = len(self.verts)
        vol = 0.0
        for _, poly in faces:
            p0 = np.array(poly[0])
            for k in range(1, len(poly) - 1):
                vol += np.dot(p0, np.cross(np.array(poly[k]), np.array(poly[k + 1])))
        flip = vol < 0
        for key, poly in faces:
            pts = [np.array(p, dtype=float) for p in (poly[::-1] if flip else poly)]
            self._polygon(key, pts)
            self.faces.append((self.shells, pts))
        self.shells += 1
        self.vrange.append((v0, len(self.verts)))

    def _polygon(self, key, pts):
        """A convex face as a fan; each face gets its own vertices (flat
        shading), at exactly the positions its neighbours use."""
        n = np.zeros(3)
        for k in range(1, len(pts) - 1):
            n += np.cross(pts[k] - pts[0], pts[k + 1] - pts[0])
        length = np.linalg.norm(n)
        if length < 1e-9:
            return
        n /= length
        # texture: project onto the face's two most spread axes, from its corner
        axis = int(np.argmax(np.abs(n)))
        u_ax, v_ax = [(1, 2), (0, 2), (0, 1)][axis]
        u0 = min(p[u_ax] for p in pts)
        v0 = min(p[v_ax] for p in pts)
        base = len(self.verts)
        for p in pts:
            self.verts.append(((float(p[0]), float(p[1]), float(p[2])), tuple(float(c) for c in n),
                               ((p[u_ax] - u0) * UV_SCALE, (p[v_ax] - v0) * UV_SCALE)))
        for k in range(1, len(pts) - 1):
            # skip slivers (a ramp's low edge may meet the ground exactly)
            if np.linalg.norm(np.cross(pts[k] - pts[0], pts[k + 1] - pts[0])) > 1e-6:
                self.tris.append((key, base, base + k, base + k + 1))

    def prism(self, bottom, top, key, top_key=None, side_key=None, bottom_key=None):
        """A solid between two rings of world points, matched point for point
        (bottom[i] below top[i]). Rings must be convex."""
        n = len(bottom)
        faces = [(bottom_key or key, list(bottom[::-1])), (top_key or key, list(top))]
        for i in range(n):
            j = (i + 1) % n
            faces.append((side_key or key, [bottom[i], bottom[j], top[j], top[i]]))
        self.shell(faces)

    def loft(self, rings, key, cap_key=None):
        """A solid through a run of rings (each convex, same point count),
        capped at both ends: a tunnel roof or a bridge deck. Quads between
        rings are split into triangles so they need not be planar."""
        n = len(rings[0])
        faces = [(cap_key or key, list(rings[0][::-1])), (cap_key or key, list(rings[-1]))]
        for r0, r1 in zip(rings, rings[1:]):
            for i in range(n):
                j = (i + 1) % n
                faces.append((key, [r0[i], r0[j], r1[j]]))
                faces.append((key, [r0[i], r1[j], r1[i]]))
        self.shell(faces)

    # -- building blocks in a Frame ------------------------------------------------

    def box(self, f, a0, a1, b0, b1, z0, z1, key, top_key=None):
        """An axis-aligned box in frame f's local coordinates."""
        ring = [(a0, b0), (a1, b0), (a1, b1), (a0, b1)]
        self.prism([f(a, b, z0) for a, b in ring], [f(a, b, z1) for a, b in ring], key, top_key)

    def ramp(self, f, a0, a1, b0, b1, z_base, z_low, z_high, key, top_key=None):
        """A solid ramp rising along a from z_low (at a0) to z_high (at a1),
        standing on z_base."""
        ring = [(a0, b0), (a1, b0), (a1, b1), (a0, b1)]
        tops = [z_low, z_high, z_high, z_low]
        self.prism([f(a, b, z_base) for a, b in ring],
                   [f(a, b, z) for (a, b), z in zip(ring, tops)], key, top_key)

    def ramp_b(self, f, a0, a1, b0, b1, z_base, z_low, z_high, key, top_key=None):
        """As ramp(), rising along b instead (from b0 to b1)."""
        ring = [(a0, b0), (a1, b0), (a1, b1), (a0, b1)]
        tops = [z_low, z_low, z_high, z_high]
        self.prism([f(a, b, z_base) for a, b in ring],
                   [f(a, b, z) for (a, b), z in zip(ring, tops)], key, top_key)

    def ngon(self, f, ca, cb, r, z0, z1, key, sides=8, top_key=None, phase=None):
        """A regular polygonal column (octagon by default)."""
        phase = math.pi / sides if phase is None else phase
        ring = [(ca + r * math.cos(phase + 2 * math.pi * k / sides),
                 cb + r * math.sin(phase + 2 * math.pi * k / sides)) for k in range(sides)]
        self.prism([f(a, b, z0) for a, b in ring], [f(a, b, z1) for a, b in ring], key, top_key)

    def arc_wall(self, f, ca, cb, r, thick, deg0, deg1, z0, z1, key, top_key=None):
        """A short straight wall chord-wise between two angles on a circle."""
        p, q = math.radians(deg0), math.radians(deg1)
        ri, ro = r - thick / 2, r + thick / 2
        ring = [(ca + ri * math.cos(p), cb + ri * math.sin(p)), (ca + ro * math.cos(p), cb + ro * math.sin(p)),
                (ca + ro * math.cos(q), cb + ro * math.sin(q)), (ca + ri * math.cos(q), cb + ri * math.sin(q))]
        self.prism([f(a, b, z0) for a, b in ring], [f(a, b, z1) for a, b in ring], key, top_key)


def polyline_stations(points, spacing):
    """Points every ~spacing along a polyline (its corners included), each
    with a mitred sideways unit vector and a mitre scale."""
    pts = [np.array(p, dtype=float) for p in points]
    out = []
    for k in range(len(pts) - 1):
        p, q = pts[k], pts[k + 1]
        n = max(1, int(math.ceil(np.linalg.norm(q - p) / spacing)))
        for i in range(n + (1 if k == len(pts) - 2 else 0)):
            out.append((p + (q - p) * i / n, k, i == 0 and k > 0))
    stations = []
    for c, k, corner in out:
        d = pts[k + 1] - pts[k]
        d /= np.linalg.norm(d)
        side = np.array([-d[1], d[0]])
        scale = 1.0
        if corner:
            d0 = pts[k] - pts[k - 1]
            d0 /= np.linalg.norm(d0)
            s0 = np.array([-d0[1], d0[0]])
            m = s0 + side
            m /= np.linalg.norm(m)
            scale = 1.0 / max(0.5, float(np.dot(m, side)))
            side = m
        stations.append((c, side, scale, d))
    return stations


def _plane(pts):
    n = np.zeros(3)
    for k in range(1, len(pts) - 1):
        n += np.cross(pts[k] - pts[0], pts[k + 1] - pts[0])
    length = np.linalg.norm(n)
    if length < 1e-9:
        return None, None
    n /= length
    # one sign per plane, so faces back to back land in the same bucket
    for c in n:
        if abs(c) > 1e-6:
            if c < 0:
                n = -n
            break
    return n, float(np.dot(n, pts[0]))


def _overlap_2d(p, q, eps=1e-3):
    """Do two convex polygons (2D) overlap by more than eps (separating axes)?"""
    for poly in (p, q):
        for k in range(len(poly)):
            e = poly[(k + 1) % len(poly)] - poly[k]
            axis = np.array([-e[1], e[0]])
            length = np.linalg.norm(axis)
            if length < 1e-9:
                continue
            axis /= length
            a, b = [x @ axis for x in p], [x @ axis for x in q]
            if min(max(a), max(b)) - max(min(a), min(b)) < eps:
                return False
    return True


def check(part):
    """Faces of different shells that lie in one plane and overlap: tool
    reports them as overlapping surfaces (or, back to back, as ambiguous
    connections). Returns [(shell, shell, face centre), ...]."""
    buckets = {}
    for shell, pts in part.faces:
        n, d = _plane(pts)
        if n is None:
            continue
        key = (tuple(np.round(n, 3)), round(d, 2))
        buckets.setdefault(key, []).append((shell, pts, n))
    bad = []
    for faces in buckets.values():
        for i in range(len(faces)):
            for j in range(i + 1, len(faces)):
                (s0, p0, n), (s1, p1, _) = faces[i], faces[j]
                if s0 == s1:
                    continue
                u = np.cross(n, [0.0, 0.0, 1.0] if abs(n[2]) < 0.9 else [1.0, 0.0, 0.0])
                u /= np.linalg.norm(u)
                v = np.cross(n, u)
                a = [np.array([x @ u, x @ v]) for x in p0]
                b = [np.array([x @ u, x @ v]) for x in p1]
                if _overlap_2d(a, b):
                    bad.append((s0, s1, tuple(np.round(sum(p0) / len(p0), 2))))
    return bad

"""Writing JMS 8213 files (Halo 3's model source format) for `tool render`,
`tool collision` and `tool physics`.

Layout (the Blender toolset's 8213 writer, and tool's own reader): version,
nodes (name, parent, rotation i j k w, translation), materials (name, then
"(slot) [lod] [permutation] [region]"), markers, instance xref paths, instance
markers, vertices (position, normal, node influences, UVs, colour), triangles
(material, three vertex indices), then spheres, boxes, capsules, convex
shapes, ragdolls, hinges, car wheels, point-to-points, prismatics, bounding
spheres and skylights.

A static prop has one node, "frame root", at the origin (tool wants a space after a "frame" prefix). Positions are in JMS
units: 100 to a world unit (as in the .ASS).

    m = Model()
    m.material("shader_name")                    -> index
    m.triangle(material, (p, n, uv) x3)          a triangle in world units
    m.box(name, material, centre, size, yaw=0)   a physics box (world units)
    m.write(path)
"""

import math

SCALE = 100.0           # JMS units per world unit


def _v3(p):
    return f"{p[0] * SCALE:.6f}\t{p[1] * SCALE:.6f}\t{p[2] * SCALE:.6f}"


class Model:
    def __init__(self, node="frame root"):
        self.node = node
        self.materials = []         # (name, definition)
        self.vertices = []          # (position, normal, uv)
        self.triangles = []         # (material, a, b, c)
        self.boxes = []             # (name, material, rotation quat, centre, (w, l, h))

    def material(self, name, definition="(1) default"):
        for k, (n, _) in enumerate(self.materials):
            if n == name:
                return k
        self.materials.append((name, definition))
        return len(self.materials) - 1

    def vertex(self, position, normal, uv):
        self.vertices.append((tuple(position), tuple(normal), tuple(uv)))
        return len(self.vertices) - 1

    def triangle(self, material, corners):
        """corners: three (position, normal, uv), wound counterclockwise seen from outside."""
        idx = [self.vertex(*c) for c in corners]
        self.triangles.append((material, *idx))

    def closed_box(self, material, lo, hi):
        """A closed axis-aligned box of triangles, faces out (collision geometry)."""
        (x0, y0, z0), (x1, y1, z1) = lo, hi
        self.closed_hull(material, [(x, y, z) for z in (z0, z1) for y in (y0, y1) for x in (x0, x1)])

    def closed_hull(self, material, c):
        """A closed box of any orientation (collision geometry): its 8 corners in closed_box's order
        (x fastest, then y, then z, of a right-handed frame), faces out."""
        faces = (0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)
        for quad in faces:
            p = [tuple(c[k]) for k in quad]
            e1 = [p[1][i] - p[0][i] for i in range(3)]
            e2 = [p[2][i] - p[0][i] for i in range(3)]
            n = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
            ln = math.sqrt(sum(v * v for v in n)) or 1.0
            n = tuple(v / ln for v in n)
            for t in ((0, 1, 2), (0, 2, 3)):
                self.triangle(material, [(p[k], n, (0.0, 0.0)) for k in t])

    def box(self, name, material, centre, size, yaw=0.0, quat=None):
        """A physics box primitive: centre and (x, y, z) size in world units, turned yaw degrees about z
        (or by quat (i, j, k, w), a rotation from the box's own axes to the model's)."""
        if quat is None:
            h = math.radians(yaw) / 2
            quat = (0.0, 0.0, math.sin(h), math.cos(h))
        self.boxes.append((name, material, tuple(quat), tuple(centre), tuple(size)))

    def write(self, path):
        L = ["8213", "1", self.node, "-1", "0.0000000000\t0.0000000000\t0.0000000000\t1.0000000000",
             "0.000000\t0.000000\t0.000000"]
        L.append(str(len(self.materials)))
        for name, definition in self.materials:
            L += [name, definition]
        L += ["0", "0", "0"]                            # markers, xref paths, xref markers
        L.append(str(len(self.vertices)))
        for p, n, (u, v) in self.vertices:
            L += [_v3(p), f"{n[0]:.6f}\t{n[1]:.6f}\t{n[2]:.6f}", "1", "0", "1.000000", "1",
                  f"{u:.6f}\t{v:.6f}", "0.000000\t0.000000\t0.000000"]
        L.append(str(len(self.triangles)))
        for m, a, b, c in self.triangles:
            L += [str(m), f"{a}\t{b}\t{c}"]
        L.append("0")                                   # spheres
        L.append(str(len(self.boxes)))
        for name, m, q, centre, (w, l, h) in self.boxes:
            L += [name, "0", str(m), "%0.10f\t%0.10f\t%0.10f\t%0.10f" % q, _v3(centre),
                  f"{w * SCALE:.6f}", f"{l * SCALE:.6f}", f"{h * SCALE:.6f}"]
        L += ["0"] * 9                                  # capsules .. skylights
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="\r\n") as f:
            f.write("\n".join(L) + "\n")
        return len(self.vertices), len(self.triangles)

"""A level's structure design: soft ceilings and water physics volumes, an .ASS
compiled by `tool structure-design` into <level>\\<name>_design.structure_design
and referenced from the scenario's structure bsp (and every resource copy's
structure reference).

What tool reads in a design .ASS (Microsoft's H3 guides; Valhalla's design tag):
  * a material named "+soft_ceiling:<name>" (or "+soft_kill:<name>",
    "+slip_surface:<name>") makes its triangles one soft surface of that name;
    any triangle soup, the faces' normals pointing into the play area, every
    open edge buried in the level or meeting another soft surface's edge;
  * an object instance named "~<name>" is a water physics volume: a closed
    convex shape whose top lines up with the water surface drawn in the level
    (the engine keeps it as planes: Valhalla's are six-plane boxes).

    d = Design()
    d.soft_box("bounds", x0, x1, y0, y1, z0, z1, cap=True)   walls (and a cap) facing in
    d.water("fountain", prism_points, top, bottom)           a convex water volume
    d.write(path)                                            the .ASS

1 world unit is about 10 feet; .ASS positions are in hundredths of a unit.
"""

import math

import numpy as np

from . import ass

# a material for the water volumes' faces: tool takes the volume from the instance's name
WATER_MATERIAL = "water_volume"


def _quad(p, normal):
    """Two triangles of a quad (4 corners), wound counterclockwise seen from where `normal` points."""
    a, b, c = (np.array(p[k], float) for k in range(3))
    flip = np.dot(np.cross(b - a, c - a), normal) < 0
    return [(0, 2, 1), (0, 3, 2)] if flip else [(0, 1, 2), (0, 2, 3)]


class Design:
    def __init__(self):
        self.meshes, self.instances, self.materials = [], [], []

    def _material(self, name):
        if name not in self.materials:
            self.materials.append(name)
        return self.materials.index(name)

    def _add(self, name, faces, material):
        """faces: [(corner points, outward normal)] -> one mesh, one instance."""
        m = self._material(material)
        pos, nrm, uv, tri = [], [], [], []
        for pts, n in faces:
            base = len(pos)
            for x, y, z in pts:
                pos.append((x, y, z))
                nrm.append(n)
                uv.append((x / 8.0, y / 8.0))
            if len(pts) == 4:
                order = _quad(pts, n)
            else:   # a convex polygon: a fan, wound to face n
                order = [(0, k, k + 1) for k in range(1, len(pts) - 1)]
                a, b, c = (np.array(pts[k], float) for k in order[0])
                if np.dot(np.cross(b - a, c - a), n) < 0:
                    order = [(t[0], t[2], t[1]) for t in order]
            tri += [tuple(base + k for k in t) for t in order]
        self.meshes.append(ass.Mesh(np.array(pos, float), np.array(nrm, float), np.array(uv, float),
                                    np.array(tri, int), np.full(len(tri), m, int)))
        self.instances.append(ass.Instance(len(self.meshes) - 1, name, np.eye(3), (0.0, 0.0, 0.0)))

    def soft_box(self, name, x0, x1, y0, y1, z0, z1, cap=True, kind="soft_ceiling"):
        """Four walls round x0..x1, y0..y1 from z0 (buried under the ground) to z1,
        and with `cap` a lid at z1: every face's normal points into the box."""
        walls = [([(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)], (0, 1, 0)),
                 ([(x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1)], (0, -1, 0)),
                 ([(x0, y0, z0), (x0, y1, z0), (x0, y1, z1), (x0, y0, z1)], (1, 0, 0)),
                 ([(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)], (-1, 0, 0))]
        if cap:
            walls.append(([(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)], (0, 0, -1)))
        self._add(f"soft_{name}", walls, f"+{kind}:{name}")

    def water(self, name, outline, top, bottom):
        """A water physics volume: the convex polygon `outline` [(x, y)...] from
        `bottom` up to the water's surface at `top`, closed, faces pointing out."""
        pts = [(float(x), float(y)) for x, y in outline]
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        faces = [([(x, y, top) for x, y in pts], (0, 0, 1)),
                 ([(x, y, bottom) for x, y in reversed(pts)], (0, 0, -1))]
        for k in range(len(pts)):
            (ax, ay), (bx, by) = pts[k], pts[(k + 1) % len(pts)]
            mx, my = (ax + bx) / 2 - cx, (ay + by) / 2 - cy
            n = math.hypot(mx, my) or 1.0
            faces.append(([(ax, ay, bottom), (bx, by, bottom), (bx, by, top), (ax, ay, top)], (mx / n, my / n, 0)))
        self._add(f"~{name}", faces, WATER_MATERIAL)

    def write(self, path, header=("h3kit", "H3KIT")):
        return ass.write_instanced(path, self.meshes, self.instances, [(m, []) for m in self.materials],
                                   header=header)


def circle(cx, cy, r, sides=16):
    """A convex polygon round (cx, cy): its corners on a circle of radius r."""
    return [(cx + r * math.cos(2 * math.pi * k / sides), cy + r * math.sin(2 * math.pi * k / sides))
            for k in range(sides)]

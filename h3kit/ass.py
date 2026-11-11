"""Writing a level as an .ASS file for `tool structure`.

A level is a list of objects (name, vertices, triangles): vertices are
((x, y, z), normal, (u, v)) in world units with UVs in world units too,
triangles are (material key, a, b, c). An object name starting with "%" is
instanced geometry ("%!" lit per pixel, "%?" per vertex); the rest is the
structure itself, which must seal the level (sky_box()).

Materials are named by a look: any object (a module will do) with
  SHADERS    key -> shader name ("<collection prefix> <shader>", a name in the
             level's own shaders folder, or "+sky")
  UV_REPEAT  key -> world units one UV unit covers for that shader
  GROUND_UV  repeats at least this large are left unshifted (see scale_uvs)
  LIGHTING   key -> .ASS emissive strings (look.emissive) for light materials
  FIXTURES   key -> (intensity, reach) of the lights put in front of fixtures

    ass.write(path, objects, look, lights)   -> (objects, vertices, triangles, per material)
    ass.ground_tiles(xs, H, normals, material)   a heightfield as closed instanced tiles
                                             (material edges cut smooth along a field)
    ass.sky_box(half, floor, ceiling)        the sealed +sky box
    ass.write_instanced(path, meshes, instances, materials)   shared meshes, placed with transforms

1 world unit is about 10 feet; .ASS positions are in hundredths of a unit.
"""

import math
from dataclasses import dataclass

import numpy as np

from . import lights as L

IDENTITY = ("0.0000000000\t0.0000000000\t0.0000000000\t1.0000000000\n"
            "0.0000000000\t0.0000000000\t0.0000000000\n1.0000000000\n")


def scale_uvs(verts, tris, look):
    """World-unit UVs to each material's repeat (look.UV_REPEAT). A vertex
    shared by two materials is split. Small repeats are shifted by a whole
    number of repeats toward 0 (large UVs warn), which keeps seams matching."""
    out_v, out_t, seen, offset = [], [], {}, {}
    for key, *corners in tris:
        r = look.UV_REPEAT[key]
        if key not in offset:
            us = [verts[c][2] for _, *cs in tris if _ == key for c in cs]
            offset[key] = 0.0 if r >= look.GROUND_UV else tuple(
                math.floor(min(q[a] for q in us) / r) * r for a in (0, 1))
        new = []
        for c in corners:
            if (c, key) not in seen:
                pos, n, (tu, tv) = verts[c]
                o = offset[key] or (0.0, 0.0)
                seen[c, key] = len(out_v)
                out_v.append((pos, n, ((tu - o[0]) / r, (tv - o[1]) / r)))
            new.append(seen[c, key])
        out_t.append((key, *new))
    return out_v, out_t


def fixture_lights(objects, look, cap=L.MAX_LIGHTS):
    """One generic light per light fixture in `objects` (lights.lights with the look's
    FIXTURES and the colours of its emissive strings)."""
    return L.lights(list(objects), look.FIXTURES, L.colors_of(look.LIGHTING), cap=cap)


def write(path, objects, look, lights=(), header=("h3kit", "H3KIT"), first_id=8470):
    """Write the level: `objects` (the structure and the instanced geometry) and
    generic `lights` (lights.Light). Instances get unique ids from first_id.
    Returns (objects, vertices, triangles, triangles per material)."""
    objects = list(objects)
    lights = list(lights or [])
    light_objs, light_insts = L.ass_blocks(lights, len(objects), first_id + len(objects))
    keys = sorted({t[0] for _, _, tris in objects for t in tris})
    index = {k: n for n, k in enumerate(keys)}
    user, machine = header

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="\r\n") as f:
        w = f.write
        w(f";### HEADER ###\n7\n\"MAX\"\n\"7.0\"\n\"{user}\"\n\"{machine}\"\n")
        w(f"\n;### MATERIALS ###\n{len(keys)}\n")
        for k, key in enumerate(keys):
            # a look may leave its emissive strings out of the bake (BAKE_EMISSIVE = False)
            lighting = look.LIGHTING.get(key, []) if getattr(look, "BAKE_EMISSIVE", True) else []
            w(f"\n;MATERIAL {k}\n\"{look.SHADERS[key]}\"\n\"\"\n{len(lighting)}\n")
            for line in lighting:
                w(f"\"{line}\"\n")
        w(f"\n;### OBJECTS ###\n{len(objects) + len(light_objs)}\n")
        for k, (_, verts, tris) in enumerate(objects):
            verts, tris = scale_uvs(verts, tris, look)
            w(f"\n;OBJECT {k}\n\"MESH\"\n\"\"\n\"\"\n{len(verts)}\n")
            for (px, py, pz), (nx, ny, nz), (tu, tv) in verts:
                w(f"{px * 100:.4f}\t{py * 100:.4f}\t{pz * 100:.4f}\n"
                  f"{nx:.6f}\t{ny:.6f}\t{nz:.6f}\n"
                  "0.000000\t0.000000\t0.000000\n"
                  "0\n1\n"
                  f"{tu:.6f}\t{tv:.6f}\t0.000000\n")
            w(f"{len(tris)}\n")
            for key, a, b, c in tris:
                w(f"{index[key]}\t\t{a}\t{b}\t{c}\n")
        for text in light_objs:     # GENERIC_LIGHT objects (lights.py)
            w(text)
        w(f"\n;### INSTANCES ###\n{len(objects) + len(light_insts) + 1}\n")
        w("\n;INSTANCE 0\n-1\n\"Scene Root\"\n-1\n-1\n0\n" + IDENTITY + IDENTITY)
        for k, (name, _, _) in enumerate(objects):
            w(f"\n;INSTANCE {k + 1}\n{k}\n\"{name}\"\n{first_id + k}\n0\n0\n" + IDENTITY + IDENTITY)
        for k, (obj, name, uid, transform) in enumerate(light_insts):
            w(f"\n;INSTANCE {len(objects) + k + 1}\n{obj}\n\"{name}\"\n{uid}\n0\n0\n" + transform + IDENTITY)
    counts = {}
    for _, _, tris in objects:
        for t in tris:
            counts[t[0]] = counts.get(t[0], 0) + 1
    return len(objects), sum(len(v) for _, v, _ in objects), sum(len(t) for _, _, t in objects), counts


# -- shared meshes placed by transforms ----------------------------------------------

@dataclass
class Mesh:
    """An .ASS object: positions, normals and UVs (N x 3, N x 3, N x 2, world
    units, UVs as the .ASS takes them: v up) and triangles (M x 3) with a
    material index each (M)."""
    positions: np.ndarray
    normals: np.ndarray
    uvs: np.ndarray
    triangles: np.ndarray
    materials: np.ndarray


@dataclass
class Instance:
    """An .ASS instance of a Mesh: name (a leading % makes it instanced
    geometry, see the module doc), a rotation matrix whose rows are the
    local axes in the world (forward, left, up), a translation in world units
    and a uniform scale."""
    mesh: int
    name: str
    rotation: np.ndarray
    translation: tuple
    scale: float = 1.0


def quaternion(m):
    """(i, j, k, w) of a rotation matrix with the local axes as rows."""
    r = np.asarray(m, float).T          # columns: the local axes
    t = np.trace(r)
    if t > 0:
        s = math.sqrt(t + 1.0) * 2
        q = ((r[2, 1] - r[1, 2]) / s, (r[0, 2] - r[2, 0]) / s, (r[1, 0] - r[0, 1]) / s, 0.25 * s)
    elif r[0, 0] > r[1, 1] and r[0, 0] > r[2, 2]:
        s = math.sqrt(1.0 + r[0, 0] - r[1, 1] - r[2, 2]) * 2
        q = (0.25 * s, (r[0, 1] + r[1, 0]) / s, (r[0, 2] + r[2, 0]) / s, (r[2, 1] - r[1, 2]) / s)
    elif r[1, 1] > r[2, 2]:
        s = math.sqrt(1.0 + r[1, 1] - r[0, 0] - r[2, 2]) * 2
        q = ((r[0, 1] + r[1, 0]) / s, 0.25 * s, (r[1, 2] + r[2, 1]) / s, (r[0, 2] - r[2, 0]) / s)
    else:
        s = math.sqrt(1.0 + r[2, 2] - r[0, 0] - r[1, 1]) * 2
        q = ((r[0, 2] + r[2, 0]) / s, (r[1, 2] + r[2, 1]) / s, 0.25 * s, (r[1, 0] - r[0, 1]) / s)
    q = np.array(q)
    return q / np.linalg.norm(q)


# the .ASS takes quaternion() as it is: checked on a compiled test level, whose instances'
# forward/left/up came out as the rows given (the conjugate gave their transpose)
QUAT_SIGN = 1.0


def write_instanced(path, meshes, instances, materials, lights=(), header=("h3kit", "H3KIT"), first_id=8470):
    """Write a level of shared meshes placed by instances. materials: [(shader
    name with its symbols, [emissive strings])]. Returns (meshes, instances,
    triangles placed)."""
    lights = list(lights or [])
    light_objs, light_insts = L.ass_blocks(lights, len(meshes), first_id + len(instances))
    user, machine = header
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="\r\n") as f:
        w = f.write
        w(f";### HEADER ###\n7\n\"MAX\"\n\"7.0\"\n\"{user}\"\n\"{machine}\"\n")
        w(f"\n;### MATERIALS ###\n{len(materials)}\n")
        for k, (name, lighting) in enumerate(materials):
            w(f"\n;MATERIAL {k}\n\"{name}\"\n\"\"\n{len(lighting)}\n")
            for line in lighting:
                w(f"\"{line}\"\n")
        w(f"\n;### OBJECTS ###\n{len(meshes) + len(light_objs)}\n")
        for k, m in enumerate(meshes):
            w(f"\n;OBJECT {k}\n\"MESH\"\n\"\"\n\"\"\n{len(m.positions)}\n")
            rows = [f"{px * 100:.4f}\t{py * 100:.4f}\t{pz * 100:.4f}\n{nx:.6f}\t{ny:.6f}\t{nz:.6f}\n"
                    "0.000000\t0.000000\t0.000000\n0\n1\n"
                    f"{tu:.6f}\t{tv:.6f}\t0.000000\n"
                    for (px, py, pz), (nx, ny, nz), (tu, tv) in zip(m.positions.tolist(), m.normals.tolist(),
                                                                     m.uvs.tolist())]
            w("".join(rows))
            w(f"{len(m.triangles)}\n")
            w("".join(f"{mat}\t\t{a}\t{b}\t{c}\n"
                      for mat, (a, b, c) in zip(m.materials.tolist(), m.triangles.tolist())))
        for text in light_objs:
            w(text)
        w(f"\n;### INSTANCES ###\n{len(instances) + len(light_insts) + 1}\n")
        w("\n;INSTANCE 0\n-1\n\"Scene Root\"\n-1\n-1\n0\n" + IDENTITY + IDENTITY)
        for k, inst in enumerate(instances):
            qi, qj, qk, qw = quaternion(inst.rotation)
            s = QUAT_SIGN
            x, y, z = inst.translation
            w(f"\n;INSTANCE {k + 1}\n{inst.mesh}\n\"{inst.name}\"\n{first_id + k}\n0\n0\n"
              f"{s * qi:.10f}\t{s * qj:.10f}\t{s * qk:.10f}\t{qw:.10f}\n"
              f"{x * 100:.4f}\t{y * 100:.4f}\t{z * 100:.4f}\n{inst.scale:.10f}\n" + IDENTITY)
        for k, (obj, name, uid, transform) in enumerate(light_insts):
            w(f"\n;INSTANCE {len(instances) + k + 1}\n{obj}\n\"{name}\"\n{uid}\n0\n0\n" + transform + IDENTITY)
    placed = sum(len(meshes[i.mesh].triangles) for i in instances)
    return len(meshes), len(instances), placed


# -- ground from a heightfield ------------------------------------------------------

def normals_of(H, step):
    """Unit normals of a heightfield H sampled `step` apart."""
    gx, gy = np.gradient(H, step)
    normals = np.dstack([-gx, -gy, np.ones_like(H)])
    return normals / np.linalg.norm(normals, axis=2, keepdims=True)


def close_slab(verts, tris, xs, H, i0, i1, j0, j1, side_key, uv_scale=1.0, cuts=None):
    """Close a ground tile into a solid: sides down to a flat bottom. An open
    sheet gives open edges and leaky collision. cuts: {(grid point a, grid point
    b): (x, y, z)} for rim edges the top surface splits (ground_tiles' `field`),
    so the sides meet the top vertex to vertex."""
    cuts = cuts or {}
    bottom = float(H[i0:i1 + 1, j0:j1 + 1].min()) - 4.0
    # the tile's rim, counterclockwise seen from above
    rim = ([(i, j0) for i in range(i0, i1)] + [(i1, j) for j in range(j0, j1)] +
           [(i, j1) for i in range(i1, i0, -1)] + [(i0, j) for j in range(j1, j0, -1)])
    ring = []       # the rim's points (x, y, z), with any cut points between grid points
    for k in range(len(rim)):
        (ia, ja), (ib, jb) = rim[k], rim[(k + 1) % len(rim)]
        ring.append((xs[ia], xs[ja], H[ia, ja]))
        if ((ia, ja), (ib, jb)) in cuts:
            ring.append(cuts[(ia, ja), (ib, jb)])
        elif ((ib, jb), (ia, ja)) in cuts:
            ring.append(cuts[(ib, jb), (ia, ja)])
    m = len(ring)
    for k in range(m):
        (ax, ay, az), (bx, by, bz) = ring[k], ring[(k + 1) % m]
        out = np.array([by - ay, -(bx - ax), 0.0])
        out = tuple(out / np.linalg.norm(out))
        base = len(verts)
        for x, y, z in ((ax, ay, az), (bx, by, bz), (bx, by, bottom), (ax, ay, bottom)):
            verts.append(((x, y, z), out, ((x + y) * uv_scale, z * uv_scale)))
        # seen from outside, top a -> bottom a -> bottom b runs counterclockwise
        tris.append((side_key, base, base + 3, base + 2))
        tris.append((side_key, base, base + 2, base + 1))
    # the bottom as a fan through every rim point, so its edges meet the sides'
    centre = len(verts)
    verts.append((((xs[i0] + xs[i1]) / 2, (xs[j0] + xs[j1]) / 2, bottom), (0.0, 0.0, -1.0), (0.0, 0.0)))
    for k in range(m):
        (ax, ay, _), (bx, by, _) = ring[k], ring[(k + 1) % m]
        base = len(verts)
        for x, y in ((ax, ay), (bx, by)):
            verts.append(((x, y, bottom), (0.0, 0.0, -1.0), (x * uv_scale, y * uv_scale)))
        tris.append((side_key, centre, base + 1, base))  # facing down


CUT_MIN = 0.15   # a field cut keeps this fraction of an edge's length from either end (no slivers)


def ground_tiles(xs, H, normals, material, cliff="cliff", tile=24, uv_scale=1.0, prefix="%?ground",
                 field=None, keys=None):
    """A heightfield H[i, j] at (xs[i], xs[j]) as tile x tile-cell objects: tool
    welds each object's vertices pairwise, so one big mesh takes far too long
    to import. Each cell is the triangles (i,j)-(i+1,j)-(i+1,j+1) and
    (i,j)-(i+1,j+1)-(i,j+1) (h3kit.terrain reads the same). material(points)
    names each triangle's material; `cliff` triangles take a side projection,
    and closes each tile's slab. UVs are world units (u = x, v = y), so tiled
    ground shaders run on across tiles.

    Smooth material edges: with `field` (an array like H, a value per grid
    point) and keys = (high key, low key), a triangle whose material() is None
    is cut along the field's zero line (linear on the facet) into keys[0] where
    the field is >= 0 and keys[1] below. The pieces lie on the facet, so the
    ground's shape is unchanged; the edge between two materials runs as a
    smooth line across the cells instead of a sawtooth of whole triangles.
    Triangles with a fixed material next to a cut are split at the cut points
    too (a fan from their centre), and so are the tiles' sides, so every tile
    stays closed vertex to vertex."""
    n = len(xs)
    for i0 in range(0, n - 1, tile):
        for j0 in range(0, n - 1, tile):
            i1, j1 = min(i0 + tile, n - 1), min(j0 + tile, n - 1)
            w = j1 - j0 + 1
            verts, tris = [], []
            for i in range(i0, i1 + 1):
                for j in range(j0, j1 + 1):
                    x, y = xs[i], xs[j]
                    verts.append(((x, y, H[i, j]), tuple(normals[i, j]), (x * uv_scale, y * uv_scale)))

            def grid_of(k):
                return i0 + k // w, j0 + k % w

            high = {}
            if field is not None:
                for k in range(len(verts)):
                    high[k] = bool(field[grid_of(k)] >= 0)
            # the cells' triangles and their materials (None: cut by the field)
            faces = []
            for i in range(i1 - i0):
                for j in range(j1 - j0):
                    a, b = i * w + j, (i + 1) * w + j
                    c, d = b + 1, a + 1
                    for t in ((a, b, c), (a, c, d)):
                        mat = material([np.array(verts[k][0]) for k in t])
                        if mat is None and field is None:
                            raise ValueError("material() gave None but ground_tiles has no field")
                        faces.append((t, mat))
            # edges a cut triangle splits: (low vertex, high vertex) -> the cut vertex
            cut_at = {}
            for t, mat in faces:
                if mat is None:
                    for u, v in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
                        if high[u] != high[v]:
                            cut_at[min(u, v), max(u, v)] = None
            for (u, v) in cut_at:
                fu, fv = field[grid_of(u)], field[grid_of(v)]
                s = min(max(fu / (fu - fv), CUT_MIN), 1.0 - CUT_MIN)
                (pu, nu, tu), (pv, nv, tv) = verts[u], verts[v]
                pos = tuple(pu[q] + s * (pv[q] - pu[q]) for q in range(3))
                nrm = np.add(np.multiply(nu, 1 - s), np.multiply(nv, s))
                cut_at[u, v] = len(verts)
                verts.append((pos, tuple(nrm / np.linalg.norm(nrm)), (pos[0] * uv_scale, pos[1] * uv_scale)))

            def cut(u, v):
                return cut_at.get((min(u, v), max(u, v)))

            pieces = []     # (material, (a, b, c)), counterclockwise as the cell's triangles
            for t, mat in faces:
                if mat is None:
                    keys_of = [keys[0] if high[k] else keys[1] for k in t]
                    if keys_of[0] == keys_of[1] == keys_of[2]:
                        pieces.append((keys_of[0], t))
                        continue
                    # the corner alone on its side of the line, then the other two in order
                    lone = next(q for q in range(3) if keys_of[q] != keys_of[(q + 1) % 3]
                                and keys_of[q] != keys_of[(q + 2) % 3])
                    v0, v1, v2 = t[lone], t[(lone + 1) % 3], t[(lone + 2) % 3]
                    m1, m2 = cut(v0, v1), cut(v0, v2)
                    pieces.append((keys_of[lone], (v0, m1, m2)))
                    other = keys_of[(lone + 1) % 3]
                    pieces.append((other, (m1, v1, v2)))
                    pieces.append((other, (m1, v2, m2)))
                    continue
                ring = []
                for q in range(3):
                    ring.append(t[q])
                    m = cut(t[q], t[(q + 1) % 3])
                    if m is not None:
                        ring.append(m)
                if len(ring) == 3:
                    pieces.append((mat, t))
                    continue
                # a fixed triangle beside a cut: a fan from its centre through the cut points
                ps = [verts[k][0] for k in t]
                pos = tuple(sum(p[q] for p in ps) / 3 for q in range(3))
                nrm = np.sum([verts[k][1] for k in t], axis=0)
                centre = len(verts)
                verts.append((pos, tuple(nrm / np.linalg.norm(nrm)), (pos[0] * uv_scale, pos[1] * uv_scale)))
                for q in range(len(ring)):
                    pieces.append((mat, (centre, ring[q], ring[(q + 1) % len(ring)])))
            side = {}   # (vertex, axis) -> its side-projected copy, for cliff faces
            for mat, t in pieces:
                if mat == cliff:
                    # steep faces take their texture from the side (u along the
                    # face, v up it) instead of stretching a top-down projection
                    pts = [np.array(verts[k][0]) for k in t]
                    fn = np.cross(pts[1] - pts[0], pts[2] - pts[0])
                    axis = 0 if abs(fn[0]) >= abs(fn[1]) else 1
                    new = []
                    for k in t:
                        if (k, axis) not in side:
                            (x, y, z), nrm, _ = verts[k]
                            side[k, axis] = len(verts)
                            verts.append(((x, y, z), nrm, ((y if axis == 0 else x) * uv_scale, z * uv_scale)))
                        new.append(side[k, axis])
                    t = tuple(new)
                tris.append((mat,) + tuple(t))
            # cut points on the tile's rim, for its sides
            rim_cuts = {}
            for (u, v), m in cut_at.items():
                (iu, ju), (iv, jv) = grid_of(u), grid_of(v)
                if (iu == iv and iu in (i0, i1)) or (ju == jv and ju in (j0, j1)):
                    rim_cuts[(iu, ju), (iv, jv)] = verts[m][0]
            close_slab(verts, tris, xs, H, i0, i1, j0, j1, cliff, uv_scale, rim_cuts)
            # % makes the tile instanced geometry; ? lights it per vertex
            yield f"{prefix}_{i0 // tile}_{j0 // tile}", verts, tris


def sky_box(half, floor, ceiling, fill, sky="sky", uv_scale=1.0):
    """The level's structure: a sealed +sky box round the ground. The ground itself
    is instanced geometry inside it, which tool compiles tile by tile instead of
    into one huge BSP. `fill` is the material of a small box buried under the
    ground: the lightmapper needs some non-sky mesh in the structure itself."""
    corners = [(x, y, z) for z in (floor, ceiling) for y in (-half, half) for x in (-half, half)]
    # the floor is +sky too: lit, a huge floor face takes most of the lightmap
    # atlas and leaves the buildings' interiors a few pixels each
    faces = [((0, 1, 3, 2), sky, (0, 0, 1)), ((4, 5, 7, 6), sky, (0, 0, -1)),
             ((0, 1, 5, 4), sky, (0, 1, 0)), ((2, 3, 7, 6), sky, (0, -1, 0)),
             ((0, 2, 6, 4), sky, (1, 0, 0)), ((1, 3, 7, 5), sky, (-1, 0, 0))]
    verts, tris = [], []
    for quad, mat, inward in faces:
        base = len(verts)
        for k in quad:
            x, y, z = corners[k]
            verts.append(((x, y, z), inward, (x * uv_scale, y * uv_scale)))
        p = [np.array(corners[k]) for k in quad]
        # wind each face counterclockwise seen from inside the box
        flip = np.dot(np.cross(p[1] - p[0], p[2] - p[0]), inward) < 0
        for t in ((0, 1, 2), (0, 2, 3)):
            t = (t[0], t[2], t[1]) if flip else t
            tris.append((mat,) + tuple(base + k for k in t))
    lo, hi, z0, z1 = -1.0, 1.0, floor + 1.0, floor + 2.0
    box = [(x, y, z) for z in (z0, z1) for y in (lo, hi) for x in (lo, hi)]
    for (q, out) in (((0, 2, 3, 1), (0, 0, -1)), ((4, 5, 7, 6), (0, 0, 1)), ((0, 1, 5, 4), (0, -1, 0)),
                     ((2, 6, 7, 3), (0, 1, 0)), ((0, 4, 6, 2), (-1, 0, 0)), ((1, 3, 7, 5), (1, 0, 0))):
        b0 = len(verts)
        for k in q:
            x, y, z = box[k]
            verts.append(((x, y, z), out, (x * uv_scale, y * uv_scale)))
        p = [np.array(box[k]) for k in q]
        flip = np.dot(np.cross(p[1] - p[0], p[2] - p[0]), out) < 0
        for t in ((0, 1, 2), (0, 2, 3)):
            t = (t[0], t[2], t[1]) if flip else t
            tris.append((fill,) + tuple(b0 + k for k in t))
    return "sky_box", verts, tris

"""Props imported from model files: a textured OBJ (Z up, metres, origin at the
foot of the model, front toward -y) becomes a Halo 3 object through the kit's
own model pipeline.

    data\\<props>\\<name>\\render\\<name>.JMS      the OBJ's triangles  -> tool render
    data\\<props>\\<name>\\collision\\<name>.JMS   closed boxes        -> tool collision
    data\\<props>\\<name>\\physics\\<name>.JMS     box primitives      -> tool physics (crates)
    data\\<props>\\bitmaps\\<material>.tif         its textures        -> tool bitmaps
    tags\\<props>\\<name>\\shaders\\<material>     a diffuse (or alpha-tested) shader each
    tags\\<props>\\<name>\\<name>.model / .scenery or .crate   from a stock prop's tags

A scenery prop placed with Plan.prop becomes a static machine (machines.py):
no map-variant slot. A crate keeps its physics: players can push it around,
and it takes a map-variant slot like any crate.

    p = Prop("traffic_cone", folder, scale=0.62)
    build([p, ...])          -> {name: object tag path (no extension)}; exits on a tool error
    p.tag, p.kind            what Plan.prop takes
"""

import base64
import math
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageChops

from . import ek, jms
from .env import EK
from .project import active

SCENERY_TEMPLATE = ("objects\\gear\\human\\residential\\office_table\\office_table", "scenery")
CRATE_TEMPLATE = ("objects\\gear\\human\\residential\\office_chair\\office_chair", "crate")
MODEL_TEMPLATE = "objects\\gear\\human\\residential\\office_chair\\office_chair"
SHADER_TEMPLATE = "levels\\shared\\shaders\\simple\\grey150"              # diffuse: base_map only
ALPHA_TEMPLATE = "objects\\levels\\solo\\070_waste\\shaders\\dry_curly_plant"   # base_map + alpha_test_map
EMISSIVE_TEMPLATE = "objects\\levels\\multi\\cyberdyne\\shaders\\cyber_monitor_screen"   # base_map + self_illum_map
# its parameters, in order: base_map, self_illum_map, detail_map, detail_map2, diffuse_coefficient,
# specular_coefficient, roughness, area_specular_contribution, analytical_specular_contribution,
# self_illum_intensity, environment_map_specular_contribution, environment_map (each value one constant)
EMISSIVE_NO_SPECULAR = (5, 7, 8, 10)     # specular, area / analytical / environment-map specular: all 0


def _constant(value):
    """An animated parameter's function data (base64, as export-tag-to-xml prints it): a constant."""
    return base64.b64encode(bytes([1, 0x24, 0, 0]) + struct.pack("<ff", float(value), 1.0) + bytes(20)).decode()


def props_dir():
    """objects\\...\\imported: the props' tag (and data) folder."""
    return active().tag_dir("imported")


@dataclass
class Prop:
    name: str
    folder: Path                    # holds <name>.obj, <name>.mtl and the textures
    scale: float = 0.62             # world units per metre of the model
    kind: str = "scenery"           # or "crate" (pushable)
    material: str = "hard_metal_thin_hum_object"    # the global material it sounds and breaks like
    # collision boxes ((x0, y0, z0), (x1, y1, z1)) in the model's metres; None: its bounding box
    collision: list = None
    # physics boxes, the same way (crates); None: the collision boxes
    physics: list = None
    alpha: set = field(default_factory=set)         # materials drawn alpha-tested
    emissive: set = field(default_factory=set)      # materials that glow with their own picture (screens)
    tone: float = 1.0               # textures' brightness scaled by this (not the emissive ones)
    # with no `collision` boxes: the bounding box of these materials' faces only (a plant's pot,
    # not its leaves); empty: of the whole model
    collision_materials: tuple = ()
    # oriented collision boxes: each 8 corners (jms.closed_hull's order) in the model's metres; when set,
    # they are the collision instead of `collision` (a leaning board's tilted slab)
    hulls: list = None
    # a fixed physics model of box primitives (the collision boxes or hulls) for a scenery prop too: bipeds
    # walk on a prop through its physics model; a collision model alone stops only bullets
    static_physics: bool = False
    # set the object's bounding sphere from the model (else 0, and a big prop is culled when its origin
    # leaves the view)
    bounds: bool = False

    @property
    def tag(self):
        return f"{props_dir()}\\{self.name}\\{self.name}"

    @property
    def data_dir(self):
        return EK / "data" / Path(*props_dir().split("\\")) / self.name


# -- reading the model ----------------------------------------------------------------------

def read_obj(path):
    """(positions, uvs, normals, [(material, [(vi, ti, ni) x3])]) of a triangulated OBJ."""
    P, T, N, faces, mat = [], [], [], [], None
    for line in path.read_text().splitlines():
        a = line.split()
        if not a:
            continue
        if a[0] == "v":
            P.append(tuple(float(x) for x in a[1:4]))
        elif a[0] == "vt":
            T.append(tuple(float(x) for x in a[1:3]))
        elif a[0] == "vn":
            N.append(tuple(float(x) for x in a[1:4]))
        elif a[0] == "usemtl":
            mat = a[1]
        elif a[0] == "f":
            corners = []
            for c in a[1:]:
                parts = (c.split("/") + ["", ""])[:3]
                corners.append(tuple(int(x) - 1 if x else -1 for x in parts))
            for k in range(1, len(corners) - 1):        # fan, in case of a stray quad
                faces.append((mat, [corners[0], corners[k], corners[k + 1]]))
    return P, T, N, faces


def read_mtl(path):
    """{material: (diffuse texture file, alpha texture file or None)}."""
    out, cur = {}, None
    for line in path.read_text().splitlines():
        a = line.split()
        if not a:
            continue
        if a[0] == "newmtl":
            cur = a[1]
            out[cur] = [None, None]
        elif a[0] == "map_Kd" and cur:
            out[cur][0] = a[-1]
        elif a[0] == "map_d" and cur:
            out[cur][1] = a[-1]
    return {k: tuple(v) for k, v in out.items()}


def bounds(P):
    xs, ys, zs = zip(*P)
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


# -- the source files -----------------------------------------------------------------------

def _bitmap_name(prop, mat):
    return mat if mat.startswith(prop.name) else f"{prop.name}_{mat}"


def write_sources(prop):
    """The JMS files and the textures as TIFFs; returns (materials, bitmaps dir)."""
    P, T, N, faces = read_obj(prop.folder / f"{prop.name}.obj")
    mtl = read_mtl(prop.folder / f"{prop.name}.mtl")
    s = prop.scale
    bmp_dir = EK / "data" / Path(*props_dir().split("\\")) / "bitmaps"
    bmp_dir.mkdir(parents=True, exist_ok=True)
    materials = {}
    for mat, (diffuse, alpha) in mtl.items():
        name = _bitmap_name(prop, mat)
        img = Image.open(prop.folder / diffuse)
        img = img.convert("RGBA") if (alpha or mat in prop.alpha) else img.convert("RGB")
        if alpha and alpha != diffuse:
            img.putalpha(Image.open(prop.folder / alpha).convert("L"))
        rgb = img.convert("RGB")
        r_, g_, b_ = rgb.split()
        if ImageChops.difference(r_, g_).getbbox() is None and ImageChops.difference(g_, b_).getbbox() is None:
            # a pure grey picture: tool bitmaps stores it monochrome and the shader then draws it white
            # (a dark grey bin came out white and bright): a faint blue tint
            bands = list(img.split())
            bands[2] = bands[2].point(lambda v: min(255, v + 3))
            img = Image.merge(img.mode, bands)
        if prop.tone != 1.0 and mat not in prop.emissive:
            bands = list(img.split())
            for i in range(3):
                bands[i] = bands[i].point(lambda v, k=prop.tone: int(v * k))
            img = Image.merge(img.mode, bands)
        img.save(bmp_dir / f"{name}.tif")
        materials[mat] = (name, bool(alpha) or mat in prop.alpha)

    render = jms.Model()
    for mat, corners in faces:
        m = render.material(materials[mat][0])
        cs = []
        for vi, ti, ni in corners:
            p = tuple(c * s for c in P[vi])
            n = N[ni] if ni >= 0 else (0.0, 0.0, 1.0)
            uv = T[ti] if ti >= 0 else (0.0, 0.0)
            cs.append((p, n, uv))
        render.triangle(m, cs)
    render.write(prop.data_dir / "render" / f"{prop.name}.JMS")

    lo, hi = bounds(P)
    if prop.collision_materials:
        used = [P[vi] for mat, corners in faces if mat in prop.collision_materials for vi, _, _ in corners]
        if not used:
            raise ValueError(f"{prop.name}: no faces of {prop.collision_materials}")
        lo, hi = bounds(used)
    boxes = prop.collision or [(lo, hi)]
    col = jms.Model()
    cm = col.material(prop.material)
    if prop.hulls:
        for hull in prop.hulls:
            col.closed_hull(cm, [tuple(c * s for c in p) for p in hull])
    else:
        for a, b in boxes:
            col.closed_box(cm, tuple(c * s for c in a), tuple(c * s for c in b))
    col.write(prop.data_dir / "collision" / f"{prop.name}.JMS")

    if prop.kind == "crate" or prop.static_physics:
        phy = jms.Model()
        pm = phy.material(prop.material)
        if prop.hulls and not prop.physics:
            for k, hull in enumerate(prop.hulls[:MAX_PHYSICS_BOXES]):
                centre, size, quat = _obb(hull, s)
                phy.box(f"box{k}", pm, centre, size, quat=quat)
        else:
            for k, (a, b) in enumerate(prop.physics or boxes):
                centre = tuple((a[i] + b[i]) / 2 * s for i in range(3))
                size = tuple((b[i] - a[i]) * s for i in range(3))
                phy.box(f"box{k}", pm, centre, size)
        phy.write(prop.data_dir / "physics" / f"{prop.name}.JMS")
    return materials, bmp_dir


MAX_PHYSICS_BOXES = 64


def _obb(hull, s):
    """(centre, size, quaternion (i, j, k, w)) in world units of a hull's 8 corners (jms.closed_hull's
    order): its axes are corner 1 - 0 (x), 2 - 0 (y), 4 - 0 (z)."""
    c = [tuple(v * s for v in p) for p in hull]
    ax = [[c[k][i] - c[0][i] for i in range(3)] for k in (1, 2, 4)]
    size = [math.sqrt(sum(v * v for v in a)) for a in ax]
    cols = [[v / (L or 1.0) for v in a] for a, L in zip(ax, size)]
    centre = tuple(sum(p[i] for p in c) / 8 for i in range(3))
    # rotation matrix R (columns = the box's axes in the model frame) -> quaternion
    r = [[cols[j][i] for j in range(3)] for i in range(3)]
    tr = r[0][0] + r[1][1] + r[2][2]
    if tr > 0:
        q = math.sqrt(tr + 1.0) * 2
        w, x, y, z = 0.25 * q, (r[2][1] - r[1][2]) / q, (r[0][2] - r[2][0]) / q, (r[1][0] - r[0][1]) / q
    elif r[0][0] > r[1][1] and r[0][0] > r[2][2]:
        q = math.sqrt(1.0 + r[0][0] - r[1][1] - r[2][2]) * 2
        w, x, y, z = (r[2][1] - r[1][2]) / q, 0.25 * q, (r[0][1] + r[1][0]) / q, (r[0][2] + r[2][0]) / q
    elif r[1][1] > r[2][2]:
        q = math.sqrt(1.0 + r[1][1] - r[0][0] - r[2][2]) * 2
        w, x, y, z = (r[0][2] - r[2][0]) / q, (r[0][1] + r[1][0]) / q, 0.25 * q, (r[1][2] + r[2][1]) / q
    else:
        q = math.sqrt(1.0 + r[2][2] - r[0][0] - r[1][1]) * 2
        w, x, y, z = (r[1][0] - r[0][1]) / q, (r[0][2] + r[2][0]) / q, (r[1][2] + r[2][1]) / q, 0.25 * q
    return centre, tuple(max(v, 0.01) for v in size), (x, y, z, w)


def radius(prop):
    """(bounding radius, offset (x, y, z)) in world units: a sphere round the model's box."""
    P, _, _, _ = read_obj(prop.folder / f"{prop.name}.obj")
    lo, hi = bounds(P)
    mid = [(lo[i] + hi[i]) / 2 * prop.scale for i in range(3)]
    r = math.sqrt(sum(((hi[i] - lo[i]) / 2 * prop.scale) ** 2 for i in range(3)))
    return r * 1.05, mid


def size(prop):
    """(width, depth, height) in world units."""
    P, _, _, _ = read_obj(prop.folder / f"{prop.name}.obj")
    lo, hi = bounds(P)
    return tuple((hi[i] - lo[i]) * prop.scale for i in range(3))


# -- the tags -------------------------------------------------------------------------------

def shader_lines(prop, materials):
    lines = []
    bdir = f"{props_dir()}\\bitmaps"
    for mat, (name, alpha) in materials.items():
        out = f"{props_dir()}\\{prop.name}\\shaders\\{name}"
        if mat in prop.emissive:
            lines += [f"load\t{EMISSIVE_TEMPLATE}\tshader",
                      f"set\trender_method/parameters[0]/bitmap\t{bdir}\\{name},bitmap",
                      f"set\trender_method/parameters[1]/bitmap\t{bdir}\\{name},bitmap"]
            # the template is glossy (two-lobe phong, specular 1.0, roughness 0.22): on a curved CRT with a
            # light in front of it that's a white hotspot over the picture
            for i in EMISSIVE_NO_SPECULAR:
                lines.append(f"set\trender_method/parameters[{i}]/animated parameters[0]/function/data\t{_constant(0.0)}")
        elif alpha:
            lines += [f"load\t{ALPHA_TEMPLATE}\tshader",
                      f"set\trender_method/parameters[0]/bitmap\t{bdir}\\{name},bitmap",
                      f"set\trender_method/parameters[1]/bitmap\t{bdir}\\{name},bitmap"]
        else:
            lines += [f"load\t{SHADER_TEMPLATE}\tshader",
                      "set\trender_method/options[0]/short\t0",
                      f"set\trender_method/parameters[0]/bitmap\t{bdir}\\{name},bitmap",
                      "remove\trender_method/parameters\t11"]     # grey150's albedo colour
        lines.append(f"saveas\t{out}\tshader")
    return lines


def object_lines(prop):
    tag = prop.tag
    lines = [f"load\t{MODEL_TEMPLATE}\tmodel",
             f"set\trender model\t{tag},render_model",
             f"set\tcollision model\t{tag},collision_model",
             f"set\tphysics_model\t{tag + ',physics_model' if prop.kind == 'crate' or prop.static_physics else ''}",
             f"set\tmaterials[0]/material name\t{prop.material}",
             f"set\tmaterials[0]/global material name\t{prop.material}",
             f"saveas\t{tag}\tmodel"]
    src, ext = CRATE_TEMPLATE if prop.kind == "crate" else SCENERY_TEMPLATE
    lines += [f"load\t{src}\t{ext}",
              f"set\tobject/model\t{tag},model"]
    if prop.bounds:
        r, mid = radius(prop)
        lines += [f"set\tobject/bounding radius\t{r:.4f}",
                  f"set\tobject/bounding offset\t{mid[0]:.4f},{mid[1]:.4f},{mid[2]:.4f}"]
    lines.append(f"saveas\t{tag}\t{ext}")
    if prop.static_physics and prop.kind != "crate":      # never moves (office_table's body is a dynamic box)
        lines += [f"load\t{tag}\tphysics_model",
                  "set\trigid bodies[0]/motion type\tfixed",
                  f"save"]
    return lines


def build(props, verbose=True):
    """Every prop's sources, bitmaps, shaders, models and object tag. Returns {name: Prop}."""
    shader_script, bmp_dir = [], None
    for p in props:
        materials, bmp_dir = write_sources(p)
        shader_script += shader_lines(p, materials)
    if bmp_dir is not None:
        code, tail = ek.tool("bitmaps", f"{props_dir()}\\bitmaps", log="props_bitmaps.log")
        if code:
            sys.exit("tool bitmaps (props) failed:\n" + "\n".join(tail))
        ek.mbedit(shader_script, "props_shaders.txt")
    for p in props:
        src = f"{props_dir()}\\{p.name}"
        steps = [("render", src, "draft"), ("collision", src)] + (
            [("physics", src)] if p.kind == "crate" or p.static_physics else [])
        for args in steps:
            code, tail = ek.tool(*args, log=f"props_{args[0]}.log")
            ext = {"render": "render_model", "collision": "collision_model", "physics": "physics_model"}[args[0]]
            out = EK / "tags" / Path(*p.tag.split("\\")).with_suffix("." + ext)
            if code or not out.exists():
                sys.exit(f"tool {args[0]} {p.name} failed:\n" + "\n".join(tail))
        if verbose:
            w, d, h = size(p)
            print(f"prop {p.name}: {p.kind}, {w:.2f} x {d:.2f} x {h:.2f} units")
    ek.mbedit([line for p in props for line in object_lines(p)], "props_objects.txt")
    return {p.name: p for p in props}


def footprint_radius(prop):
    w, d, _ = size(prop)
    return math.hypot(w, d) / 2

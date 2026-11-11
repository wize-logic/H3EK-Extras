"""The example map's level: rolling ground 300 units across with a hill in the
middle, and a bunker for each team. Red's half (+x) is written once and turned
180 degrees about the origin for blue, so both teams get the same base.

    python3 maps/example/level.py [out.ASS]     # writes ground.npz and the level .ASS

Meshes follow h3kit.mesh's rules: closed shells that overlap where they meet,
never just touch, and no coplanar overlapping faces (mesh.check() finds them).
"""

import sys
from pathlib import Path

import numpy as np

import project
from h3kit import ass, mesh
from h3kit.mesh import Frame, Part
from h3kit.terrain import Heightfield

import look

HERE = Path(__file__).resolve().parent
NPZ = HERE / "ground.npz"
HALF, STEP = 150.0, 5.0          # the ground spans -HALF..HALF, one sample every STEP
BASE_X = 100.0                   # red's bunker; blue's is at -BASE_X
BUNKER = dict(half=6.0, wall=0.5, height=3.0, door=1.2)


def heights(x, y):
    """Gentle rolling ground, flat round each base, a hill in the middle, rising at the edges."""
    h = 1.5 * np.sin(x / 23.0) * np.cos(y / 19.0) + 1.0 * np.cos((x + y) / 31.0)
    for bx in (BASE_X, -BASE_X):     # level pads for the bunkers
        d = np.hypot(x - bx, y)
        h *= np.clip((d - 14.0) / 10.0, 0.0, 1.0)
    h += 8.0 * np.exp(-(x * x + y * y) / (2 * 18.0 ** 2))          # the centre hill
    h += 30.0 * np.clip((np.maximum(np.abs(x), np.abs(y)) - 120.0) / 30.0, 0.0, 1.0) ** 2   # edge walls
    return h


def grid():
    xs = np.arange(-HALF, HALF + 0.01, STEP)
    X, Y = np.meshgrid(xs, xs, indexing="ij")
    H = heights(X, Y)
    return Heightfield(xs, 0.5 * (H + H[::-1, ::-1]))     # exactly point-symmetric


def material(pts):
    n = np.cross(pts[1] - pts[0], pts[2] - pts[0])
    return "ground" if n[2] / np.linalg.norm(n) > 0.8 else "cliff"


def bunker(team):
    """One team's bunker: floor, walls with a door toward the centre, roof, a light strip."""
    s = 1.0 if team == "red" else -1.0
    f = Frame(s * BASE_X, 0.0, 0.0, a=(-s, 0.0), b=(0.0, s))   # local a points at the enemy
    h, t, top, door = BUNKER["half"], BUNKER["wall"], BUNKER["height"], BUNKER["door"]
    p = Part(f"%!{team}_bunker")
    p.box(f, -h + 0.1, h - 0.1, -h + 0.1, h - 0.1, -0.5, 0.2, "floor")
    for b0, b1 in ((h - t, h), (-h, -h + t)):                       # side walls, full length
        p.box(f, -h, h, b0, b1, 0.1, top, "wall")
    p.box(f, -h - 0.05, -h + t, -h + t - 0.05, h - t + 0.05, 0.05, top - 0.05, "wall")   # back wall
    for b0, b1 in ((-h + t - 0.05, -door), (door, h - t + 0.05)):  # front wall, the door between
        p.box(f, h - t, h + 0.05, b0, b1, 0.05, top - 0.05, "wall")
    p.box(f, -h - 0.35, h + 0.35, -h - 0.3, h + 0.3, top - 0.2, top + 0.3, "wall", top_key="floor")   # roof
    p.box(f, -1.5, 1.5, -0.15, 0.15, top - 0.3, top - 0.15, "light")
    return p


def objects():
    """The bunkers as (name, vertices, triangles), checked for coplanar overlaps."""
    out = []
    for team in ("red", "blue"):
        p = bunker(team)
        bad = mesh.check(p)
        if bad:
            raise SystemExit(f"{p.name}: coplanar overlapping faces {bad[:3]}")
        out.append(p.result())
    return out


def write(ass_path=None):
    """ground.npz and the level .ASS (default: the project's, in the kit's data folder)."""
    t = grid()
    t.save(NPZ)
    extra = objects()
    tiles = list(ass.ground_tiles(t.xs, t.H, ass.normals_of(t.H, STEP), material, cliff="cliff", tile=20))
    box = ass.sky_box(HALF, -20.0, 200.0, "cliff")
    path = ass_path or project.PROJECT.ass_path
    lights = ass.fixture_lights(extra, look)
    n = ass.write(path, tiles + [box] + extra, look, lights,
                  header=project.PROJECT.ass_header, first_id=project.PROJECT.map_id)
    print(f"wrote {path}: {n[0]} objects, {n[2]} triangles, {len(lights)} lights")


def terrain():
    if not NPZ.exists():
        grid().save(NPZ)
    return Heightfield.load(NPZ)


if __name__ == "__main__":
    write(Path(sys.argv[1]) if len(sys.argv) > 1 else None)

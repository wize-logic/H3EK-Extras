"""The level's collision, read back from the compiled structure BSP, and the
engine's own point tests on it: does a player fit standing here?

A two-way teleporter pad on the same channel only receives a player if
(halo3_tag_test.exe FUN_14043fa00 / FUN_1405aeb90 / collision_test_point
FUN_1406520b0):
  * the biped's standing havok shape at the destination (+0.2) touches nothing
    (structure, instanced geometry, objects);
  * the point half a biped height above it is inside a structure cluster and
    NOT inside any instanced geometry's solid (instance collision bsp leaf -1)
    or any object;
  * the player's moved origin is inside a cluster.
Otherwise the HUD says "teleporter blocked". The destination is about the
receiving pad's origin plus the rider's height above the sender pad.

    col = load_collision(path)    # written by `mbedit bspdump <structure bsp> <file>`
"""

from pathlib import Path


def load_collision(path):
    """Collision bsps written by `mbedit bspdump <structure bsp> <file>`."""
    lines = Path(path).read_text(encoding="latin-1").splitlines()
    pos = [0]

    def nxt():
        pos[0] += 1
        return lines[pos[0] - 1]

    def bsp():
        n = int(nxt().split()[1])
        nodes = [int(nxt()) & 0xFFFFFFFFFFFFFFFF for _ in range(n)]
        m = int(nxt().split()[1])
        planes = [tuple(float(v) for v in nxt().split(",")) for _ in range(m)]
        return nodes, planes

    inst = [dict(kv.split("=", 1) for kv in nxt().split("|")) for _ in range(int(nxt().split()[1]))]
    assert nxt() == "structure"
    structure = bsp()
    defs = []
    for _ in range(int(nxt().split()[1])):
        assert nxt() == "def"
        defs.append(bsp())
    for d in inst:
        d["centre"] = tuple(float(v) for v in d["world bounding sphere center"].split(","))
        d["radius"] = float(d["world bounding sphere radius"])
    return {"structure": structure, "defs": defs, "instances": inst}


def _leaf(bsp, p):
    """The engine's 3d bsp walk (FUN_1404ab6f0, 8-byte nodes): leaf index, or -1 for solid."""
    nodes, planes = bsp
    if not nodes:
        return 0
    k = 0
    while True:
        v = nodes[k]
        a, b, c, d = planes[v & 0xFFFF]
        child = (v >> 40) & 0xFFFFFF if a * p[0] + b * p[1] + c * p[2] - d >= 0 else (v >> 16) & 0xFFFFFF
        if child == 0xFFFFFF:
            return -1
        if child & 0x800000:
            return child & 0x7FFFFF
        k = child


def solid_at(col, p):
    """Why the point p fails collision_test_point: 'outside the structure', or the
    names of instanced geometry it is inside; [] if clear. (Identity instance
    transforms, as ass.write writes them.)"""
    if _leaf(col["structure"], p) == -1:
        return ["outside the structure"]
    out = []
    for d in col["instances"]:
        c, r = d["centre"], d["radius"]
        if (c[0] - p[0]) ** 2 + (c[1] - p[1]) ** 2 + (c[2] - p[2]) ** 2 > r * r:
            continue
        if _leaf(col["defs"][int(d["instance definition"])], p) == -1:
            out.append(d["name"])
    return out


def standing_room(col, x, y, z, height=1.8, radius=0.4):
    """Problems for a player standing at (x, y, z): solid geometry anywhere in a
    column `height` tall and `radius` round (the receiver test needs about 0.2..1.1
    above a pad's top; this asks for margin)."""
    bad = set()
    for dz in [0.05 + 0.1 * k for k in range(int(height / 0.1))]:
        for ox, oy in ((0, 0), (radius, 0), (-radius, 0), (0, radius), (0, -radius)):
            bad.update(solid_at(col, (x + ox, y + oy, z + dz)))
    return sorted(bad)


def blocked_teleporters(plan, col):
    """[(placement, problems)] for every teleporter whose pad has no standing room."""
    out = []
    for p in plan.items:
        kind, tag = p.resolve()
        if p.channel >= 0 or "teleporter" in tag:
            bad = standing_room(col, *p.position)
            if bad:
                out.append((p, bad))
    return out

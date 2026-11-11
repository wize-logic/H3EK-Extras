"""Try lighting in minutes: bake a small scratch level and read the light on
its measuring floors, instead of waiting hours for a full build.

A test level is any .ASS with per-vertex measuring floors (floor_grid) last
among its objects. run() compiles it (tool structure), bakes it as its own job
(JOB, never a real build's) and prints the median light per floor, with an
estimate for a medium bake. Reference: sunlit ground measures about 1.48 at
medium. Medium adds bounce light, ~3.3x the draft numbers. p10 is often ~0:
vertices under furniture or against walls.

Every floor needs a different cell count, so measure() can tell their
lightprobe blocks apart. Don't run a test during a real bake: both use every
core, and each slows the other badly.
"""

import re
import sys
from pathlib import Path

import numpy as np

from . import ek
from .env import EK, EK_WIN, WORK
from .mesh import Part

JOB = "222"          # the test bake's faux\<job> (a real build uses its project's light_job)
STEP = 0.6           # measuring grid cell (world units)
MEDIUM_FACTOR = 3.3  # medium / draft light, measured


def floor_grid(name, a0, a1, b0, b1, z, step=STEP):
    """A per-vertex measuring floor ("%?" in the name): a closed slab 0.1 deep
    whose top is a grid of step-sized cells (the lightmapper lights each vertex)."""
    p = Part(name)
    na, nb = int(round((a1 - a0) / step)), int(round((b1 - b0) / step))
    faces = []
    for i in range(na):
        for j in range(nb):
            x0, x1 = a0 + i * step, a0 + (i + 1) * step
            y0, y1 = b0 + j * step, b0 + (j + 1) * step
            faces.append(("floor", [(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)]))
    zb = z - 0.1
    faces.append(("floor", [(a0, b0, zb), (a0, b1, zb), (a1, b1, zb), (a1, b0, zb)]))
    # sides: one polygon each, through the grid's edge points (no T-junctions)
    xs = [a0 + i * step for i in range(na + 1)]
    ys = [b0 + j * step for j in range(nb + 1)]
    faces.append(("floor", [(x, b0, z) for x in xs][::-1] + [(a0, b0, zb), (a1, b0, zb)]))
    faces.append(("floor", [(x, b1, z) for x in xs] + [(a1, b1, zb), (a0, b1, zb)]))
    faces.append(("floor", [(a0, y, z) for y in ys] + [(a0, b1, zb), (a0, b0, zb)]))
    faces.append(("floor", [(a1, y, z) for y in ys][::-1] + [(a1, b0, zb), (a1, b1, zb)]))
    out = []
    for k, pts in faces:
        while pts[0][2] != zb and any(q[2] == zb for q in pts):
            pts = pts[1:] + pts[:1]
        out.append((k, pts))
    p.shell(out)
    return p


def level_paths(level):
    """(scenario tag, bsp name, .ASS path) of a test level at tags folder `level`
    (e.g. levels\\test\\lt_barracks); tool structure makes the scenario."""
    name = level.split("\\")[-1]
    return f"{level}\\{name}", name, EK / "data" / Path(*level.split("\\")) / "structure" / f"{name}.ASS"


def _h(v):
    return np.array(v, dtype=np.uint16).view(np.float16).astype(float)


def measure(level, floors, label="last"):
    """Per-vertex light on each measuring floor ({name: ...}, in the order they were
    written, last in the level), from the bake's lightmap bsp data: the SH DC term
    of r, g, b as luminance, and the dominant light intensity."""
    scenario, _, _ = level_paths(level)
    (WORK / "lighting_test").mkdir(exist_ok=True)
    out = f"{EK_WIN}\\work\\lighting_test\\lbd_{label}.xml"
    import subprocess
    subprocess.run([str(EK / ek.TOOL), "export-tag-to-xml", f"{EK_WIN}\\tags\\{scenario}.scenario_lightmap_bsp_data",
                    out], cwd=EK, capture_output=True)
    s = (WORK / "lighting_test" / f"lbd_{label}.xml").read_text(encoding="latin-1")
    s = s[:s.find('<block name="clusters"')]
    blocks = s.split('<block name="lightprobe data"')[1:]
    rows = []
    for b in blocks:
        els = [e for e in b.split("<element")[1:] if "dominant light intensity" in e]
        if not els:
            continue
        dom, dc = [], []
        for el in els:
            d = [int(x) for x in re.findall(r'"dominant light intensity [rgb]" value="(-?\d+)"', el)]
            terms = re.split(r'lightprobe terms', el)[1:]
            c0 = [int(re.findall(r'"coefficient" value="(-?\d+)"', t)[0]) for t in terms]
            dom.append(_h([x & 0xffff for x in d]))
            dc.append(_h([x & 0xffff for x in c0]))
        lum = np.array(dc) @ np.array([0.2126, 0.7152, 0.0722])
        rows.append((len(els), lum, np.array(dom).mean()))
    for name, (n, lum, dom) in zip(floors, rows[-len(floors):]):
        q = np.percentile(lum, [10, 50, 90])
        print(f"{name:22s} {n:4d} verts  median {q[1]:.3f}  p10 {q[0]:.3f}  p90 {q[2]:.3f}  "
              f"(~{q[1] * MEDIUM_FACTOR:.2f} at medium)  dominant {dom:.3f}")


def run(level, floors, quality="draft", label=None):
    """Compile the test level already written at level_paths(level), bake it as JOB
    and measure its floors (about 5 minutes at draft)."""
    scenario, bsp_name, _ = level_paths(level)
    code, tail = ek.tool("structure", f"{level}\\structure\\{bsp_name}.ASS", log="lighting_test_structure.log")
    if code:
        sys.exit("tool structure failed (H3EK\\work\\lighting_test_structure.log):\n" + "\n".join(tail))
    code, tail = ek.bake(scenario, bsp_name, quality, job=JOB, log="lighting_test_bake.log")
    if code:
        sys.exit("bake failed (H3EK\\work\\lighting_test_bake.log):\n" + "\n".join(tail[-3:]))
    done = [l.strip() for l in (WORK / "lighting_test_bake.log").read_text(errors="replace").splitlines()
            if l.startswith("*** finished")]
    print("\n".join(done))
    measure(level, floors, label or quality)

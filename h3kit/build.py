"""Build a map: a new level inside a copy of a stock map's scenario, laid
out, lit and compiled, with the project's donors ported in.

The steps (Builder.run):

    map.write_level(.ASS)           the level mesh with its generic lights
    mbedit pre-structure lines       tags tool structure needs (e.g. copied shaders)
    tool_fast structure <.ASS>      -> structure bsp + structure lighting info
    mbedit bspdump                  -> the level's collision (standing-room checks)
    map.plan(terrain, collision)    every placement (a scenario.Plan)
    mbedit <name>.txt               the map's tag scripts, then the scenario from the
                                    base map's copy: the new BSP and its lighting info,
                                    cleared stock objects, the placements, split resources
    the light bake (faux)           -> the project's light stamp (what it was made from)
    tool_fast build-cache-file      -> H3EK\\maps\\<name>.map
    checks                          placements counted in the built map
    donor.port(map) per donor       tags from other built maps
    copy                            the map into the package's maps\\

--reuse-light skips the level compile and the bake (most of a build's time)
and keeps the last bake: for changes to vehicles, weapons, equipment and
machines. It refuses when the level (geometry, materials or lights) would
differ from the bake's, or when scenery or crates moved (the bake lights
those too), except for the map's late_tags placed after every baked crate.
--plan-only builds the layout and the scenario script without touching the
kit's tags, and says whether --reuse-light would be accepted.

A map gives the build a Map (see the class below) and calls main(map).
"""

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

from . import ek, lights, object_memory
from . import scenario as sc
from .collision import blocked_teleporters, load_collision
from .env import EK
from .project import active

# the old level's data that no longer fits: split resources to drop
DROPPED_RESOURCES = ["light resource", "effect scenery", "decal resource",
                     "cluster data resource", "sound scenery resource", "decorator resource",
                     "structure lighting resource", "cubemap reference resource"]
# split resources a map may take over (Map.resources() keys)
RESOURCE_FIELDS = {"decorators": "decorator resource", "lights": "light resource",
                   "devices": "device resource", "effect_scenery": "effect scenery",
                   "decals": "decal resource", "sound_scenery": "sound scenery resource",
                   "cluster_data": "cluster data resource", "structure_lighting": "structure lighting resource",
                   "cubemap": "cubemap reference resource"}
# placement blocks cleared in each resource copy
CLEARED = {"scenery": ["scenerys", "crates"], "vehicles": ["vehicles"],
           "weapons": ["weapons"], "equipment": ["equipments"]}
BAKED_KINDS = ("scenery", "crate", "machine")   # placed objects the bake lights (scenery / machine probes:
                                                # scenario.bake_mirror shows them to it)
QUALITIES = ["draft", "low", "medium", "high", "none"]


class Map:
    """What a map gives the build. Subclass it; write_level, terrain and plan are required."""

    # placement tags the layout puts after every baked crate: a reuse build accepts them
    # though the bake never saw them (they take new slots at the end of the crate block)
    late_tags = ()

    def write_level(self, ass_path):
        """Write the level .ASS to ass_path (and whatever the terrain reads)."""
        raise NotImplementedError

    def pre_structure_lines(self):
        """mbedit lines that must run before tool structure (shaders the level names)."""
        return []

    def terrain(self):
        """The ground the layout stands things on (scenario.py's terrain API)."""
        raise NotImplementedError

    def plan(self, terrain, collision):
        """The built layout (a scenario.Plan); collision: collision.load_collision() of the level."""
        raise NotImplementedError

    def tag_script(self, plan):
        """mbedit lines making the map's own tags, run before the scenario edit. Default:
        the machines the plan uses and every donor's placeholders."""
        from . import machines
        lines = machines.tag_script()
        for d in active().donors:
            lines += d.tag_script()
        return lines

    def scenario_lines(self):
        """Extra scenario edits (sky, atmosphere, cluster data...), after new_level_edits()."""
        return []

    def resources(self, plan, terrain):
        """{RESOURCE_FIELDS key: mbedit lines} for split resources the map fills in
        (copied from the base map's, edited, saved as the map's own); the key
        "scenario" adds lines to the scenario itself."""
        return {}

    def finish_script(self, lines):
        """The whole mbedit script, last: a map may add lines inside a resource
        copy the layout writes (before its saveas), e.g. device groups."""
        return lines

    def design(self, d):
        """Fill the structure design (design.Design: soft ceilings, water volumes).
        Return False (the default) for a map without one."""
        return False

    def cubemap_points(self):
        """[(x, y, z)] where the game renders the level's cubemaps (dynamic environment
        maps for reflective shaders): the kit's standalone game renders them with
        `cubemap_dynamic_generate`, and `tool cubemaps` imports the result. Empty: no cubemaps."""
        return []


def lighting_info():
    return f"{active().bsp},scenario_structure_lighting_info"


def lightmap():
    """The bake's lightmap (the farm points the scenario at it)."""
    return f"{active().scenario}_faux_lightmap,scenario_lightmap"


def design_tag():
    """The structure design tag tool structure-design makes: <level>\\<bsp>_design."""
    p = active()
    return f"{p.bsp_dir}\\{p.bsp_name}_design"


def design_ass():
    p = active()
    return EK / "data" / Path(*p.bsp_dir.split("\\")) / "structure_design" / f"{p.bsp_name}_design.ASS"


def cubemap_bitmap():
    """The bitmap `tool cubemaps` makes from the game's renders, if it exists."""
    p = active()
    tag = f"{p.bsp_dir}\\{p.name}_{p.bsp_name}_cubemaps"
    return tag if ek.tag_exists(tag, "bitmap") and (EK / "tags").exists() else None


def new_level_edits(reuse_light=False, design=None, cubemaps=None):
    """mbedit lines for the scenario and each resource copy, beyond scenario.script():
    the new BSP in place of the base map's, its lighting info (the lightmapper reads
    the lights only through this reference: leaving it empty bakes no lights), the old
    level's data dropped. The lightmap reference is cleared for a new bake, or kept
    (reuse_light). `design`: the structure design tag (or None); `cubemaps`: the
    cubemap bitmap (or None)."""
    bsp = active().bsp
    info = lighting_info()
    sddt = f"{design},structure_design" if design else ""
    cube = f"{cubemaps},bitmap" if cubemaps else ""
    scenario = [f"set\tstructure bsps[0]/structure bsp\t{bsp},scenario_structure_bsp",
                f"set\tstructure bsps[0]/structure lighting_info\t{info}",
                f"set\tstructure bsps[0]/structure design\t{sddt}",
                f"set\tstructure bsps[0]/cubemap bitmap group reference\t{cube}",
                f"set\tnew lightmaps\t{lightmap() if reuse_light else ''}",
                "clear\tscenario cluster data",
                "clear\tdecorators",
                "clear\tzone set pvs"]
    for field in DROPPED_RESOURCES:
        scenario.append(f"set\tscenario resources[0]/new split resources[0]/{field}\t")
    resources = {}
    for res, blocks in CLEARED.items():
        resources[res] = [f"clear\t{b}" for b in blocks] + [
            f"set\tstructure references[0]/structure bsp\t{bsp},scenario_structure_bsp",
            f"set\tstructure references[0]/structure design\t{sddt}",
            f"set\tstructure references[0]/structure lighting_info\t{info}",
            f"set\tstructure references[0]/cubemap bitmap group reference\t{cube}"]
    return scenario, resources


def script(m, plan, terrain, reuse_light=False):
    """The whole mbedit script: (lines, expected block counts)."""
    p = active()
    palettes, counts, _ = sc.stock_state()
    for res, blocks in CLEARED.items():
        for b in blocks:
            counts[b] = 0
    lines = sc.script(plan, palettes, counts, [])
    has_design = (EK / "tags" / Path(*design_tag().split("\\"))).with_suffix(".structure_design").exists()
    scenario, resources = new_level_edits(reuse_light, design_tag() if has_design else None, cubemap_bitmap())
    scenario += m.scenario_lines()
    points = m.cubemap_points()
    if points:
        cube = ["clear\tcubemaps"]
        for x, y, z in points:
            cube += ["add\tcubemaps", f"set\tcubemaps[{{cube}}]/cubemap position\t{x:.3f},{y:.3f},{z:.3f}",
                     "set\tcubemaps[{cube}]/cubemap resolution\t3"]   # enum: 16, 32, 64, 128, 256
        cube = [line.replace("{cube}", str(k)) for k, line in _numbered(cube)]
        scenario += cube
    # resources the map fills in: copy the stock one, edit, point at it
    taken = {}
    extra = dict(m.resources(plan, terrain))
    if points:   # the cubemap resource repeats the scenario's cubemap points (as stock maps do)
        extra["cubemap"] = extra.get("cubemap", []) + cube
    for res, body in extra.items():
        if res == "scenario":
            scenario += body
            continue
        field = RESOURCE_FIELDS[res]
        scenario.append(f"set\tscenario resources[0]/new split resources[0]/{field}\t"
                        f"{p.resources},scenario_{res}_resource")
        taken[res] = body
    scenario = [l for l in scenario if not any(
        l == f"set\tscenario resources[0]/new split resources[0]/{RESOURCE_FIELDS[r]}\t" for r in taken)]
    for res, body in taken.items():
        lines += [f"load\t{p.base.resources}\tscenario_{res}_resource", *body,
                  f"saveas\t{p.resources}\tscenario_{res}_resource"]
    lines = m.tag_script(plan) + lines
    out = []
    edited = False
    for line in lines:
        out.append(line)
        cmd = line.split("\t")
        if cmd[0] == "load" and cmd[2] == "scenario" and not edited:   # once: scenario.bake_mirror loads it again
            out += scenario
            edited = True
        elif cmd[0] == "load" and cmd[2].startswith("scenario_") and cmd[2].endswith("_resource"):
            res = cmd[2][len("scenario_"):-len("_resource")]
            out += resources.get(res, [])
    return m.finish_script(sc.number_mv(out, sc.base_scenario_xml())), counts


def _numbered(lines):
    """[(index of the block element the line is about, line)]: each "add" starts the next."""
    out, k = [], -1
    for line in lines:
        if line.startswith("add\t"):
            k += 1
        out.append((max(k, 0), line))
    return out


# -- reusing the last bake ------------------------------------------------------------

def baked_objects(plan, skip=()):
    """Digest of the placements the bake lights (BAKED_KINDS): tag, position, angles;
    placements of the tags in `skip` left out. A placement turned after the bake on the
    spot (its lighting is sampled where it stands) carries the yaw the bake saw as
    `baked_yaw`, and the digest uses that, so --reuse-light can keep the bake. A placement
    moved after the bake (a teleporter pad settled onto the ground) carries `baked_position`
    the same way."""
    skip = {t.lower() for t in skip}
    rows = sorted((p.resolve()[0], p.resolve()[1], *(round(c, 2) for c in getattr(p, "baked_position", p.position)),
                   round(getattr(p, "baked_yaw", p.yaw), 1), round(p.pitch, 1), round(p.roll, 1))
                  for p in plan.items if p.resolve()[0] in BAKED_KINDS and (p.resolve()[1] or "").lower() not in skip)
    return hashlib.sha256(json.dumps(rows).encode()).hexdigest(), len(rows)


def file_digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_stamp():
    path = active().light_stamp
    return json.loads(path.read_text()) if path.exists() else None


def level_unchanged(m, stamp):
    """Regenerate the level into a scratch .ASS (the real one stays as baked): does
    it match the bake's?"""
    real = active().ass_path
    scratch = real.with_name(real.stem + "_reuse_check.ASS")
    try:
        m.write_level(scratch)
        return file_digest(scratch) == stamp["geometry"]
    finally:
        scratch.unlink(missing_ok=True)


def objects_unchanged(m, plan, stamp):
    """(ok, message): do the placements the bake lights match the bake's?"""
    baked = baked_objects(plan)
    if baked[0] == stamp["objects"]:
        return True, "the bake's scenery and crates are unchanged"
    # a stamp records its objects without the late ones too ("early_objects"): the late ones may change
    if m.late_tags and baked_objects(plan, skip=m.late_tags)[0] in (stamp["objects"], stamp.get("early_objects")):
        return True, ("the bake's scenery and crates are unchanged; the late crates come after "
                      "them and are lit like vehicles")
    return False, (f"scenery or crates differ from the bake's ({baked[1]} now, {stamp['object_count']} baked); "
                   "the bake lights them, so run a full build")


# -- the build ------------------------------------------------------------------------

class Builder:
    def __init__(self, m):
        self.m = m
        self.p = active()

    def compile_level(self, stamp):
        p = self.p
        self.compile_design()     # no part of the bake: a reuse build recompiles it too
        if stamp:
            if not level_unchanged(self.m, stamp):
                sys.exit("--reuse-light: the level geometry or its lights changed since the last bake; "
                         "run a full build")
            print("level unchanged since the bake: reusing its lighting")
            return
        self.m.write_level(p.ass_path)
        pre = self.m.pre_structure_lines()
        if pre:
            ek.mbedit(pre, "pre_structure.txt")
        if not p.bsp_tag.exists() or p.bsp_tag.stat().st_mtime < p.ass_path.stat().st_mtime:
            rel = f"{p.bsp_dir}\\structure\\{p.bsp_name}.ASS"
            before = p.bsp_tag.stat().st_mtime if p.bsp_tag.exists() else None
            code, tail = ek.tool("structure", rel, log="structure.log")
            # tool exits 0 when an instance's import fails, and the last good tag stays:
            # only a newly written tag means the level compiled
            if code or not p.bsp_tag.exists() or p.bsp_tag.stat().st_mtime == before:
                sys.exit("tool structure failed (no new structure bsp):\n" + "\n".join(tail))
            print("structure compiled:", p.bsp)

    def compile_design(self):
        """The structure design (soft ceilings, water), if the map has one: tool structure-design."""
        from . import design
        d = design.Design()
        if self.m.design(d) is False:
            return
        path = design_ass()
        d.write(path, header=self.p.ass_header)
        tag = (EK / "tags" / Path(*design_tag().split("\\"))).with_suffix(".structure_design")
        before = tag.stat().st_mtime if tag.exists() else None
        rel = str(path.relative_to(EK / "data")).replace("/", "\\")
        code, tail = ek.tool("structure-design", rel, log="structure_design.log")
        if code or not tag.exists() or tag.stat().st_mtime == before:
            sys.exit("tool structure-design failed:\n" + "\n".join(tail))
        print("structure design compiled:", design_tag())

    def layout(self, stamp=None):
        """(terrain, plan) on the compiled level; exits if a reuse build can't keep the bake."""
        p = self.p
        terrain = self.m.terrain()
        col = load_collision(p.collision_dump) if p.collision_dump.exists() else None
        plan = self.m.plan(terrain, col)   # spawns and pads checked for standing room
        for stage, msg in getattr(plan, "problems", []):   # a map's layout may collect them
            print(f"layout problem [{stage}]: {msg}")
        if col is not None:
            blocked = blocked_teleporters(plan, col)
            if blocked:
                print("WARNING: teleporters with no standing room (the game says 'teleporter blocked'):")
                for b in blocked:
                    print("   ", b)
        print(f"plan: {len(plan.items)} objects {plan.kind_counts()}")
        if stamp:
            ok, msg = objects_unchanged(self.m, plan, stamp)
            if not ok:
                sys.exit("--reuse-light: " + msg)
            print("--reuse-light:", msg)
        return terrain, plan

    def bake(self, quality, plan):
        p = self.p
        code, tail = ek.bake(p.scenario, p.bsp_name, quality, job=p.light_job)
        if code:
            sys.exit("lightmapping failed:\n" + "\n".join(tail))
        print("lit:", quality)
        baked = baked_objects(plan)
        early = baked_objects(plan, skip=self.m.late_tags)
        p.light_stamp.write_text(json.dumps({"quality": quality, "geometry": file_digest(p.ass_path),
                                             "objects": baked[0], "object_count": baked[1],
                                             "early_objects": early[0], "early_object_count": early[1]},
                                            indent=1))

    def build_map(self, counts):
        p = self.p
        code, tail = ek.tool("build-cache-file", p.scenario, "pc", log="build.log")
        # the tool's own object pool overflows (see object_memory.py) and it dumps a
        # report into the kit's root on every failed object: hundreds of files
        dumps = list(EK.glob(f"{p.name}_object_memory*.txt"))
        for f in dumps:
            f.unlink()
        print(f"build tool object pool: {len(dumps)} overflow reports (removed)")
        if code or not any("successfully built" in t for t in tail):
            sys.exit("build failed:\n" + "\n".join(tail))
        placed = sc.built_counts(p.built_map)
        print("placements in the built map:", placed)
        short = {b: (placed.get(b), n) for b, n in counts.items() if b in placed and placed[b] < n}
        if short:
            sys.exit(f"the build dropped placements (built, expected): {short}")
        extra = {b: (placed[b], counts.get(b, 0)) for b in sc.MIRRORED_BLOCKS if placed.get(b, 0) > counts.get(b, 0)}
        if extra:   # the scenario's own copies (scenario.bake_mirror) placed as well as the resources'
            sys.exit(f"the build placed more than planned (built, expected): {extra}")
        for d in p.donors:
            d.port(p.built_map, p.package_dir)
        p.package_map.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p.built_map, p.package_map)
        print(f"built {p.built_map.stat().st_size / 2**20:.0f} MB -> {p.package_map}")

    def run(self, quality="draft", reuse_light=False, no_build=False):
        p = self.p
        stamp = None
        if reuse_light:
            stamp = read_stamp()
            if not stamp:
                sys.exit(f"--reuse-light: no {p.light_stamp.name} (no bake recorded); run a full build")
            quality = stamp["quality"]
        lights.QUALITY = quality   # lights are scaled down where the bake adds bounce light
        self.compile_level(stamp)
        ek.mbedit([f"bspdump\t{p.bsp}\twork\\{p.collision_dump.name}"], "bspdump.txt")
        terrain, plan = self.layout(stamp)
        lines, counts = script(self.m, plan, terrain, reuse_light=bool(stamp))
        ek.mbedit(lines, f"{p.name}.txt")
        print(f"scenario saved ({len(lines)} commands):", p.scenario)
        if stamp:
            print("lighting: reused from the last bake")
        elif quality != "none":
            self.bake(quality, plan)
        if not no_build:
            self.build_map(counts)

    def plan_only(self, script_out=None):
        """The layout and the scenario script on the level as last compiled, without
        touching the kit's tags; says whether a reuse build would keep the bake."""
        stamp = read_stamp()
        if stamp:
            lights.QUALITY = stamp["quality"]
        terrain, plan = self.layout()
        try:
            print(object_memory.report(plan))
        except FileNotFoundError as e:   # a model new since the last build has no tag yet
            print(f"object memory: not estimated ({e}; a full build makes it)")
        if script_out:
            lines, _ = script(self.m, plan, terrain, reuse_light=bool(stamp))
            script_out.write_text("\n".join(lines) + "\n", encoding="utf-8")
            print(f"script ({len(lines)} commands): {script_out}")
        if not stamp:
            print("reuse: no bake recorded; the next build must be a full one")
            return
        ok, msg = objects_unchanged(self.m, plan, stamp)
        same = level_unchanged(self.m, stamp)
        print("reuse: level", "unchanged" if same else "CHANGED (run a full build)", "|", msg)


def main(m, argv=None, description=None):
    """The build's command line for map `m`."""
    p = active()
    ap = argparse.ArgumentParser(description=description or f"Build {p.name} with the Halo 3 Editing Kit.")
    ap.add_argument("--light", default="draft", choices=QUALITIES,
                    help="light bake quality (none: no bake); medium for a release")
    ap.add_argument("--no-build", action="store_true", help="stop before build-cache-file")
    ap.add_argument("--reuse-light", action="store_true",
                    help="keep the level and the last bake's lighting; only objects change")
    ap.add_argument("--plan-only", action="store_true",
                    help="lay out and script without touching the kit; check whether --reuse-light would work")
    ap.add_argument("--script-out", type=Path,
                    help="with --plan-only: write the mbedit script here")
    args = ap.parse_args(argv)
    b = Builder(m)
    if args.plan_only:
        b.plan_only(args.script_out)
    else:
        b.run(args.light, args.reuse_light, args.no_build)

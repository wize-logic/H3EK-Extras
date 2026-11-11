"""Placements and the scenario edit.

A layout is a Plan: a list of Placements (a stock piece, a vehicle, weapon or
equipment by name, or any object tag as a "prop") standing on a terrain.
script() turns a Plan into mbedit commands that copy the base map's scenario
and its split resource tags into the project's own and fill their placement
blocks and palettes.

The base map keeps its placements and trigger volumes in split resource tags
beside the scenario, and build-cache-file reads them from there: the copies
in the scenario tag itself are ignored. The new map gets its own copies.

A terrain is anything with height(x, y, r) (highest ground within r, or
None), ground(x, y) and slope(x, y).
"""

import math
import random
import re
from dataclasses import dataclass

from . import cache as h3cache
from . import ek, machines, stock
from .project import active
from .stock import (EQUIPMENT, GAMEPLAY, MUST, NEUTRAL, PIECES, PRIORITY, SCENERY,  # noqa: F401
                    VEHICLE, VEHICLE_REST, VEHICLES, WEAPONS, vehicle_z)

# resource (scenario_<name>_resource): the scenario's split resource field
SPLIT = {
    "scenery": "scenery resource",
    "vehicles": "vehicle resource",
    "weapons": "weapon resource",
    "equipment": "equipment resource",
    "trigger_volumes": "trigger volume resource",
    "devices": "device resource",   # machines (static props that take no map-variant slot)
}

# block, palette block, object type, tag extension, resource
KINDS = {
    "scenery": ("scenerys", "scenery palette", "scenery", "scenery", "scenery"),
    "crate": ("crates", "crate palette", "crate", "crate", "scenery"),
    "vehicle": ("vehicles", "vehicle palette", "vehicle", "vehicle", "vehicles"),
    "weapon": ("weapons", "weapon palette", "weapon", "weapon", "weapons"),
    "equipment": ("equipments", "equipment palette", "equipment", "equipment", "equipment"),
    "machine": ("machines", "machine palette", "machine", "device_machine", "devices"),
}
# the five object types that take a map-variant slot (halo3 FUN_1403f6dd0, type mask 0x44e)
VARIANT_KINDS = ("scenery", "crate", "vehicle", "weapon", "equipment")
# Plan.prop places static scenery/crate props (priority >= SCENERY) as machines (machines.py)
CONVERT_TO_MACHINES = True
UNIQUE_ID_SEED = 470        # seeds the placements' object unique ids


# multiplayer data/game engine flags: an object with any set appears only in those game types (as
# Isolation's oddball spawn crates, 0x4); 0 (the default) means every game type
ENGINE = {"ctf": 0x1, "slayer": 0x2, "oddball": 0x4, "king": 0x8, "juggernaut": 0x10, "territories": 0x20,
          "assault": 0x40, "vip": 0x80, "infection": 0x100, "target training": 0x200}
NOT_INFECTION = 0x3ff & ~ENGINE["infection"]


@dataclass
class Placement:
    piece: str          # key of PIECES, or "vehicle:<name>", "weapon:<name>", "equipment:<name>", or "prop"
    position: tuple
    yaw: float = 0.0    # degrees
    pitch: float = 0.0  # degrees, positive lifts the piece's +x end
    team: str = NEUTRAL
    spawn_time: int = 0
    channel: int = -1
    boundary: tuple = None  # (shape, width/radius, box length, +height, -height)
    flags: int = 0x20       # create at rest
    roll: float = 0.0       # degrees
    priority: int = None    # MUST..VEHICLE; None: from the piece (see PRIORITY)
    tag: str = None         # piece "prop": the object tag path (no extension)
    kind: str = None        # piece "prop": a KINDS key
    spawn_order: int = 0    # KOTH hills: the order a moving hill visits them
    games: int = 0          # game engine flags: 0 = every game type; else only the set ones (ENGINE bits)

    def __post_init__(self):
        if self.priority is None:
            k = self.piece.split(":")[0]
            self.priority = PRIORITY.get(self.piece, VEHICLE if k == "vehicle" else
                                         GAMEPLAY if k in ("weapon", "equipment") else SCENERY)

    def resolve(self):
        """(kind, tag path) of what this placement creates."""
        if self.tag:
            return self.kind, self.tag
        if ":" in self.piece:
            kind, name = self.piece.split(":")
            tag = {"vehicle": VEHICLES, "weapon": WEAPONS}.get(kind, {}).get(name)
            tag = tag[0] if isinstance(tag, tuple) else (tag or EQUIPMENT[name])
            return kind, tag
        return PIECES[self.piece]


class Plan:
    """A layout: placements on a terrain, with helpers that stand each kind
    of object on the ground."""

    def __init__(self, terrain, seed=None):
        self.t = terrain
        self.items = []
        self.rng = random.Random(active().map_id if seed is None else seed)

    # -- ground --------------------------------------------------------------

    def z(self, x, y):
        h = self.t.height(x, y, 1.0)
        if h is None:
            raise ValueError(f"no ground at ({x:.1f}, {y:.1f})")
        return h

    def base(self, x, y, half_x, half_y, yaw=0.0):
        """Lowest ground under a footprint, so the piece never shows a gap."""
        c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
        hs = [self.z(x + c * a - s * b, y + s * a + c * b)
              for a in (-half_x, 0, half_x) for b in (-half_y, 0, half_y)]
        return min(hs) - 0.05

    # -- placing -------------------------------------------------------------

    def put(self, piece, x, y, z=None, yaw=0.0, half=(0.5, 0.5), **kw):
        z = self.base(x, y, half[0], half[1], yaw) if z is None else z
        self.items.append(Placement(piece, (x, y, z), yaw, **kw))

    def vehicle(self, name, x, y, yaw=0.0, team=NEUTRAL):
        _, hl, hw = VEHICLE_REST.get(name, (0.05, 1.0, 1.0))
        c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
        # on the highest ground under it, so it doesn't sink; a fixed turret with a
        # pedestal (stock.SUNK) on the lowest, its base buried in the rest
        pick = min if name in stock.SUNK else max
        top = pick(self.z(x + c * a - s * b, y + s * a + c * b) for a in (-hl, 0, hl) for b in (-hw, 0, hw))
        self.items.append(Placement("vehicle:" + name, (x, y, vehicle_z(name, top)), yaw, team=team,
                                    spawn_time=VEHICLES[name][1], flags=0))

    def weapon(self, name, x, y, z=None, team=NEUTRAL):
        z = self.z(x, y) + 0.15 if z is None else z
        self.items.append(Placement("weapon:" + name, (x, y, z), team=team, spawn_time=WEAPONS[name][1], flags=0))

    def equipment(self, name, x, y, z=None):
        z = self.z(x, y) + 0.15 if z is None else z
        self.items.append(Placement("equipment:" + name, (x, y, z), spawn_time=60, flags=0))

    def spawn(self, x, y, team, yaw, initial=False):
        """A respawn point, or with `initial` a start point for every game type (stock.INITIAL_PIECES)."""
        for piece in (stock.INITIAL_PIECES if initial else ("respawn",)):
            self.items.append(Placement(piece, (x, y, self.z(x, y) + 0.05), yaw, team=team, flags=0))

    def teleporter(self, x, y, z, channel, yaw=0.0):
        # stock Avalanche pads: placement flags 0 (not "create at rest"), neutral team
        self.items.append(Placement("teleporter", (x, y, z), yaw, channel=channel, flags=0))

    def prop(self, tag, x, y, z=None, yaw=0.0, pitch=0.0, kind="scenery", roll=0.0, priority=SCENERY,
             team=NEUTRAL, flags=None):
        """Place any object tag (path without extension) of a KINDS kind; its
        palette entry is added on demand. z=None stands it on the ground.
        Returns the Placement (callers may set spawn_time, channel...)."""
        if kind not in KINDS:
            raise ValueError(f"prop {tag}: kind {kind!r} is not one of {list(KINDS)}")
        tag = tag.replace("/", "\\")
        ext = KINDS[kind][3]
        if not ek.tag_exists(tag, ext):
            raise ValueError(f"prop: no tag {tag}.{ext} under {ek.EK / 'tags'}")
        if (CONVERT_TO_MACHINES and kind in ("scenery", "crate") and priority >= SCENERY
                and self.machine_count() < machines.max_machines()):
            new = machines.machine_for(tag, kind)
            if new:   # same model, never moves, no variant slot; created by machines.tag_script()
                tag, kind = new, "machine"
                flags = 0 if flags is None else flags
        if z is None:
            z = self.z(x, y)
        if flags is None:
            flags = 0x20 if kind in ("scenery", "crate") else 0
        p = Placement("prop", (x, y, z), yaw, pitch, team=team, flags=flags, roll=roll, priority=priority,
                      tag=tag, kind=kind)
        self.items.append(p)
        return p

    def machine_count(self):
        return sum(1 for p in self.items if p.kind == "machine")

    def variant_count(self):
        """Placements that take one of the map variant's 640 slots."""
        return sum(1 for p in self.items if p.resolve()[0] in VARIANT_KINDS)

    def kind_counts(self):
        """{kind: placements}."""
        kinds = {}
        for p in self.items:
            kinds[p.resolve()[0]] = kinds.get(p.resolve()[0], 0) + 1
        return kinds

    def ramp(self, a, b, lanes=3, grade_limit=0.6):
        """Wood bridges laid edge to edge from the ground at a (2D) up to the
        surface at b: a drivable road, `lanes` bridges wide."""
        z0 = self.t.ground(*a)
        z1 = self.z(*b)
        dx, dy = b[0] - a[0], b[1] - a[1]
        run = math.hypot(dx, dy)
        grade = (z1 - z0) / run
        if abs(grade) > grade_limit:
            raise ValueError(f"ramp {a} -> {b} climbs {grade:.2f}")
        yaw = math.degrees(math.atan2(dy, dx))
        pitch = math.degrees(math.atan(grade))
        slope = math.hypot(run, z1 - z0)
        ux, uy = dx / run, dy / run
        lx, ly = -uy, ux
        n = math.ceil(slope / 4.1)
        for k in range(n):
            s = min(slope - 2.17, 2.17 + k * 4.1) / slope  # piece centre along the road
            cx, cy, cz = a[0] + dx * s, a[1] + dy * s, z0 + (z1 - z0) * s
            for lane in range(lanes):
                o = (lane - (lanes - 1) / 2) * 1.8
                self.items.append(Placement("bridge", (cx + lx * o, cy + ly * o, cz), yaw, pitch))
        return grade

    def build(self):
        """Fill self.items; returns self."""
        raise NotImplementedError


# -- the scenario edit ----------------------------------------------------------

def stock_state(retire_pads=()):
    """Palettes, block sizes and stock objects to keep out of play, read from the
    base map's resources: (palettes, counts, retire). `retire` lists the CTF flag
    crates and the respawn points within 0.5 of any of `retire_pads` (x, y)."""
    base = active().base
    xml = {res: ek.export_xml(base.resources, f"scenario_{res}_resource", f"res_{res}.xml")
           for res in sorted({k[4] for k in KINDS.values()})}

    def block(res, name):
        m = re.search(r'<block name="%s" value="[^,"]*,(\d+)">(.*?)\n    </block>' % re.escape(name), xml[res], re.S)
        return int(m.group(1)), (m.group(2) if m else "")

    palettes, counts = {}, {}
    for kind, (blk, pal, _, ext, res) in KINDS.items():
        counts[blk], _ = block(res, blk)
        _, body = block(res, pal)
        palettes[pal] = [r.split(",")[0] for r in re.findall(r'name="name" value="([^"]+)" type="tag reference"', body)]
    retire = []
    crate_pal = palettes["crate palette"]
    flag_types = {crate_pal.index(t) for t in (PIECES["flag"][1], PIECES["flag_return"][1]) if t in crate_pal}
    _, crates = block("scenery", "crates")
    for i, el in enumerate(re.split(r'\n        <element index=', crates)[1:]):
        t = int(re.search(r'name="type" value="[^,]*,(-?\d+)"', el).group(1))
        if t in flag_types:
            retire.append(("crates", i))
    _, scenery = block("scenery", "scenerys")
    respawn = palettes["scenery palette"].index(PIECES["respawn"][1])
    for i, el in enumerate(re.split(r'\n        <element index=', scenery)[1:]):
        t = int(re.search(r'name="type" value="[^,]*,(-?\d+)"', el).group(1))
        pos = [float(v) for v in re.search(r'name="position" value="([^"]+)"', el).group(1).split(",")]
        if t == respawn and any(abs(pos[0] - p[0]) < 0.5 and abs(pos[1] - p[1]) < 0.5 for p in retire_pads):
            retire.append(("scenerys", i))
    return palettes, counts, retire


def forge_vehicles():
    """Vehicles given a Forge (map variant) palette entry, so they respawn: the
    project's stock ones, then every donor's."""
    p = active()
    return [*p.forge_vehicles, *(k for d in p.donors for k in d.vehicles)]


def script(plan, palettes, counts, retire):
    """mbedit commands: the scenario first, then each resource copy."""
    p_ = active()
    rng = random.Random(UNIQUE_ID_SEED)
    # (the structure design reference is build.new_level_edits()'s: the map's own design, or none)
    lines = [f"load\t{p_.base.scenario}\tscenario", f"set\tmap id\t{p_.map_id}"]
    for res, field_name in SPLIT.items():
        lines.append(f"set\tscenario resources[0]/new split resources[0]/{field_name}\t{p_.resources},scenario_{res}_resource")
    main_lines = lines
    res_lines = {res: [] for res in SPLIT}
    for i, name in p_.base.retired_volumes.items():
        res_lines["trigger_volumes"].append(f"set\ttrigger volumes[{i}]/name\t{name}")
    for blk, i in retire:
        res_lines["scenery"].append(f"set\t{blk}[{i}]/object data/placement flags\t0x8")  # never placed

    def palette_index(kind, tag):
        _, pal, _, ext, res = KINDS[kind]
        entries = palettes[pal]
        if tag not in entries:
            entries.append(tag)
            res_lines[res].append(f"add\t{pal}")
            res_lines[res].append(f"set\t{pal}[{len(entries) - 1}]/name\t{tag},{ext}")
        return entries.index(tag)

    # forge (map variant) palette entries, so new vehicles and weapons respawn
    for name in forge_vehicles():
        tag, _, display = VEHICLES[name]
        lines += ["add\tmv vehicle palette"]
        lines += [f"set\tmv vehicle palette[{{mvv}}]/name\t{tag},vehicle",
                  f"set\tmv vehicle palette[{{mvv}}]/display_name\t{display}",
                  "set\tmv vehicle palette[{mvv}]/maximum allowed\t32",
                  "set\tmv vehicle palette[{mvv}]/price per instance\t10"]
    for name in p_.forge_weapons:
        tag, _ = WEAPONS[name]
        lines += ["add\tmv weapon palette"]
        lines += [f"set\tmv weapon palette[{{mvw}}]/name\t{tag},weapon",
                  f"set\tmv weapon palette[{{mvw}}]/display_name\t{name}",
                  "set\tmv weapon palette[{mvw}]/maximum allowed\t32",
                  "set\tmv weapon palette[{mvw}]/price per instance\t10"]

    for p in plan.items:
        kind, tag = p.resolve()
        blk, _, obj_type, _, res = KINDS[kind]
        t = palette_index(kind, tag)
        i = counts[blk]
        counts[blk] += 1
        e = f"{blk}[{i}]"
        lines = res_lines[res]
        lines += [f"add\t{blk}",
                  f"set\t{e}/type\t{t}",
                  f"set\t{e}/name\t-1",
                  f"set\t{e}/object data/placement flags\t{p.flags}",
                  f"set\t{e}/object data/position\t{p.position[0]:.4f},{p.position[1]:.4f},{p.position[2]:.4f}",
                  f"set\t{e}/object data/rotation\t{p.yaw:.3f},{p.pitch:.3f},{p.roll:.3f}",
                  f"set\t{e}/object data/object id/unique id\t{rng.randint(1, 2**31 - 1)}",
                  f"set\t{e}/object data/object id/origin bsp index\t{0 if kind in ('scenery', 'machine') else -1}",
                  f"set\t{e}/object data/object id/type\t{obj_type}",
                  f"set\t{e}/object data/object id/source\teditor",
                  f"set\t{e}/object data/editor folder\t-1",
                  # without a BSP to attach to, build-cache-file drops the object
                  f"set\t{e}/object data/can attach to bsp flags\t1"]
        if kind == "machine":
            # as stock MP maps place static machines: no power or position group, never moves
            lines += [f"set\t{e}/device data/power group\t-1",
                      f"set\t{e}/device data/position group\t-1",
                      f"set\t{e}/device data/flags\t0",
                      f"set\t{e}/machine data/flags\t0"]
            continue
        lines.append(f"set\t{e}/multiplayer data/owner team\t{p.team}")
        if p.spawn_time:
            lines.append(f"set\t{e}/multiplayer data/spawn time\t{p.spawn_time}")
        if p.channel >= 0:
            lines.append(f"set\t{e}/multiplayer data/teleporter channel\t{p.channel}")
        if p.spawn_order:
            lines.append(f"set\t{e}/multiplayer data/spawn order\t{p.spawn_order}")
        if p.games:
            lines.append(f"set\t{e}/multiplayer data/game engine flags\t{p.games}")
        if p.boundary:
            shape, w, length, up, down = p.boundary
            lines += [f"set\t{e}/multiplayer data/boundary shape\t{shape}",
                      f"set\t{e}/multiplayer data/boundary width or radius\t{w}",
                      f"set\t{e}/multiplayer data/boundary box length\t{length}",
                      f"set\t{e}/multiplayer data/boundary positive height\t{up}",
                      f"set\t{e}/multiplayer data/boundary negative height\t{down}"]
    out = main_lines + [f"saveas\t{p_.scenario}\tscenario"]
    for res, body in res_lines.items():
        out += [f"load\t{p_.base.resources}\tscenario_{res}_resource", *body,
                f"saveas\t{p_.resources}\tscenario_{res}_resource"]
    return out + bake_mirror()


# The light bake (faux) reads the placements in the scenario tag's own blocks, never the split resources the
# game places from (a bake lit the base map's stale scenery copies and none of the new machines, scenery or
# crates; device machine probes 0, so every prop took a fallback light and ignored the level's).
# So the scenario's own blocks get a copy of the resources' (same unique ids: the probes
# are found by object id); build-cache-file still reads the resources (a duplicate would show in built_counts).
BAKE_MIRROR = (("scenery", "scenery palette", "scenery palette"), ("scenery", "scenerys", "scenery"),
               ("scenery", "crate palette", "crate palette"), ("scenery", "crates", "crates"),
               ("devices", "machine palette", "machine palette"), ("devices", "machines", "machines"))
MIRRORED_BLOCKS = ("scenerys", "crates", "machines")    # built_counts' names of the mirrored blocks


def bake_mirror():
    """mbedit lines: the resources' scenery, crates and machines (with their palettes) copied into the
    scenario's own blocks, for the bake."""
    p_ = active()
    lines = [f"load\t{p_.scenario}\tscenario"]
    for res, src, dst in BAKE_MIRROR:
        lines.append(f"copyfrom\t{p_.resources}\tscenario_{res}_resource\t{src}\t{dst}")
    return lines + ["save"]


def number_mv(lines, xml):
    """Fill in the indices of the Forge palette entries script() adds."""
    mvv, mvw = mv_counts(xml)
    out = []
    for line in lines:
        if "{mvv}" in line or line == "add\tmv vehicle palette":
            if line == "add\tmv vehicle palette":
                current = mvv
                mvv += 1
            line = line.replace("{mvv}", str(current))
        elif "{mvw}" in line or line == "add\tmv weapon palette":
            if line == "add\tmv weapon palette":
                current = mvw
                mvw += 1
            line = line.replace("{mvw}", str(current))
        out.append(line)
    return out


def mv_counts(xml):
    def count(name):
        return int(re.search(r'<block name="%s" value="[^,"]*,(\d+)"' % re.escape(name), xml).group(1))
    return count("mv vehicle palette"), count("mv weapon palette")


def base_scenario_xml():
    """The base map's scenario as XML (for number_mv)."""
    base = active().base
    return ek.export_xml(base.scenario, "scenario", base.xml_name)


# scnr placement block offsets in a built cache (Assembly's Halo3MCC plugin)
SCNR_BLOCKS = (("scenerys", 0xB4), ("vehicles", 0xE4), ("equipments", 0xFC),
               ("weapons", 0x114), ("machines", 0x138), ("crates", 0x5BC))


def built_counts(path):
    """Placement block sizes in a built cache's scenario."""
    cache = h3cache.Cache(str(path))
    scnr = next(t for t in cache.tags if t and t.group == "scnr")
    out = {blk: cache.block(scnr.offset, off)[0] for blk, off in SCNR_BLOCKS}
    cache.close()
    return out

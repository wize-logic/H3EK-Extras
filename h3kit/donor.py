"""Vehicles (and crates) taken from another built map: a donor.

Some vehicles exist only compiled into another mod's .map, with no source tags
for the Editing Kit (a Lich, a Longsword, a Vulture...). They come over
as compiled tags, in two halves:

  1. tag_script(): a placeholder per donor vehicle (a copy of a stock vehicle
     under the project's objects\\...\\<donor key>), so the layout, the Forge
     palette and the placements go through the normal H3EK build;
  2. port(map) after build-cache-file, with tools/hgport (Assembly's Blamite):
       * the built map's tags in `replaced` (e.g. the player animation
         graphs) are renamed out of the way, so the donor's come over in
         their place (its graphs hold the seat animations its vehicles use);
       * each vehicle, crate and replaced tag is extracted from the donor with
         every tag, resource and sound entry it needs, stopping at tags the
         built map already has (by group and name: the injection reuses
         those), and injected;
       * every reference to a placeholder (the scenario's vehicle and Forge
         palettes) and to a renamed tag is pointed at the new tag;
       * checks: the injected tags are extracted again and compared with the
         donor's (data, references by name, resources by content), the
         palettes hold the real vehicles, physics materials are in range;
       * seat_fixes widen seats a player can't reach from the ground;
       * the donor's loose sound banks (halo3\\fmod\\pc, which its sounds play
         from) are copied into the package.

Resting heights, footprints and object-memory costs of the placeholders come
from the real vehicles in the donor's map (info(), cached in H3EK\\work).

Known limits: the injection copies the donor's whole shader pipeline under
unique names ("<name>_0x<datum>"), even where the built map has tags of the
same names (reusing the built map's same-named templates, compiled for it,
drew a donor's Seraphs white). Forge display names and "Hold X to pilot"
prompts are text in the donor's string lists, which aren't ported: blank.
"""

import json
import math
import shutil
import struct
import subprocess
from pathlib import Path

from . import cache as h3cache
from . import env, stock
from .project import active

HGPORT = env.WORK / "hgport" / "bin"          # tools/hgport/build.sh builds it here
WORK = env.WORK / "hgport" / "out"

# cache layout offsets (Assembly's Halo3MCC plugins)
OBJ_DEFAULT_VARIANT, OBJ_MODEL, OBJ_ATTACHMENTS, OBJ_CHANGE_COLORS, OBJ_MP = 0x30, 0x34, 0xBC, 0xD4, 0xE0
VEHI_WEAPONS, VEHI_FRICTION = 0x24C, 0x380
VEHI_SEATS, SEAT_SIZE, SEAT_INVALID_FOR_PLAYER = 0x258, 0xD4, 0x10000
SEAT_ENTRY = 0xBC                         # entry radius, then the cone and facing angles (radians)
HLMT_RENDER, HLMT_ANIMATION, HLMT_VARIANTS, HLMT_DAMAGE = 0x0, 0x20, 0x64, 0x88
MODE_REGIONS, MODE_NODES, MODE_COMPRESSION = 0xC, 0x30, 0x74
SCNR_VEHICLE_PALETTE, SCNR_MV_VEHICLE_PALETTE, SCNR_CRATE_PALETTE = 0xF0, 0x1E0, 0x5C8
MATG_MATERIALS, PHMO_NODE_EDGES, PHMO_MATERIALS = 0x464, 0x4C, 0x64
ZONE_RESOURCES = 0x64                     # elements 0x40, the owner tag reference first
GROUP_TYPE = {"vehi": "vehicle", "weap": "weapon", "eqip": "equipment", "scen": "scenery", "bloc": "crate",
              "bipd": "biped", "proj": "projectile", "mach": "machine", "gint": "giant"}

# the stock tags each placeholder copies
VEHICLE_PLACEHOLDER = "objects\\vehicles\\mongoose\\mongoose"
CRATE_PLACEHOLDER = "objects\\levels\\dlc\\sandbox\\sand_block\\sand_block"
# the player animation graphs: a donor that adds seat animations to them replaces these
PLAYER_GRAPHS = [("jmad", "objects\\characters\\masterchief\\masterchief"),
                 ("jmad", "objects\\characters\\elite\\elite")]


def _u32(c, off):
    return struct.unpack("<I", c.read(off, 4))[0]


def _ref(c, off):
    """The tag a tag reference at file offset off points to, or None."""
    return c.tag_by_datum(_u32(c, off + 12))


def _object(c, tag, variant="", depth=0):
    """[[tag path, type, counts]] of an object and the objects created with it (unit
    weapons, then the model variant's objects), as object_memory._walk; counts are
    object_memory.size_of's arguments after the type."""
    typ = GROUP_TYPE[tag.group]
    o = tag.offset
    nodes = regions = 1
    graph = False
    sections = None
    kids = []
    if tag.group == "vehi":
        n, f = c.block(o, VEHI_WEAPONS)
        kids += [(_ref(c, f + 0x10 * i), "") for i in range(n)]
    hl = _ref(c, o + OBJ_MODEL)
    if hl:
        mo = _ref(c, hl.offset + HLMT_RENDER)
        graph = _ref(c, hl.offset + HLMT_ANIMATION) is not None
        if mo:
            nodes = max(c.block(mo.offset, MODE_NODES)[0], 1)
            regions = max(c.block(mo.offset, MODE_REGIONS)[0], 1)
        n, f = c.block(hl.offset, HLMT_DAMAGE)
        if n:
            sections = c.block(f, 0x68)[0]
        n, f = c.block(hl.offset, HLMT_VARIANTS)
        variants = [(c.string(_u32(c, f + 0x30 * i)), f + 0x30 * i) for i in range(n)]
        want = (variant or c.string(_u32(c, o + OBJ_DEFAULT_VARIANT))).lower()
        pick = next((v for v in variants if v[0].lower() == want), variants[0] if variants else None)
        if pick:
            n, f = c.block(pick[1], 0x20)
            kids += [(_ref(c, f + 0x1C * j + 0xC), c.string(_u32(c, f + 0x1C * j + 0x8))) for j in range(n)]
    friction = c.block(o, VEHI_FRICTION)[0] if tag.group == "vehi" else 0
    counts = [c.block(o, OBJ_ATTACHMENTS)[0], sections, c.block(o, OBJ_CHANGE_COLORS)[0],
              nodes, regions, graph, c.block(o, OBJ_MP)[0], friction]
    out = [[tag.name, typ, counts]]
    if depth < 4:
        for kid, v in kids:
            if kid is not None and kid.group in GROUP_TYPE:
                out += _object(c, kid, v if not v.startswith("<sid") else "", depth + 1)
    return out


def _bounds(c, tag):
    """The render model's (x0, x1, y0, y1, z0, z1) from its compression bounds."""
    hl = _ref(c, tag.offset + OBJ_MODEL)
    mo = _ref(c, hl.offset + HLMT_RENDER)
    n, f = c.block(mo.offset, MODE_COMPRESSION)
    return struct.unpack("<6f", c.read(f + 4, 24))


def hgport(*args):
    """Run hgport.exe (from its own folder: it reads Formats\\ and Plugins\\ there); stdout lines."""
    exe = HGPORT / "hgport.exe"
    if not exe.exists():
        raise SystemExit(f"donor: {exe} is missing; run tools/hgport/build.sh")
    r = subprocess.run([str(exe), *args], cwd=HGPORT, capture_output=True, text=True)
    if r.returncode not in (0, 4):
        raise SystemExit(f"hgport {args[0]} failed ({r.returncode}):\n{(r.stderr or r.stdout)[-3000:]}")
    return r.stdout.splitlines(), r.returncode


def _datum(c, group, name):
    t = c.find(group, name)
    if t is None:
        raise SystemExit(f"donor: no {group} {name} in {c.path}")
    return t.datum


def retarget(path, pairs):
    """Point every tag reference (group, 8 zero bytes, datum) in the tag section at a
    new tag: pairs [(group, old datum, new datum)]. Returns the count per pair. The
    resource table's owner tags (the zone tag's resources) keep their owner: the old
    tag's resources still belong to it."""
    c = h3cache.Cache(str(path), writable=True)
    start, size = c.tag_section_offset, c.tag_section_size
    data = bytearray(c.read(start, size))
    zone = next(t for t in c.tags if t and t.group == "zone")
    n, first = c.block(zone.offset, ZONE_RESOURCES)
    owners = range(first - start, first - start + 0x40 * n) if n else range(0)
    counts = []
    for group, old, new in pairs:
        pat = group.encode("latin-1")[::-1] + bytes(8) + struct.pack("<I", old)
        rep = pat[:12] + struct.pack("<I", new)
        n = 0
        i = data.find(pat)
        while i >= 0:
            if i % 4 == 0 and not (i in owners and (i - owners.start) % 0x40 == 0):
                data[i:i + 16] = rep
                n += 1
            i = data.find(pat, i + 1)
        counts.append(n)
    c.write(start, bytes(data))
    c.close()
    return counts


def _palette(c, off):
    scnr = next(t for t in c.tags if t and t.group == "scnr")
    n, f = c.block(scnr.offset, off)
    size = 0x1C if off == SCNR_MV_VEHICLE_PALETTE else 0x10
    return [_ref(c, f + size * i) for i in range(n)]


def _check_materials(c, injected):
    """Problems with injected physics models' global materials: node edge indices past
    the globals' material list, named global materials the globals lack. (A collision
    model's materials are its own names, not global ones; an empty name means none.)"""
    matg = next(t for t in c.tags if t and t.group == "matg")
    n, f = c.block(matg.offset, MATG_MATERIALS)
    names = {c.string(_u32(c, f + 0x170 * i)) for i in range(n)}
    bad = []
    for t in injected:
        if t.group != "phmo":
            continue
        k, g = c.block(t.offset, PHMO_NODE_EDGES)
        for i in range(k):
            a, b = struct.unpack("<hh", c.read(g + 0x1C * i, 4))
            if a >= n or b >= n:
                bad.append(f"{t.name}: node edge material {max(a, b)} of {n}")
        k, g = c.block(t.offset, PHMO_MATERIALS)
        for i in range(k):
            m = c.string(_u32(c, g + 0xC * i + 4))
            if m and m not in names:
                bad.append(f"{t.name}: global material {m}")
    return bad


class Donor:
    """A built map to take vehicles and crates from.

    vehicles: {key: (donor vehicle tag, size class, spawn seconds, Forge display name)}
    crates: {key: donor crate tag}
    replaced: [(group, path)] tags of the built map replaced by the donor's
    seat_fixes: {vehicle key: entry radius}: every player seat widened to it, any approach
    sunk: vehicle keys whose model reaches below the origin (a turret's pedestal)
    sounds: the donor's loose FMOD banks (copied to the package's halo3\\fmod\\pc)
    """

    def __init__(self, key, map_path, vehicles, crates=None, replaced=(), seat_fixes=None, sunk=(),
                 sounds=None, renamed_suffix="_stock", workshop_id=None):
        self.key = key
        self.map_path = Path(map_path)
        self.vehicles = dict(vehicles)
        self.crates = dict(crates or {})
        self.replaced = list(replaced)
        self.seat_fixes = dict(seat_fixes or {})
        self.sunk = set(sunk)
        self.sounds = Path(sounds) if sounds else None
        self.renamed_suffix = renamed_suffix
        self.workshop_id = workshop_id

    # -- names -------------------------------------------------------------------
    @property
    def dir(self):
        """The placeholders' tag folder: objects\\...\\<key> in the project."""
        return active().tag_dir(self.key)

    @property
    def tags(self):
        return {key: f"{self.dir}\\{key}" for key in self.vehicles}

    @property
    def crate_tags(self):
        return {key: f"{self.dir}\\crate_{key}" for key in self.crates}

    @property
    def info_path(self):
        return env.WORK / f"{self.key}_info.json"

    @property
    def tagc(self):
        """The last port's tag container."""
        return WORK / f"{self.key}.tagc"

    @property
    def injected_list(self):
        """The tags the last port added ("group:path" lines)."""
        return WORK / f"{self.key}_injected.txt"

    def say(self, *args):
        print(f"{self.key}:", *args)

    # -- the build half ----------------------------------------------------------
    def register(self):
        """Add the vehicles to stock.VEHICLES (placed by their placeholders), with their
        resting heights, footprints and pedestals (stock.SUNK)."""
        tags = self.tags
        stock.VEHICLES.update({key: (tags[key], spawn, display)
                               for key, (_, _, spawn, display) in self.vehicles.items()})
        stock.VEHICLE_REST.update(self.rest())
        stock.VEHICLE_RADIUS.update(self.radius())
        stock.SUNK.update(self.sunk)

    def tag_script(self):
        """mbedit lines making the placeholders (run before the scenario edit)."""
        lines = []
        for key in self.vehicles:
            lines += [f"load\t{VEHICLE_PLACEHOLDER}\tvehicle", f"saveas\t{self.tags[key]}\tvehicle"]
        for key in self.crates:
            lines += [f"load\t{CRATE_PLACEHOLDER}\tcrate", f"saveas\t{self.crate_tags[key]}\tcrate"]
        return lines

    def info(self):
        """{key: {"rest": (origin height, half length, half width), "walk": [...], "radius": r}},
        cached in info_path until the donor's map changes."""
        st = self.map_path.stat()
        stamp = f"{st.st_size}:{int(st.st_mtime)}"
        try:
            cached = json.loads(self.info_path.read_text())
            if cached.get("stamp") == stamp and set(cached["vehicles"]) == set(self.vehicles):
                return cached["vehicles"]
        except (OSError, ValueError, KeyError):
            pass
        c = h3cache.Cache(str(self.map_path))
        out = {}
        for key, (path, *_rest) in self.vehicles.items():
            tag = c.find("vehi", path)
            if tag is None:
                raise SystemExit(f"{self.key}: {path} is not in {self.map_path}")
            x0, x1, y0, y1, z0, _ = _bounds(c, tag)
            hl, hw = max(-x0, x1), max(-y0, y1)
            out[key] = {"rest": [round(0.03 - z0, 2), round(hl, 1), round(hw, 1)],
                        "radius": round(max(hl, hw), 1),
                        "walk": _object(c, tag)}
        c.close()
        self.info_path.write_text(json.dumps({"stamp": stamp, "vehicles": out}, indent=1))
        return out

    def rest(self):
        """stock.VEHICLE_REST entries: (origin height above the surface at rest, half length, half width)."""
        return {key: tuple(v["rest"]) for key, v in self.info().items()}

    def radius(self):
        """Footprint radius per vehicle (half the longer side of the render model)."""
        return {key: v["radius"] for key, v in self.info().items()}

    def walk(self, tag):
        """object_memory._walk for a placeholder: [(tag, type, data size)] of the real
        vehicle's objects; None for any other tag."""
        from . import object_memory as om
        t = tag.replace("/", "\\").lower()
        if t in {p.lower() for p in self.crate_tags.values()}:   # a crate's placeholder: cost it as its source
            return om._walk(CRATE_PLACEHOLDER, "crate")
        for key, path in self.tags.items():
            if path.lower() == t:
                return [(name, typ, om.size_of(typ, *counts)) for name, typ, counts in self.info()[key]["walk"]]
        return None

    # -- the port ----------------------------------------------------------------
    def _roots(self):
        return ([f"vehi:{path}" for path, *_ in self.vehicles.values()] + [f"bloc:{path}" for path in self.crates.values()]
                + [f"{g}:{p}" for g, p in self.replaced])

    def port(self, built, package_dir):
        """Bring the vehicles into the built map (in place), check it (verify) and copy
        the donor's sound banks into the package."""
        WORK.mkdir(parents=True, exist_ok=True)
        before = h3cache.Cache(str(built))
        had = {(t.group, t.name) for t in before.tags if t}
        placeholders = {key: _datum(before, "vehi", self.tags[key]) for key in self.vehicles}
        crate_placeholders = {key: _datum(before, "bloc", self.crate_tags[key]) for key in self.crates}
        before.close()
        sfx = self.renamed_suffix
        for group, path in self.replaced:
            if (group, path + sfx) in had:
                raise SystemExit(f"{self.key}: {built} was already ported (it has {path}{sfx})")
        had |= {(group, path + sfx) for group, path in self.replaced}   # renamed, not injected

        bw = env.win(built)
        for group, path in self.replaced:
            hgport("rename", bw, f"{group}:{path}", path + sfx)
        out, _ = hgport("extract", env.win(self.map_path), env.win(self.tagc), env.MCC_MAPS_WIN,
                        "--existing", bw, *self._roots())
        self.say("; ".join(l for l in out if not l.startswith("group")))
        out, _ = hgport("inject", bw, env.win(self.tagc))
        self.say("; ".join(out))

        c = h3cache.Cache(str(built))
        pairs = [("vehi", placeholders[key], _datum(c, "vehi", path)) for key, (path, *_) in self.vehicles.items()]
        pairs += [("bloc", crate_placeholders[key], _datum(c, "bloc", path)) for key, path in self.crates.items()]
        pairs += [(group, _datum(c, group, path + sfx), _datum(c, group, path)) for group, path in self.replaced]
        self.injected_list.write_text(
            "\n".join(f"{t.group}:{t.name}" for t in c.tags if t and (t.group, t.name) not in had) + "\n")
        c.close()
        counts = retarget(built, pairs)
        names = list(self.vehicles) + [f"crate {k}" for k in self.crates] + [p for _, p in self.replaced]
        self.say("references retargeted: " + ", ".join(f"{n} {k}" for k, n in zip(names, counts)))
        if any(n == 0 for n in counts):
            raise SystemExit(f"{self.key}: a placeholder or replaced tag had no references to retarget")
        self.verify(built)
        self.fix_seats(built)

        if self.sounds:     # the donor's custom sounds play from loose banks beside the map
            dst = Path(package_dir) / "halo3" / "fmod" / "pc"
            dst.mkdir(parents=True, exist_ok=True)
            n = 0
            for f in self.sounds.iterdir():
                if f.is_file() and not f.name.endswith(".tmp"):
                    shutil.copyfile(f, dst / f.name)
                    n += 1
            self.say(f"{n} sound bank files -> {dst}")

    def _player_seats(self, c, key):
        t = c.find("vehi", self.vehicles[key][0])
        n, f = c.block(t.offset, VEHI_SEATS)
        return [f + SEAT_SIZE * i for i in range(n) if not _u32(c, f + SEAT_SIZE * i) & SEAT_INVALID_FOR_PLAYER]

    def fix_seats(self, built):
        """seat_fixes: widen the entry of every player seat of those vehicles (in place)."""
        if not self.seat_fixes:
            return
        c = h3cache.Cache(str(built), writable=True)
        for key, radius in self.seat_fixes.items():
            for e in self._player_seats(c, key):
                c.write(e + SEAT_ENTRY, struct.pack("<3f", radius, 2 * math.pi, 2 * math.pi))
        c.close()
        self.say("seat entries widened: " + ", ".join(f"{k} {r}" for k, r in self.seat_fixes.items()))

    def _seats_fixed(self, c):
        return bool(self.seat_fixes) and all(
            struct.unpack("<3f", c.read(e + SEAT_ENTRY, 12)) == struct.unpack("<3f", struct.pack(
                "<3f", radius, 2 * math.pi, 2 * math.pi))
            for key, radius in self.seat_fixes.items() for e in self._player_seats(c, key))

    def verify(self, built):
        """Check a ported map against the last port's container and list of injected
        tags: the palettes hold the real vehicles, physics materials exist, and the
        injected tags, extracted again, equal the donor's. Exits on a failure."""
        c = h3cache.Cache(str(built))
        real = {path.lower() for path, *_ in self.vehicles.values()}
        for label, off, want in (("vehicle palette", SCNR_VEHICLE_PALETTE, real),
                                 ("Forge vehicle palette", SCNR_MV_VEHICLE_PALETTE, real),
                                 ("crate palette", SCNR_CRATE_PALETTE, {p.lower() for p in self.crates.values()})):
            pal = [t.name.lower() for t in _palette(c, off) if t]
            left = [p for p in pal if p.startswith(self.dir.lower())]
            if left or not want <= set(pal):
                raise SystemExit(f"{self.key}: the {label} still has placeholders {left} "
                                 f"or lacks {sorted(want - set(pal))}")
        wanted = {tuple(line.split(":", 1)) for line in self.injected_list.read_text().splitlines() if line}
        injected = [t for t in c.tags if t and (t.group, t.name) in wanted]
        bad = _check_materials(c, injected)
        fixed = self._seats_fixed(c)
        c.close()
        for b in bad:
            self.say("WARNING material:", b)
        back = WORK / f"{self.key}_back.tagc"
        hgport("extract", env.win(built), env.win(back), env.MCC_MAPS_WIN, *self._roots())
        # the vehicles fix_seats() changed are checked for their fix instead (when it has run)
        patched = {("vehi", self.vehicles[k][0]) for k in self.seat_fixes} if fixed else set()
        names = WORK / f"{self.key}_compared.txt"
        names.write_text("".join(f"{g}:{p}\n" for g, p in sorted(wanted - patched)))
        out, code = hgport("compare", env.win(self.tagc), env.win(back), env.win(names))
        differ = [l for l in out if l.startswith("differs")]
        self.say(f"round trip of the {len(injected)} injected tags: {out[-1] if out else 'no output'}"
                 + (f"; seat fixes in place on {len(patched)}" if fixed else ""))
        if differ:
            raise SystemExit(f"{self.key}: injected tags differ from the donor's:\n" + "\n".join(differ[:20]))

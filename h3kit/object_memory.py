"""Object memory budget: how many bytes of Halo 3's object pool each placement uses.

Engine facts (tool_fast.exe and MCC halo3.dll alike; addresses from halo3_tag_test.exe):
  * objects_initialize (FUN_140a51950; tool_fast 0x140d3e1c1; halo3.dll 0x18033f5ab) makes
    the "object" datum array with 0x800 = 2048 entries and the "objects" memory pool with
    0x180000 = 1,572,864 bytes.  The same two constants are in halo3.dll, so the game has
    the same budget as the tool, and the bipeds, their weapons, projectiles, dropped weapons
    and grenades that exist at runtime use the same pool.
  * object_new (FUN_140a460a0) allocates the object's type struct (object type definition
    +0xc, TYPE_SIZE below) from the pool; if that fails it prints
    "OUT OF MEMORY: object_header_new failed".  Then it grows the same pool block with
    object_header_block_allocate (FUN_140a441b0), which adds size + (2^align - 1) bytes per
    non-empty block:
        attachments * 8 (align 2)        damage sections * 8 (align 1)
        change colors * 24 (align 2)     nodes * 52 (align 2)
        regions * 10 (align 2)           2 x nodes * 32 (align 4), animated types only
        animation 0xb0 + mixing board (biped 772, vehicle 496, giant 596) (align 3)
        multiplayer object 0x4c (align 2)
    and the type constructors add: motor 4*0x1c + mover (biped 240, vehicle/giant 24,
    creature 12) + 0x6c; unit 0x44 + 0x5c; biped 0x28; vehicle friction points * 0x2c
    (align 4).  The pool block is that data size + a 16-byte header, rounded up to 16
    (memory_pool FUN_14037eda0; tool_fast and halo3.dll create the pool without the
    debug header that halo3_tag_test.exe uses).
  * Child objects come along: every weapon in a unit's "weapons" block and every object in
    the model variant's "objects" block (warthog -> chaingun turret -> chaingun weapon).
  * When creation fails the tool writes H3EK\\<map>_object_memory<N>.txt (objects_dump_memory,
    FUN_140a50490).  Its "maxsize" column is the data size computed here; data_size()
    reproduces every definition in the last build's dumps exactly.

    cost(tag, kind)     -> pool bytes of one placement, children included
    objects(tag, kind)  -> how many objects (of the 2048) one placement creates
    plan_bytes(plan)    -> totals for a scenario.Plan
    report(plan)        -> those totals as text, against the tool's pool and the game's
    PLAYER_COST         -> one mp Spartan + two starting weapons (16 at runtime on MCC,
                           127 under Project Reclaimer)
    MCC_LEVEL_BUDGET    -> the level's share of the pool in game on stock MCC

Tag data is read from tool export-tag-to-xml (cached under work\\object_memory_xml) and
render model node/region counts from mbedit; results are cached in
work\\object_memory_cache.json (refreshed when a tag file changes). A donor
vehicle's placeholder (donor.py) costs what the real vehicle does, read from
the donor's map with the same formula (size_of).
"""

import json
import re

from . import ek, machines
from .env import EK, WORK
from .project import active
from .scenario import KINDS

POOL_BYTES = 0x180000          # 1,572,864
MAX_OBJECTS = 0x800            # 2048 object datums
BLOCK_HEADER = 16              # memory_pool block header (no debug header in tool_fast / halo3.dll)
# Project Reclaimer's client patches halo3.dll at load (reclaimer-client.exe FUN_14094daa0): the "objects"
# pool constant at rva 0x33f5e1 0x180000 -> 0xa00000 and the object datum count at rva 0x33f5b5 0x800 -> 0x2000.
# build-cache-file (tool_fast) keeps the stock sizes, so the tool is the tighter limit.
RECLAIMER_POOL_BYTES = 0xa00000      # 10,485,760
RECLAIMER_MAX_OBJECTS = 0x2000       # 8192
# a clean build: placements + stock objects must fit the tool's pool; keep 1% for rounding/fragmentation
TOOL_LEVEL_BUDGET = POOL_BYTES * 99 // 100
MCC_PLAYERS = 16
RECLAIMER_PLAYERS = 127
# in game under Reclaimer: the pool less 127 players and room for their bodies
# (about 10.6 KB each for 30 s), dropped weapons and projectiles
GAME_HEADROOM = 3_000_000
PLAYER_HEADROOM = GAME_HEADROOM // RECLAIMER_PLAYERS    # the same room per player on stock MCC

# object type struct sizes (object type definitions +0xc; identical in halo3_tag_test.exe and tool_fast.exe)
TYPE_SIZE = {"biped": 1744, "vehicle": 1952, "weapon": 648, "equipment": 396, "terminal": 668,
             "projectile": 504, "scenery": 364, "machine": 564, "control": 552, "sound_scenery": 376,
             "crate": 356, "creature": 572, "giant": 13928, "effect_scenery": 352}
EXT_TYPE = {"biped": "biped", "vehicle": "vehicle", "weapon": "weapon", "equipment": "equipment",
            "device_terminal": "terminal", "projectile": "projectile", "scenery": "scenery",
            "device_machine": "machine", "device_control": "control", "sound_scenery": "sound_scenery",
            "crate": "crate", "creature": "creature", "giant": "giant", "effect_scenery": "effect_scenery"}
GROUP_EXT = {"bipd": "biped", "vehi": "vehicle", "weap": "weapon", "eqip": "equipment", "scen": "scenery",
             "mach": "device_machine", "ctrl": "device_control", "bloc": "crate", "efsc": "effect_scenery",
             "ssce": "sound_scenery", "term": "device_terminal", "crea": "creature", "gint": "giant",
             "proj": "projectile"}
MOVER = {"biped": 240, "vehicle": 24, "giant": 24, "creature": 12}      # motor mover data size
MIXING_BOARD = {"biped": 772, "vehicle": 496, "giant": 596}
UNITS = ("biped", "vehicle", "giant")
ANIMATED = ("biped", "vehicle", "weapon", "equipment", "crate", "creature", "giant")  # get node matrices
DEVICES = ("machine", "control", "terminal")



def stock_objects():
    """Objects the base map's scenario still creates besides the plan's placements
    (the project's BaseMap.stock_objects: (tag, type, count))."""
    return active().base.stock_objects


# a player: the mp Spartan (globals player representation) and two starting weapons
PLAYER_BIPED = "objects\\characters\\masterchief\\mp_masterchief\\mp_masterchief"
PLAYER_WEAPONS = ["objects\\weapons\\rifle\\assault_rifle\\assault_rifle",
                  "objects\\weapons\\rifle\\battle_rifle\\battle_rifle"]

# order the tool creates scenario objects in (last build.log); children follow their parent
CREATION_ORDER = ["vehicle", "weapon", "equipment", "scenery", "machine", "sound_scenery", "crate", "effect_scenery"]

CACHE = WORK / "object_memory_cache.json"
_cache = None


def _ext(kind):
    if kind in KINDS:
        return KINDS[kind][3]
    if kind in EXT_TYPE:
        return kind
    for ext, t in EXT_TYPE.items():
        if t == kind:
            return ext
    raise ValueError(f"unknown object kind {kind!r}")


def block_cost(size, align):
    """Bytes object_header_block_allocate adds for one block."""
    return size + (1 << align) - 1 if size > 0 else 0


def pool_cost(data_size):
    """Pool bytes of one object whose data size is data_size."""
    return (data_size + BLOCK_HEADER + 15) & ~15


# -- tag data ------------------------------------------------------------------

def _load():
    global _cache
    if _cache is None:
        try:
            _cache = json.loads(CACHE.read_text())
        except (OSError, ValueError):
            _cache = {}
        for k in ("objects", "models", "render"):
            _cache.setdefault(k, {})
    return _cache


def _save():
    CACHE.write_text(json.dumps(_cache, indent=0, sort_keys=True))


def _tagfile(tag, ext):
    return EK / "tags" / (tag.replace("\\", "/") + "." + ext)


def _mtime(tag, ext):
    f = _tagfile(tag, ext)
    return f.stat().st_mtime if f.exists() else None


def _xml(tag, ext):
    """export-tag-to-xml, cached (re-exported when the tag changes); list of lines."""
    out = ek.export_cached(tag, ext, "object_memory_xml")
    if out is None:
        raise RuntimeError(f"export-tag-to-xml failed for {tag}.{ext}")
    return out.read_bytes().decode("latin-1").splitlines()


_LINE = re.compile(r'(\s*)<(field|block|element) (?:index="\d+" )?name="([^"]*)"(?: value="([^"]*)")?(?: type="([^"]*)")?')


def _tree(lines):
    """Nested dicts {'name', 'kind', 'value', 'type', 'kids'} from an export-tag-to-xml file."""
    root = {"name": "", "kind": "root", "kids": []}
    stack = [(-1, root)]
    for line in lines:
        m = _LINE.match(line)
        if not m:
            continue
        ind = len(m.group(1))
        node = {"name": m.group(3), "kind": m.group(2), "value": m.group(4) or "", "type": m.group(5) or "",
                "kids": []}
        while stack[-1][0] >= ind:
            stack.pop()
        stack[-1][1]["kids"].append(node)
        if node["kind"] in ("block", "element") or node["type"] in ("struct", "array"):
            stack.append((ind, node))
    return root


def _find(node, *path):
    """First descendant chain matching names (searching depth-first at each step)."""
    for name in path:
        hit = None
        todo = list(node["kids"])
        while todo:
            n = todo.pop(0)
            if n["name"] == name:
                hit = n
                break
            if n["kind"] != "block":      # don't descend into other blocks' elements
                todo[0:0] = n["kids"]
        if hit is None:
            return None
        node = hit
    return node


def _count(block):
    if block is None:
        return 0
    m = re.search(r",(\d+)$", block["value"])
    return int(m.group(1)) if m else len([k for k in block["kids"] if k["kind"] == "element"])


def _ref(node):
    """(path, ext) of a tag reference node, or None."""
    if node is None or not node["value"]:
        return None
    path, _, group = node["value"].partition(",")
    if not path:
        return None
    return path, GROUP_EXT.get(group, group)


def _object_info(tag, ext):
    db = _load()["objects"]
    key = f"{tag.lower()}.{ext}"
    mt = _mtime(tag, ext)
    if mt is None:
        raise FileNotFoundError(f"no tag {tag}.{ext}")
    if key in db and db[key]["mtime"] == mt:
        return db[key]
    t = _tree(_xml(tag, ext))
    obj = _find(t, "object")
    info = {"mtime": mt,
            "attachments": _count(_find(obj, "attachments")),
            "change_colors": _count(_find(obj, "change colors")),
            "mp": _count(_find(obj, "multiplayer object")),
            "model": _ref(_find(obj, "model")),
            "variant": (_find(obj, "default model variant") or {}).get("value", ""),
            "weapons": [], "friction": 0, "device_flags": 0}
    weapons = _find(t, "weapons")
    if weapons is not None and EXT_TYPE.get(ext) in UNITS:
        for e in weapons["kids"]:
            r = _ref(_find(e, "weapon"))
            if r:
                info["weapons"].append(r)
    if ext == "vehicle":
        info["friction"] = _count(_find(t, "friction points"))
    if EXT_TYPE.get(ext) in DEVICES:
        dev = _find(t, "device")
        flags = _find(dev, "flags") if dev else None
        try:
            info["device_flags"] = int(flags["value"]) if flags else 0
        except ValueError:
            info["device_flags"] = 0
    db[key] = info
    _save()
    return info


def _model_info(model):
    db = _load()["models"]
    key = model.lower()
    mt = _mtime(model, "model")
    if mt is None:
        return None
    if key in db and db[key]["mtime"] == mt:
        return db[key]
    t = _tree(_xml(model, "model"))
    variants = []
    vb = _find(t, "variants")
    for e in (vb["kids"] if vb else []):
        if e["kind"] != "element":
            continue
        kids = []
        ob = _find(e, "objects")
        for o in (ob["kids"] if ob else []):
            r = _ref(_find(o, "child object"))
            if r:
                kids.append([r[0], r[1], (_find(o, "child variant name") or {}).get("value", "")])
        variants.append([(_find(e, "name") or {}).get("value", ""), kids])
    dmg = _find(t, "new damage info")
    sections = None
    if dmg is not None and _count(dmg) > 0:
        el = [k for k in dmg["kids"] if k["kind"] == "element"][0]
        sections = _count(_find(el, "damage sections"))
    info = {"mtime": mt, "render": _ref(_find(t, "render model")), "graph": _ref(_find(t, "animation")) is not None,
            "variants": variants, "damage_sections": sections}
    db[key] = info
    _save()
    return info


def _render_counts(paths):
    """{render model path lower: (nodes, regions)}, via one mbedit run for the uncached ones."""
    db = _load()["render"]
    out, todo = {}, []
    for p in paths:
        mt = _mtime(p, "render_model")
        k = p.lower()
        if k in db and db[k]["mtime"] == mt:
            out[k] = (db[k]["nodes"], db[k]["regions"])
        elif mt is not None:
            todo.append(p)
    if todo:
        lines = []
        for p in todo:
            lines += [f"load\t{p}\trender_model", "count\tnodes", "count\tregions"]
        r = ek.mbedit_run(lines, "object_memory_mb.txt")
        nums = [int(x) for x in r.stdout.split()] if not r.returncode else []
        if len(nums) != 2 * len(todo):
            raise RuntimeError("mbedit render model counts failed: " + (r.stderr or r.stdout)[-1000:])
        for i, p in enumerate(todo):
            n, g = nums[2 * i], nums[2 * i + 1]
            db[p.lower()] = {"mtime": _mtime(p, "render_model"), "nodes": n, "regions": g}
            out[p.lower()] = (n, g)
        _save()
    return out


# -- costs ---------------------------------------------------------------------

def data_size(tag, ext):
    """The object's data size (objects_dump_memory 'maxsize'), children not included."""
    typ = EXT_TYPE[ext]
    o = _object_info(tag, ext)
    m = _model_info(o["model"][0]) if o["model"] else None
    nodes = regions = 1
    graph = False
    sections = None
    if m:
        graph = m["graph"]
        sections = m["damage_sections"]
        if m["render"]:
            nodes, regions = _render_counts([m["render"][0]]).get(m["render"][0].lower(), (1, 1))
            nodes, regions = max(nodes, 1), max(regions, 1)
    return size_of(typ, o["attachments"], sections, o["change_colors"], nodes, regions, graph, o["mp"],
                   o["friction"], o["device_flags"])


def size_of(typ, attachments, sections, change_colors, nodes, regions, graph, mp, friction, device_flags=0):
    """The data size of an object of type typ (a TYPE_SIZE key) from its tag's counts:
    attachments, damage sections (None: no damage info), change colors, render model nodes and
    regions, whether its model has an animation graph, multiplayer object entries, friction points."""
    animated = graph and (typ in ANIMATED or (typ in DEVICES and device_flags & 4))
    size = TYPE_SIZE[typ]
    size += block_cost(8 * attachments, 2)
    size += block_cost(8 * (sections or 0), 1)
    size += block_cost(24 * change_colors, 2)
    size += block_cost(52 * nodes, 2)
    size += block_cost(10 * regions, 2)
    if animated:
        size += 2 * block_cost(32 * nodes, 4)
    if graph:
        size += block_cost(0xb0 + MIXING_BOARD.get(typ, 0), 3)
    if mp:
        size += block_cost(0x4c, 2)
    if typ in MOVER:
        size += block_cost(4 * 0x1c, 2) + block_cost(MOVER[typ], 2) + block_cost(0x6c, 2)
    if typ in UNITS:
        size += block_cost(0x44, 2) + block_cost(0x5c, 2)
    if typ == "biped":
        size += block_cost(0x28, 2)
    if typ == "vehicle":
        size += block_cost(0x2c * friction, 4)
    return size


def children(tag, ext, variant=""):
    """[(tag, ext, variant)] created with the object: unit weapons, then model variant objects."""
    o = _object_info(tag, ext)
    out = [(w, e, "") for w, e in o["weapons"]]
    m = _model_info(o["model"][0]) if o["model"] else None
    if m and m["variants"]:
        want = (variant or o["variant"]).lower()
        pick = next((v for v in m["variants"] if v[0].lower() == want), m["variants"][0])
        out += [tuple(k) for k in pick[1]]
    return out


def _resolve(tag, kind):
    """(tag, ext) to read; a machine made by machines.py that isn't on disk yet reads its source."""
    tag = tag.replace("/", "\\")
    ext = _ext(kind)
    if _mtime(tag, ext) is None and ext == "device_machine":
        for (src, src_ext), new in machines._USED.items():
            if new.lower() == tag.lower():
                return src, src_ext, "machine"
    return tag, ext, None


def _walk(tag, kind, variant="", depth=0):
    """[(tag, ext, data size)] of the object and its children, creation order."""
    for d in active().donors:
        ported = d.walk(tag)       # a donor vehicle's placeholder: the real vehicle's costs
        if ported is not None:
            return ported
    tag, ext, as_type = _resolve(tag, kind)
    size = data_size(tag, ext)
    if as_type:   # source scenery/crate standing in for a machine: swap the type struct
        size += TYPE_SIZE[as_type] - TYPE_SIZE[EXT_TYPE[ext]]
    out = [(tag, ext, size)]
    if depth < 4:
        for t, e, v in children(tag, ext, variant):
            if _mtime(t, e) is not None:
                out += _walk(t, e, v, depth + 1)
    return out


def cost(tag_path, kind, variant=""):
    """Pool bytes one placement of tag_path (no extension) of kind (a KINDS key or tag extension) uses,
    its child objects included."""
    return sum(pool_cost(s) for _, _, s in _walk(tag_path, kind, variant))


def objects(tag_path, kind, variant=""):
    """Object datums (of MAX_OBJECTS) one placement uses, children included."""
    return len(_walk(tag_path, kind, variant))


def player_cost():
    return cost(PLAYER_BIPED, "biped") + sum(cost(w, "weapon") for w in PLAYER_WEAPONS)


# player_cost(): mp_masterchief 9552 + its two "gear" variant objects 2 x 544 + assault_rifle 1472 + battle_rifle 1456
PLAYER_COST = 13568
# in game on stock MCC: halo3.dll's pool is the tool's, so the level shares those 1.5 MB with
# 16 players, their bodies, dropped weapons and projectiles: about 978 KB for the level
MCC_LEVEL_BUDGET = POOL_BYTES - MCC_PLAYERS * (PLAYER_COST + PLAYER_HEADROOM)
# in game under Project Reclaimer (its 10.5 MB pool): about 5.76 MB for the level
GAME_LEVEL_BUDGET = RECLAIMER_POOL_BYTES - RECLAIMER_PLAYERS * PLAYER_COST - GAME_HEADROOM
RECLAIMER_LEVEL_BUDGET = GAME_LEVEL_BUDGET


def plan_bytes(plan, stock=True):
    """Pool use of every placement in a Plan (plus the stock scenario objects that remain).
    Returns {'total', 'objects', 'by_kind': {kind: [count, bytes]}, 'by_tag': {(kind, tag): [count, bytes]}}."""
    by_kind, by_tag = {}, {}
    total = nobj = 0

    def add(kind, tag, n=1):
        nonlocal total, nobj
        c = cost(tag, kind)
        total += c * n
        nobj += objects(tag, kind) * n
        k = by_kind.setdefault(kind, [0, 0])
        k[0] += n
        k[1] += c * n
        t = by_tag.setdefault((kind, tag), [0, 0])
        t[0] += n
        t[1] += c * n

    for p in plan.items:
        kind, tag = p.resolve()
        add(kind, tag)
    if stock:
        for tag, ext, n in stock_objects():
            add(ext, tag, n)
    return {"total": total, "objects": nobj, "by_kind": by_kind, "by_tag": by_tag}


def simulate(placements, stock=True):
    """Replay build-cache-file's 'placing objects on bsp' for [(kind, tag)] (Plan order within a kind;
    the stock sky first, the stock sound/effect scenery in their slots of CREATION_ORDER).
    Returns ([(kind, tag, created?)], bytes left).  A placement is created when its whole cost
    still fits; this reproduces a build's failures in order."""
    items = list(placements)
    free = POOL_BYTES
    if stock:
        for tag, ext, n in stock_objects():
            if ext == "scenery":
                free -= cost(tag, ext) * n
            else:
                items += [(ext, tag)] * n
    order = {k: i for i, k in enumerate(CREATION_ORDER)}
    seq = sorted(items, key=lambda kt: order.get(kt[0], len(order)))
    out = []
    for kind, tag in seq:
        c = cost(tag, kind)
        ok = c <= free
        if ok:
            free -= c
        out.append((kind, tag, ok))
    return out, free


def report(plan):
    """The pool use of a plan, by kind and by tag, against the tool's and the game's pools."""
    r = plan_bytes(plan)
    out = [f"pool {POOL_BYTES:,} bytes, {MAX_OBJECTS} objects; player (biped + 2 weapons) {player_cost():,} bytes",
           f"plan + stock: {r['total']:,} bytes ({100 * r['total'] / POOL_BYTES:.0f}% of the pool), "
           f"{r['objects']} objects",
           f"{'kind':<16}{'count':>7}{'bytes':>12}{'avg':>8}"]
    for k, (n, b) in sorted(r["by_kind"].items(), key=lambda kv: -kv[1][1]):
        out.append(f"{k:<16}{n:>7}{b:>12,}{b // n:>8,}")
    out.append("top tags by total bytes:")
    for (k, t), (n, b) in sorted(r["by_tag"].items(), key=lambda kv: -kv[1][1])[:15]:
        out.append(f"  {b:>10,}  {n:>4} x {b // n:>6,}  {k:<10} {t}")
    def verdict(budget):
        over = r["total"] - budget
        return "fits" if over <= 0 else f"OVER by {over:,} bytes"

    out.append(f"tool budget (clean build, {TOOL_LEVEL_BUDGET:,} bytes): {verdict(TOOL_LEVEL_BUDGET)}")
    out.append(f"in game on MCC ({MCC_PLAYERS} players, {MCC_LEVEL_BUDGET:,} bytes for the level): "
               f"{verdict(MCC_LEVEL_BUDGET)}"
               + ("" if r["total"] <= MCC_LEVEL_BUDGET else "; objects past the pool aren't created in game"))
    out.append(f"under Project Reclaimer ({RECLAIMER_PLAYERS} players, {RECLAIMER_POOL_BYTES:,}-byte pool, "
               f"{GAME_LEVEL_BUDGET:,} bytes for the level): {verdict(GAME_LEVEL_BUDGET)}")
    return "\n".join(out)

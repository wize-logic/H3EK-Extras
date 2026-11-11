"""Static props as device_machine tags, which take no map-variant slot.

Halo 3's map variant gives one of its 640 slots to every scenario placement of
a vehicle, weapon, equipment, scenery or crate (halo3_tag_test.exe
FUN_1403f6dd0: object type mask 0x44e). Machines (type 7) are not in that mask.
A machine made from a scenery/crate tag (same object struct: model, functions,
attachments...; no animation, no power or position group) looks and collides
the same and never moves.

    machine_for(tag, kind) -> new tag path (no extension), or None if refused
    tag_script()           -> mbedit lines that create every machine used so far

Engine limits (same exe): at most 600 machine placements per scenario
(MAXIMUM_MACHINE_DATUMS_PER_SCENARIO, also the runtime placement table), and
every machine gets a networked device entity (FUN_1401a6d10: type 7 -> entity
type 0x16) out of the simulation's 1024-entity table, shared with players,
vehicles, weapons, projectiles. Stock MP maps ship at most 26 machines.
"""

import re

from . import ek
from .project import active

ENGINE_MAX_MACHINES = 600   # MAXIMUM_MACHINE_DATUMS_PER_SCENARIO


def prop_dir():
    """Where the machines go: the project's objects\\...\\props."""
    return active().tag_dir("props")


LIMIT = None    # a lower cap for a while (dressing keeps twin pairs whole); None: the project's


def max_machines():
    """Placements (engine hard cap 600, entity table 1024, see above): the project's
    machine_budget, so the network slots go to vehicles and players."""
    return active().machine_budget if LIMIT is None else LIMIT


# multiplayer object types that are gameplay, never converted
GAMEPLAY_TYPES = {"teleporter 2way", "teleporter sender", "teleporter receiver", "weapon", "vehicle",
                  "spawn point", "initial spawn point", "respawn zone", "flag spawn", "flag return",
                  "hill objective", "goal", "ball spawn", "territory", "vip boundary"}

_USED = {}      # (src tag lower, ext) -> new tag path
_CHECKED = {}   # (src tag lower, ext) -> reason or ""


def _xml(tag, ext):
    """export-tag-to-xml of a tag, cached under work\\machines_cache (refreshed when the tag changes)."""
    out = ek.export_cached(tag, ext, "machines_cache")
    return out.read_text(encoding="latin-1") if out else None


def _ref(xml, field):
    m = re.search(r'<field name="%s" value="([^",]*),' % re.escape(field), xml)
    return m.group(1) if m else ""


def why_not(tag, kind):
    """'' if the scenery/crate tag can become a static machine, else the reason."""
    tag = tag.replace("/", "\\")
    key = (tag.lower(), kind)
    if key in _CHECKED:
        return _CHECKED[key]
    reason = ""
    if kind not in ("scenery", "crate"):
        reason = f"kind {kind}"
    else:
        obj = _xml(tag, kind)
        if obj is None:
            reason = "no tag"
        else:
            mp = re.findall(r'<field name="type" value="([^"]*)" type="char enum"/>', obj)
            model = _ref(obj, "model")
            if any(t in GAMEPLAY_TYPES for t in mp):
                reason = f"gameplay multiplayer object {mp}"
            elif not model:
                reason = "no model"
            else:
                hlmt = _xml(model, "model") or ""
                if _ref(hlmt, "animation"):
                    reason = "animated model"
                elif not _ref(hlmt, "render model"):
                    reason = "no render model"
    _CHECKED[key] = reason
    return reason


def machine_for(tag, kind):
    """The device_machine standing in for a static scenery/crate tag (path without
    extension), or None if it is not convertible. Registers it for tag_script()."""
    tag = tag.replace("/", "\\")
    key = (tag.lower(), kind)
    if key in _USED:
        return _USED[key]
    if why_not(tag, kind):
        return None
    name = tag.split("\\")[-1].lower()
    taken = {v.lower() for v in _USED.values()}
    folder = prop_dir()
    new = f"{folder}\\{name}"
    k = 2
    while new.lower() in taken:
        new = f"{folder}\\{name}_{k}"
        k += 1
    _USED[key] = new
    return new


def tag_script():
    """mbedit lines (re)creating every machine handed out this run: a blank
    device_machine with the source's whole object struct (model, flags,
    bounds, functions, attachments, change colors) minus its Forge block."""
    lines = []
    for (src, kind), new in sorted(_USED.items(), key=lambda kv: kv[1]):
        lines += [f"new\t{new}\tdevice_machine",
                  f"copyfrom\t{src}\t{kind}\tobject\tdevice/object\tmultiplayer object,runtime object type",
                  "set\tdevice/object/runtime object type\t7",
                  "set\ttype\tgear",
                  "set\tflags\t0x31",    # pathfinding obstacle, NOT pathfinding mobile, default occlusion bounds
                  f"saveas\t{new}\tdevice_machine"]
    return lines


def used():
    return dict(_USED)

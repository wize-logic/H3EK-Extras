"""A map pack: several projects' built maps in one MCC mod, laid out like Ultimate Forge's
(Workshop 2933266434). A plain pack is its projects' standalone maps side by side; a shared pack
(Pack(shared=True)) rebuilds its maps against one shared.map of its own (build_shared(): the
Editing Kit's shared build for these scenarios only) and ships that
shared.map and campaign.map in halo3/maps/:

    ModInfo.json                         the pack's: every map's JSON in MultiplayerMaps
    maps/<file>.map                      each project's package map (hard-linked, not copied)
    multiplayer/<file>.json              each map's own JSON, its images renamed per map
    images/large.png, thumbnail.png      the pack's (a strip of its maps' pictures)
    images/large_<file>.png ...          each map's large, thumbnail and loading pictures
    Project Reclaimer Game Modes/        every map's game types (if any map has them)
    halo3/maps/shared.map, campaign.map  a shared pack's own (built with its maps)

    python3 -m h3kit.pack packs/<pack> build-shared     # a shared pack's maps -> packs/<pack>/shared
    python3 -m h3kit.pack packs/<pack> build            # assemble packs/<pack>/package
    python3 -m h3kit.pack packs/<pack> release [--yes]  # into the upload folder (and Reclaimer's Mods, if installed)

A pack's folder holds pack.py defining PACK = Pack(...). Each map keeps its scenario, map id and
MapGuid, so the pack and a map's own mod shouldn't be installed side by side.
"""

import argparse
import importlib.util
import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from . import package as P


@dataclass
class Pack:
    title: str                       # the package's folder name (Mods\<title>)
    shown_title: str                 # the Workshop and mod list title
    description: str
    mod_guid: str
    maps: list                       # the projects' folders (maps/<map>), in the order shown
    root: Path = None                # the pack's folder (set by load_pack)
    version: tuple = (1, 0, 0)
    workshop_id: int = 0
    upload_dir: Path = None          # the folder Excession uploads from
    shared: bool = False             # the maps come from build_shared() with the pack's own shared.map
    strip_highres: tuple = ()        # bitmap folders whose high-res mips build_shared drops (h3kit/strip.py)
    strip_shrink: tuple = ()         # bitmap folders build_shared cuts to strip_largest px at most
    strip_largest: int = 128
    projects: list = field(default_factory=list)

    @property
    def package_dir(self):
        return self.root / "package"


def load_pack(folder):
    folder = Path(folder).resolve()
    spec = importlib.util.spec_from_file_location("pack_def", folder / "pack.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    pack = mod.PACK
    pack.root = folder
    repo = folder.parent.parent
    pack.projects = [_project(repo / m) for m in pack.maps]
    return pack


def _project(map_dir):
    """A map folder's project (its project.py run under its own module name: every map's is called
    project, so project.load would hand back the first one each time)."""
    import sys
    from .project import active
    d = str(Path(map_dir).resolve())
    sys.path.insert(0, d)
    try:
        spec = importlib.util.spec_from_file_location(f"project_{Path(d).name}", Path(d) / "project.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return active()
    finally:
        sys.path.remove(d)


def modinfo(pack):
    first = pack.projects[0].mod
    return {
        "ModIdentifier": {"ModGuid": pack.mod_guid, "HostedModIds": {"SteamWorkshopId": pack.workshop_id}},
        "ModVersion": P.version(pack.version),
        "MinAppVersion": P.version(first.app_versions[0]),
        "MaxAppVersion": P.version(first.app_versions[1]),
        "Engine": "Halo3",
        "Title": {"Neutral": pack.shown_title},
        "Description": {"Neutral": pack.description},
        "InheritSharedFiles": "FromMCC",
        "ModContents": {"HasBackgroundVideos": False, "HasNameplates": False},
        "GameModContents": {
            "HasSharedFiles": False,
            "HasCampaign": False,
            "HasSpartanOps": False,
            "HasController": False,
            "MultiplayerMaps": [f"multiplayer/{p.file_name}.json" for p in pack.projects],
        },
    }


def _link(src, dst):
    """dst as a hard link to src (the maps are ~1 GB each), else a copy."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        if os.path.samefile(src, dst):
            return
        dst.unlink()
    try:
        os.link(src, dst)
    except OSError:
        shutil.copyfile(src, dst)


def _strip(pictures, w, h):
    """The pack's picture: its maps' pictures side by side, w x h."""
    from PIL import Image
    out = Image.new("RGB", (w, h))
    n = len(pictures)
    for i, path in enumerate(pictures):
        x0, x1 = round(i * w / n), round((i + 1) * w / n)
        out.paste(P.crop_to(Image.open(path), x1 - x0, h), (x0, 0))
    return out


def build(pack):
    """Assemble the pack's package folder from its projects' packages."""
    out = pack.package_dir
    if out.exists():
        shutil.rmtree(out)
    (out / "multiplayer").mkdir(parents=True)
    (out / "images").mkdir()
    for p in pack.projects:
        src_map = (pack.root / "shared" / f"{p.scenario.split(chr(92))[-1]}.map") if pack.shared else p.package_map
        if not src_map.exists():
            raise SystemExit(f"pack: {src_map} is missing; " + ("run build-shared" if pack.shared else
                                                                 f"build {p.root.name} first"))
        P.write_metadata(project=p)            # the map's own package metadata, current
        f = p.file_name
        _link(src_map, out / "maps" / f"{f}.map")
        info = P.mapinfo(p)
        for key, name in (("Large", "large"), ("Thumbnail", "thumbnail"), ("LoadingScreen", "loading"),
                          ("TopDown", "large")):
            info["Images"][key] = f"images\\{name}_{f}.png"
        (out / "multiplayer" / f"{f}.json").write_text(json.dumps(info, indent="\t"))
        for name in ("large", "thumbnail", "loading"):
            src = p.package_dir / "images" / f"{name}.png"
            if not src.exists():
                raise SystemExit(f"pack: {src} is missing (python3 -m h3kit.package {p.root} images)")
            shutil.copyfile(src, out / "images" / f"{name}_{f}.png")
        modes = p.package_dir / P.GAME_MODES
        if modes.is_dir():
            for g in modes.glob("*.json"):
                (out / P.GAME_MODES).mkdir(exist_ok=True)
                shutil.copyfile(g, out / P.GAME_MODES / g.name)
        print(f"pack: {f}.map ({src_map.stat().st_size / 2**20:,.0f} MB)")
    if pack.shared:      # where MCC looks for a mod's own shared files (Ultimate Forge's layout)
        for f in ("shared", "campaign"):
            _link(pack.root / "shared" / f"{f}.map", out / "halo3" / "maps" / f"{f}.map")
    for name, (w, h) in P.SIZES.items():
        if name != "loading.png":
            _strip([p.package_dir / "images" / "large.png" for p in pack.projects], w, h).save(out / "images" / name)
    (out / "ModInfo.json").write_text(json.dumps(modinfo(pack), indent="\t"))
    total = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    print(f"pack: {out} ({total / 2**30:.2f} GB)")
    return out


# -- a shared pack: the maps built against one shared.map of their own -------------------------------------

def _tool(step, args, log):
    from . import ek
    print(f"pack [{step}] tool {' '.join(args)}", flush=True)
    code, tail = ek.tool(*args, log=log)
    if code:
        raise SystemExit(f"pack [{step}] failed (H3EK\\work\\{log}):\n" + "\n".join(tail))
    return tail


def build_shared(pack):
    """The Editing Kit's shared build (H3EK\\BuildMapsSharedOptimizedPlusSharedSounds.ps1, steps 3-13)
    for the pack's scenarios only, into packs/<pack>/shared/: each level map, and the
    shared.map and campaign.map built for them. Unlike the kit's script it never deletes a built map:
    H3EK\\maps\\*.map and cache_builder are moved aside first and put back afterwards. Every project must
    have been built (its tags as its last build left them)."""
    import time
    from .env import EK, EK_WIN
    stamp = time.strftime("%Y%m%d_%H%M%S")
    maps_dir, cb = EK / "maps", EK / "cache_builder"
    saved_maps, saved_cb = EK / f"maps_saved_{stamp}", EK / f"cache_builder_saved_{stamp}"
    scenarios = [p.scenario for p in pack.projects]
    names = [s.split("\\")[-1] for s in scenarios]
    out = pack.root / "shared"
    moved = []
    for f in list(maps_dir.glob("*.map")) + list((maps_dir / "security").glob("*.bin")):
        dst = saved_maps / f.relative_to(maps_dir)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(f), str(dst))
        moved.append((dst, f))
    if cb.exists():
        shutil.move(str(cb), str(saved_cb))
    cb.mkdir()
    try:
        codex = cb / "sounds_file_codex.bin"
        for s in scenarios:                                                   # 3: one sound codex, in turn
            _tool("3 sound index", ["build-cache-file-cache-sounds-index", s] + (["append"] if codex.exists() else [])
                  + ["pc"], "pack_03_sounds_index.log")
        _tool("4 sounds", ["build-cache-file-cache-sounds", "pc", "english", "0", "use-fmod-data"], "pack_04_sounds.log")
        _tool("5 shared", ["build-cache-file-cache-shared-first", "pc", "english", "0", "optimizable",
                           "use-shared-sounds", "use-fmod-data"], "pack_05_shared.log")
        _tool("6 campaign", ["build-cache-file-cache-campaign-second", "pc", "english", "0", "optimizable",
                             "use-fmod-data"], "pack_06_campaign.log")
        for s, n in zip(scenarios, names):                                    # 7: each map against them
            _tool(f"7 {n}", ["build-cache-file-language-version-optimizable-use-sharing", "english", "0", s, "pc",
                             "use-shared-sounds", "use-fmod-data"], f"pack_07_{n}.log")
        opt = cb / "to_optimize"
        opt.mkdir(exist_ok=True)
        (cb / "dvd_prop_list.txt").write_text(
            "".join(f"..\\cache_builder\\to_optimize\\{n}.cache_file_resource_gestalt\r\n" for n in names))
        for f in ("shared.map", "campaign.map", "english.map"):              # 9
            if (maps_dir / f).exists():
                shutil.copyfile(maps_dir / f, opt / f)
        missing = [n for n in names if not (opt / f"{n}.cache_file_resource_gestalt").exists()]
        if missing:
            raise SystemExit(f"pack: step 7 left no to_optimize gestalt for {missing}: "
                             f"{sorted(x.name for x in opt.iterdir())}")
        _tool("10 layout", ["generate-final-shared-layout", f"{EK_WIN}\\cache_builder\\dvd_prop_list.txt", "pc"],
              "pack_10_layout.log")
        for s, n in zip(scenarios, names):                                    # 11: each map on the final layout
            _tool(f"11 {n}", ["build-cache-file-generate-new-layout", s, "pc", "use-fmod-data"], f"pack_11_{n}.log")
        _tool("12 link shared", ["build-cache-file-link", "shared", "pc", "use-fmod-data"], "pack_12_shared.log")
        _tool("13 link campaign", ["build-cache-file-link", "campaign", "pc", "use-fmod-data"], "pack_13_campaign.log")
        if out.exists():
            shutil.rmtree(out)
        out.mkdir(parents=True)
        for f in names + ["shared", "campaign"]:
            src = maps_dir / f"{f}.map"
            if not src.exists():
                raise SystemExit(f"pack: the shared build made no {src}")
            shutil.move(str(src), str(out / f"{f}.map"))
            print(f"pack: {f}.map {(out / f'{f}.map').stat().st_size / 2**20:,.0f} MB")
        for f in maps_dir.glob("*.map"):          # anything else the steps left (english.map...): kept with them
            shutil.move(str(f), str(out / f.name))
        if pack.strip_highres or pack.strip_shrink:   # high-res mips out, the armour shrunk (h3kit/strip.py)
            from . import strip as _strip
            if _strip.verify(out, prefixes=tuple(pack.strip_highres) + tuple(pack.strip_shrink)):
                raise SystemExit("pack: the shared build failed its read-back before stripping: the check or the build is wrong")
            _strip.strip(out, highres=tuple(pack.strip_highres), shrink=tuple(pack.strip_shrink),
                         largest=pack.strip_largest)
            if _strip.verify(out, prefixes=tuple(pack.strip_highres) + tuple(pack.strip_shrink)):
                raise SystemExit("pack: the stripped maps failed their read-back (see above)")
    finally:
        for dst, f in moved:
            if not f.exists():
                f.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(dst), str(f))
        if saved_maps.exists() and not any(p.is_file() for p in saved_maps.rglob("*")):
            shutil.rmtree(saved_maps)
        if saved_cb.exists():          # this run's cache_builder kept beside it (for a look), the old one back
            # only the latest: each is ~5 GB
            for old in EK.glob("cache_builder_pack_*"):
                shutil.rmtree(old, ignore_errors=True)
            shutil.move(str(cb), str(EK / f"cache_builder_pack_{stamp}"))
            shutil.move(str(saved_cb), str(cb))
    return out


def release(pack, apply=False):
    """Copy every pack file that differs into the upload folder (and Project Reclaimer's Mods\\<title>
    and Game Modes, when Reclaimer is installed); with apply=False only list them."""
    pkg = pack.package_dir
    if not (pkg / "ModInfo.json").exists():
        raise SystemExit("release: build the pack first")
    return P.sync(pkg, P.release_targets(pack.title, pack.upload_dir), apply, what="pack")


def main(argv=None):
    ap = argparse.ArgumentParser(description="A map pack: several maps in one MCC mod.")
    ap.add_argument("pack", type=Path, help="the pack's folder (packs/<pack>, holding pack.py)")
    ap.add_argument("what", choices=["build-shared", "build", "release"])
    ap.add_argument("--yes", action="store_true", help="release: copy (default: list what would change)")
    args = ap.parse_args(argv)
    pack = load_pack(args.pack)
    if args.what == "build-shared":
        if not pack.shared:
            raise SystemExit("pack: not a shared pack (Pack(shared=True))")
        build_shared(pack)
    elif args.what == "build":
        build(pack)
    else:
        release(pack, apply=args.yes)


if __name__ == "__main__":
    main()

"""The MCC mod package: ModInfo.json and the map's JSON from the project's
Mod, the Workshop images, and the release copies.

    python3 -m h3kit.package maps/<map> meta               # ModInfo.json + multiplayer/<file>.json
    python3 -m h3kit.package maps/<map> images [--art X]   # images/ from a picture (no text: the game
                                                           # draws the map's name itself)
    python3 -m h3kit.package maps/<map> release [--yes]    # sync the package into the Excession upload
                                                           # folder (and Project Reclaimer's Mods, if
                                                           # installed); dry run without --yes

A package folder holds ModInfo.json, maps\\<file>.map, multiplayer\\<file>.json,
images\\, and whatever else the map ships (a donor's halo3\\fmod\\pc sound banks, a
"Project Reclaimer Game Modes" folder). <file> is the project's file_name (the
scenario's name unless the Mod sets one). Bump Mod.version before a release; the
upload itself is Excession's (GUI only).
"""

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

from . import env
from .project import active, load

SIZES = {"large.png": (668, 292), "thumbnail.png": (316, 160), "loading.png": (1920, 1080)}
GAME_MODES = "Project Reclaimer Game Modes"     # a package folder of game type JSONs for Reclaimer players
INSTALLED = "installed mod (Reclaimer)"


def version(v):
    return dict(zip(("Major", "Minor", "Patch"), v))


def modinfo(project=None):
    p = project or active()
    m = p.mod
    return {
        "ModIdentifier": {"ModGuid": m.mod_guid, "HostedModIds": {"SteamWorkshopId": m.workshop_id}},
        "ModVersion": version(m.version),
        "MinAppVersion": version(m.app_versions[0]),
        "MaxAppVersion": version(m.app_versions[1]),
        "Engine": "Halo3",
        "Title": {"Neutral": m.shown_title},
        "Description": {"Neutral": m.description},
        "InheritSharedFiles": "FromMCC",
        "ModContents": {"HasBackgroundVideos": False, "HasNameplates": False},
        "GameModContents": {
            "HasSharedFiles": False,
            "HasCampaign": False,
            "HasSpartanOps": False,
            "HasController": False,
            "MultiplayerMaps": [f"multiplayer/{p.file_name}.json"],
        },
    }


def mapinfo(project=None):
    p = project or active()
    m = p.mod
    return {
        "MapGuid": m.map_guid,
        "ScenarioFile": p.file_name,
        "Title": {"Neutral": m.shown_title},
        "Description": {"Neutral": m.description},
        "Images": {
            "Large": "images\\large.png",
            "Thumbnail": "images\\thumbnail.png",
            "LoadingScreen": "images\\loading.png",
            "TopDown": "images\\large.png",
        },
        "Flags": list(m.flags),
        "InsertionPoints": [],
        "MaximumTeamsByGameCategory": {"All": m.max_teams},
    }


def write_metadata(out=None, project=None):
    """ModInfo.json and multiplayer/<file name>.json into the package (or `out`)."""
    p = project or active()
    pkg = Path(out or p.package_dir)
    (pkg / "maps").mkdir(parents=True, exist_ok=True)
    (pkg / "multiplayer").mkdir(exist_ok=True)
    (pkg / "images").mkdir(exist_ok=True)
    (pkg / "ModInfo.json").write_text(json.dumps(modinfo(p), indent="\t"))
    (pkg / "multiplayer" / f"{p.file_name}.json").write_text(json.dumps(mapinfo(p), indent="\t"))
    return pkg


# -- images ---------------------------------------------------------------------------

def crop_to(img, w, h):
    """A picture cropped to w:h (centred across; wider frames crop its bottom, so the
    sky and what stands on the horizon stay in) and scaled to w x h."""
    from PIL import Image
    img = img.convert("RGB")
    sw, sh = img.size
    if sw / sh > w / h:
        cw = round(sh * w / h)
        img = img.crop(((sw - cw) // 2, 0, (sw - cw) // 2 + cw, sh))
    else:
        img = img.crop((0, 0, sw, round(sw * h / w)))
    return img.resize((w, h), Image.LANCZOS)


def write_images(out, art=None, fallback=None):
    """images/large.png, thumbnail.png and loading.png: from the picture `art`, or
    fallback(w, h) -> PIL image when it is missing. Drawn large and scaled down."""
    from PIL import Image
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    src = Image.open(art) if art and Path(art).is_file() else None
    if src is None and fallback is None:
        raise SystemExit(f"package: no picture {art} and no fallback")
    for name, (w, h) in SIZES.items():
        k = max(1, 1920 // w)
        img = crop_to(src, w * k, h * k) if src else fallback(w * k, h * k)
        img.resize((w, h), Image.LANCZOS).save(out / name)
        print(out / name, (w, h))


# -- release ----------------------------------------------------------------------------

def release_targets(title, upload_dir):
    """{label: folder} a package is copied to: the Excession upload folder (when set) and,
    when Project Reclaimer is installed (env.RECLAIMER), its Mods\\<title>."""
    out = {}
    if upload_dir:
        out["upload (Excession)"] = Path(upload_dir)
    if env.RECLAIMER:
        out[INSTALLED] = env.RECLAIMER / "Mods" / title
    return out


def targets(project=None):
    """{label: folder} the project's package is copied to (release_targets)."""
    p = project or active()
    return release_targets(p.mod.title, p.mod.upload_dir)


def _digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def _same(a, b):
    return b.exists() and a.stat().st_size == b.stat().st_size and _digest(a) == _digest(b)


def sync(pkg, targets, apply=False, what="package"):
    """Copy every file of the package folder `pkg` that differs into each of `targets`
    ({label: folder}, release_targets), and its game types into Project Reclaimer's Game
    Modes when Reclaimer is installed; with apply=False only list them. Returns the changes."""
    if not targets:
        owner = "Pack" if what == "pack" else "Mod"
        raise SystemExit(f"release: nowhere to copy the {what}: set {owner}.upload_dir (the folder Excession "
                         f"uploads from), or upload the package folder itself with Excession: {pkg}")
    files = [f for f in sorted(pkg.rglob("*")) if f.is_file()]
    plan = []
    for label, folder in targets.items():
        for f in files:
            rel = f.relative_to(pkg)
            if label == INSTALLED and rel.parts[0] == GAME_MODES:
                continue    # Reclaimer reads game types from its own Game Modes folder (below)
            if not _same(f, folder / rel):
                plan.append((label, f, folder / rel))
    modes = pkg / GAME_MODES
    if env.RECLAIMER and modes.is_dir():
        for f in sorted(modes.glob("*.json")):
            dst = env.RECLAIMER / "Game Modes" / f.name
            if not _same(f, dst):
                plan.append(("Reclaimer game modes", f, dst))
    for label, src, dst in plan:
        print(f"{'copy' if apply else 'would copy'} [{label}] {src.relative_to(pkg)} -> {dst}")
        if apply:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
            if not _same(src, dst):
                raise SystemExit(f"release: {dst} differs after the copy")
    if not plan:
        print(f"release: every target already matches the {what}")
    elif not apply:
        print("dry run: add --yes to copy")
    return plan


def release(project=None, apply=False):
    """Sync the project's package into its release targets (sync); with apply=False only
    list the copies. Returns the changes."""
    p = project or active()
    if not p.package_map.exists():
        raise SystemExit(f"release: {p.package_map} is missing; build the map first")
    return sync(p.package_dir, targets(p), apply)


def main(argv=None):
    ap = argparse.ArgumentParser(description="The MCC mod package of a map.")
    ap.add_argument("map", type=Path, help="the map's folder (maps/<map>, holding project.py)")
    ap.add_argument("what", choices=["meta", "images", "release"])
    ap.add_argument("--art", type=Path, help="images: the picture to crop (default: the map's images.ART)")
    ap.add_argument("--yes", action="store_true", help="release: copy (default: list what would change)")
    args = ap.parse_args(argv)
    p = load(args.map)
    if args.what == "meta":
        print("package:", write_metadata())
    elif args.what == "images":
        sys.path.insert(0, str(p.root))
        try:
            import images as own      # the map's own images.py: ART and a fallback scene
        except ImportError:
            own = None
        art = args.art or getattr(own, "ART", None)
        write_images(p.package_dir / "images", art, getattr(own, "scene", None))
    else:
        write_metadata()
        release(p, apply=args.yes)


if __name__ == "__main__":
    main()

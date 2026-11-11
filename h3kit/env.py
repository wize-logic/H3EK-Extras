"""Where things are on this machine: Steam, the Editing Kit, MCC, the Workshop
downloads, the .NET SDK and (optionally) Project Reclaimer, seen from WSL.

The defaults are a standard Steam install on C:. Override any of them with an
environment variable or with a `local_paths.json` beside this package's
folder (the repository root), e.g.

    {"steamapps": "/mnt/d/SteamLibrary/steamapps", "documents": "/mnt/c/Users/me/Documents"}

Keys (and environment variables H3KIT_<KEY in capitals>): steamapps, ek,
mcc, workshop, documents, reclaimer (the user folder), reclaimer_exe, dotnet,
python_launcher.

Nothing needs Project Reclaimer: RECLAIMER is None unless it is set here or its
user folder exists; without it, `release` copies only to the Excession upload folder.
"""

import getpass
import json
import os
import subprocess
from pathlib import Path, PureWindowsPath

ROOT = Path(__file__).resolve().parent.parent      # the repository
LOCAL = ROOT / "local_paths.json"
MCC_APP_ID = 976730                                # Steam app id of MCC (Workshop content folder)


def _local():
    try:
        return json.loads(LOCAL.read_text())
    except (OSError, ValueError):
        return {}


def _get(key, default):
    v = os.environ.get(f"H3KIT_{key.upper()}") or _local().get(key)
    return Path(v) if v else Path(default)


STEAMAPPS = _get("steamapps", "/mnt/c/Program Files (x86)/Steam/steamapps")
EK = _get("ek", STEAMAPPS / "common" / "H3EK")                     # Halo 3 Editing Kit (Steam app 1695791)
MCC = _get("mcc", STEAMAPPS / "common" / "Halo The Master Chief Collection")
MCC_MAPS = MCC / "halo3" / "maps"                                  # stock built maps (sidewinder.map, ...)
WORKSHOP = _get("workshop", STEAMAPPS / "workshop" / "content" / str(MCC_APP_ID))
EXCESSION = STEAMAPPS / "common" / "Excession"                     # the Workshop uploader (GUI)
DOCUMENTS = _get("documents", f"/mnt/c/Users/{getpass.getuser()}/Documents")
# Project Reclaimer's user folder: Mods, Game Modes, Logs\client.log. Since 0.10 it is
# %LOCALAPPDATA%\ProjectReclaimer, and the old Documents folder is no longer read (the game
# leaves a "Your files moved.txt" there). 0.9 and earlier still use the Documents folder.
_LEGACY_RECLAIMER = DOCUMENTS / "My Games" / "Project Reclaimer"
_APPDATA_RECLAIMER = DOCUMENTS.parent / "AppData" / "Local" / "ProjectReclaimer"


def _reclaimer():
    """The configured user folder, else the one that exists; None when Reclaimer isn't installed
    (so nothing creates its folders on a machine that only has MCC)."""
    v = os.environ.get("H3KIT_RECLAIMER") or _local().get("reclaimer")
    if v:
        return Path(v)
    return next((d for d in (_APPDATA_RECLAIMER, _LEGACY_RECLAIMER) if d.is_dir()), None)


RECLAIMER = _reclaimer()
RECLAIMER_EXE = _get("reclaimer_exe", DOCUMENTS.parent / "Desktop" / "Reclaimer" / "Reclaimer.exe")
DOTNET = _get("dotnet", "/mnt/c/Program Files/dotnet/dotnet.exe")  # builds tools/hgport
PY_LAUNCHER = _get("python_launcher", "/mnt/c/Windows/py.exe")     # Windows Python, for the kit's bake script

# the optimized build of tool; tool.exe is the slower debug build
TOOL = "tool_fast.exe"
WORK = EK / "work"          # h3kit's scratch folder in the kit: mbedit.exe, logs, caches


def win(path):
    """The Windows form of a WSL path ("/mnt/c/x/y" -> "C:\\x\\y")."""
    p = Path(path)
    parts = p.parts
    if len(parts) >= 3 and parts[0] == "/" and parts[1] == "mnt" and len(parts[2]) == 1:
        return str(PureWindowsPath(f"{parts[2].upper()}:\\", *parts[3:]))
    return subprocess.run(["wslpath", "-w", str(p)], capture_output=True, text=True, check=True).stdout.strip()


EK_WIN = win(EK)
MCC_MAPS_WIN = win(MCC_MAPS)


def workshop_item(item_id):
    """The folder Steam downloads a Workshop item into."""
    return WORKSHOP / str(item_id)

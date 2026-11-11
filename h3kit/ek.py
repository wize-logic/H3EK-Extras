"""Running the Halo 3 Editing Kit from WSL: tool, mbedit (this project's tag
editor, tools/mbedit), tag XML exports and the light bake.

Every kit program runs with the kit's folder as its working directory, as it
must; scripts and logs go in H3EK\\work.

    tool("structure", r"levels\\...\\x.ASS", log="structure.log") -> (exit code, last lines)
    mbedit(lines, "edit.txt")             runs a script, exits on failure
    export_xml(tag, ext, "name.xml")      a tag as XML, exported once
    export_cached(tag, ext, "cache dir")  a tag as XML, re-exported when the tag changes
    bake(scenario, bsp, "medium")         the kit's lightmap farm on every core
"""

import re
import shutil
import subprocess
import sys

from . import env
from .env import EK, EK_WIN, TOOL, WORK

MBEDIT = WORK / "mbedit.exe"
KIT_FARM = "calc_lm_farm_local.py"     # the kit's bake script (job folder faux\111)
KIT_JOB = "111"

_TAGS_SEEN = {}


def tag_file(tag, ext):
    return EK / "tags" / (tag.replace("\\", "/") + "." + ext)


def tag_exists(tag, ext):
    """True if tags\\<tag>.<ext> is in the Editing Kit (always True without the kit)."""
    key = (tag.lower(), ext)
    if key not in _TAGS_SEEN:
        root = EK / "tags"
        _TAGS_SEEN[key] = not root.exists() or tag_file(tag, ext).exists()
    return _TAGS_SEEN[key]


def tool(*args, log=None):
    """Run tool_fast with its output in work\\<log>: (exit code, its last 8 non-empty lines)."""
    path = WORK / (log or "tool.log")
    with open(path, "w") as f:
        r = subprocess.run([str(EK / TOOL), *args], cwd=EK, stdout=f, stderr=subprocess.STDOUT)
    tail = path.read_text(errors="replace").replace("\r", "\n").splitlines()
    return r.returncode, [t for t in tail if t.strip()][-8:]


def mbedit_run(lines, name):
    """Write an mbedit script to work\\<name> and run it; the CompletedProcess (text)."""
    (WORK / name).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return subprocess.run([str(MBEDIT), EK_WIN, f"work\\{name}"], cwd=EK, capture_output=True, text=True)


def mbedit(lines, name):
    """Run an mbedit script; exit with the failing line on an error."""
    if not MBEDIT.exists():
        sys.exit(f"{MBEDIT} is missing: build it with tools/mbedit/build.sh")
    r = mbedit_run(lines, name)
    if r.returncode:
        if not r.stderr.strip():
            # ManagedBlam died without a message (e.g. a block past its maximum):
            # every add/count printed one line, so the next one is where it died
            done = len(r.stdout.splitlines())
            at = [i for i, line in enumerate(lines) if line.split("\t")[0] in ("add", "count")]
            if done < len(at):
                i = at[done]
                sys.exit(f"mbedit {name} crashed without a message at line {i + 1}: {lines[i]}")
        sys.exit(f"mbedit {name} failed: " + (r.stderr or r.stdout)[-2000:])
    return r


def export_xml(tag, ext, name):
    """A tag as XML (tool export-tag-to-xml), exported once into work\\<name>."""
    out = WORK / name
    if not out.exists():
        subprocess.run([str(EK / TOOL), "export-tag-to-xml",
                        f"{EK_WIN}\\tags\\{tag}.{ext}", f"{EK_WIN}\\work\\{name}"],
                       cwd=EK, check=True, capture_output=True)
    return out.read_text(encoding="latin-1")


def export_cached(tag, ext, cache):
    """A tag's XML file under work\\<cache>, re-exported when the tag is newer;
    None if the tag doesn't exist or the export failed."""
    src = tag_file(tag, ext)
    if not src.exists():
        return None
    folder = WORK / cache
    folder.mkdir(parents=True, exist_ok=True)
    name = re.sub(r"[^a-z0-9]+", "_", (tag + "." + ext).lower()) + ".xml"
    out = folder / name
    if not out.exists() or out.stat().st_mtime < src.stat().st_mtime:
        subprocess.run([str(EK / TOOL), "export-tag-to-xml", f"{EK_WIN}\\tags\\{tag}.{ext}",
                        f"{EK_WIN}\\work\\{cache}\\{name}"],
                       cwd=EK, stdin=subprocess.DEVNULL, capture_output=True)
    return out if out.exists() else None


def farm_script(job=KIT_JOB):
    """The bake script for a job folder: the kit's own for its default (faux\\111),
    else a copy of it in work\\ with the job id changed (ids must be numeric)."""
    if str(job) == KIT_JOB:
        return KIT_FARM
    if not str(job).isdigit():
        raise ValueError(f"bake job {job!r}: job ids must be numeric")
    text = (EK / KIT_FARM).read_text()
    new = text.replace(f'blob_dir_name = "{KIT_JOB}"', f'blob_dir_name = "{job}"')
    if new == text:
        raise RuntimeError(f"{KIT_FARM}: its job id line has changed; update ek.farm_script")
    (WORK / f"farm_{job}.py").write_text(new)
    return f"work\\farm_{job}.py"


def bake(scenario, bsp_name, quality, job=KIT_JOB, log="lightmap.log"):
    """The light bake (faux_data_sync, then dillum, pcast, radest, extillum and
    fgather on every core, then the compression steps): (exit code, last lines).
    Its stage logs go to faux\\<job>\\logs; never run two bakes at once."""
    script = farm_script(job)
    with open(WORK / log, "w") as f:
        # the Windows launcher; a WSL shell without Windows folders on its PATH finds it by path
        py = shutil.which("py.exe") or str(env.PY_LAUNCHER)
        r = subprocess.run([py, "-3", script, scenario, bsp_name, quality], cwd=EK,
                           stdout=f, stderr=subprocess.STDOUT)
    tail = (WORK / log).read_text(errors="replace").splitlines()[-8:]
    return r.returncode, tail

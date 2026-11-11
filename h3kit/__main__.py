"""python3 -m h3kit [maps/<map>]: what this machine has for building maps, and,
given a map folder, that map's project and donors."""

import shutil
import sys

from . import env, ek


def row(label, path, ok=None, fix=""):
    ok = path.exists() if ok is None else ok
    print(f"  {'ok ' if ok else 'MISSING'}  {label:28s} {path}" + ("" if ok or not fix else f"\n           -> {fix}"))
    return ok


def main(argv):
    print("h3kit setup (override paths in local_paths.json or H3KIT_* variables; see h3kit/env.py)")
    good = all([
        row("Halo 3 Editing Kit", env.EK, fix="Steam: Halo 3 Mod Tools - MCC (app 1695791)"),
        row("  extracted tags", env.EK / "tags" / "globals", fix='run "H3EK (Extract).bat" in the kit folder'),
        row("  tool_fast.exe", env.EK / env.TOOL),
        row("  mbedit.exe", ek.MBEDIT, fix="tools/mbedit/build.sh"),
        row("MCC Halo 3 maps", env.MCC_MAPS / "sidewinder.map", fix="install Halo 3 in MCC"),
        row("Windows Python launcher", env.PY_LAUNCHER, ok=bool(shutil.which("py.exe")) or env.PY_LAUNCHER.exists(),
            fix="install Python for Windows (the light bake runs the kit's farm script)"),
    ])
    print("optional:")
    from .donor import HGPORT
    row("hgport.exe (donor ports)", HGPORT / "hgport.exe", fix="tools/hgport/build.sh (needs the .NET SDK)")
    row(".NET SDK", env.DOTNET)
    row("Excession", env.EXCESSION, fix="Steam: Excession (app 1695795), the Workshop uploader")
    if env.RECLAIMER:
        row("Project Reclaimer client", env.RECLAIMER_EXE)
        row("Reclaimer user folder", env.RECLAIMER)
    else:
        print(f"  --   {'Project Reclaimer':28s} not installed: not needed for MCC "
              "(release fills the Excession upload folder only)")
    if argv:
        from .project import load
        p = load(argv[0])
        print(f"map {p.name}: scenario {p.scenario}, level {p.bsp}, map id {p.map_id}, base {p.base.scenario}")
        row("  package", p.package_dir)
        row("  last bake's stamp", p.light_stamp, fix="a full build records it (needed for --reuse-light)")
        for d in p.donors:
            row(f"  donor {d.key}", d.map_path, fix=f"subscribe to Workshop item {d.workshop_id}" if d.workshop_id else "")
    sys.exit(0 if good else 1)


if __name__ == "__main__":
    main(sys.argv[1:])

# Tools: what each one does

Everything used to build, package and inspect a map, with paths. How the pieces fit together: [the toolkit's README](../h3kit/README.md).

## Paths

`h3kit/env.py` holds them all (`python3 -m h3kit` checks them). Override any in `local_paths.json` at the repository root or with `H3KIT_*` environment variables, e.g. for a Steam library on another drive.

| What | Default Windows path (WSL: `/mnt/c/...`) |
| --- | --- |
| Halo MCC | `C:\Program Files (x86)\Steam\steamapps\common\Halo The Master Chief Collection` (stock maps in `halo3\maps`, e.g. `sidewinder.map`, Avalanche) |
| Halo 3 Editing Kit (H3EK) | `C:\Program Files (x86)\Steam\steamapps\common\H3EK` (Steam app 1695791, "Halo 3 Mod Tools - MCC") |
| Excession (Workshop uploader) | `C:\Program Files (x86)\Steam\steamapps\common\Excession` (Steam app 1695795) |
| Workshop downloads | `C:\Program Files (x86)\Steam\steamapps\workshop\content\976730\<item id>\` |

## Scripts

Run from the repository root, in WSL. `<map>` is a map folder such as `maps/example`.

| Script | What it does |
| --- | --- |
| `python3 -m h3kit [<map>]` | Checks the machine's setup (kit, extracted tags, mbedit, hgport, MCC, the Windows Python launcher...) and, given a map, its package, light stamp and donors. |
| `python3 -u <map>/build.py ...` | The build driver (`h3kit/build.py`): level, layout, light bake, map, donor ports, package copy. `--light draft/low/medium/high/none`, `--reuse-light`, `--no-build`, `--plan-only [--script-out X]`. |
| `python3 -m h3kit.package <map> meta` | Writes `ModInfo.json` and `multiplayer/<name>.json` into the map's package from its `project.py` (`Mod`: GUIDs, Workshop id, version, title, description). |
| `python3 -m h3kit.package <map> images` | The Workshop images (large, thumbnail, loading screen), without text, from the map's `images.ART` (or its `scene()` fallback). |
| `python3 -m h3kit.package <map> release [--yes]` | Syncs the package into the Excession upload folder (`Mod.upload_dir`); a dry run without `--yes`. |
| `python3 -m h3kit.pack packs/<pack> build-shared\|build\|release` | A map pack: several maps in one mod, optionally built against one `shared.map` of their own. |
| `python3 -m h3kit.strip <folder>` | Shrinks a shared pack's maps: drops chosen bitmaps' top mips. |
| `python3 -m h3kit.catalog` | The prop catalog: checks every tag is in the kit and prints the table. |
| `python3 -m h3kit.bsp_terrain [map] [out.png]` | A stock map's ground from its BSP collision, as a picture. |

### Trying lighting in minutes

`h3kit.lighting_test` compiles a small test level, bakes it as its own job (222, never a real build's 111; the bake script is the kit's own with the job id changed) and prints the median light on each per-vertex measuring floor (`floor_grid`), with an estimate for a medium bake. About 5 minutes at draft. Reference: sunlit ground measures about 1.48 at medium. Don't run it during a real bake.

## `tools/mbedit/`: the tag editor

`mbedit.cs` is the source of `H3EK\work\mbedit.exe`, built with ManagedBlam by `tools/mbedit/build.sh` (the .NET Framework 4 compiler that ships with Windows; it compiles to a scratch name first, so a failed compile keeps the working exe). Run it with the kit as the working directory:

```
work\mbedit.exe "<H3EK folder>" work\<script>.txt
```

A script is one command per line, fields separated by tabs: `load`, `new`, `saveas`, `save`, `dump` (shows at most 2 block elements), `count`, `add`, `remove`, `clear`, `set`, `copyfrom` (copy a field tree from another tag) and `bspdump` (dump a BSP's collision for the layout's checks). An unknown field or enum value prints the valid choices. It can die without a message, on a block past its maximum for example; `h3kit.ek.mbedit` then reports the script line it reached. The script language, field paths and value formats: [h3ek.md](h3ek.md#5-mbedit).

`dump_tag.ps1` prints a tag's field tree through ManagedBlam from PowerShell.

## `tools/hgport/`: tags from one built map into another

A console build of Assembly's Blamite library (XboxChaos/Assembly, GPLv3, vendored in `vendor/` with Assembly's Halo3MCC and Halo3 plugins). It does what Assembly's GUI does for "Extract" then "Import" (same code path, the GUI's default inject settings), without the GUI. `h3kit/donor.py` uses it to bring a donor map's vehicles into the built map.

`tools/hgport/build.sh` copies the sources to `H3EK\work\hgport` and builds `bin\hgport.exe` with the Windows .NET SDK (.NET Framework 4.8 target, x64), in about 15 s. Run it from `bin\` (it reads `Formats\` and `Plugins\` there) with Windows paths:

| Command | What it does |
| --- | --- |
| `hgport info <map>` | The engine Blamite matches (a map built with the kit: "Halo 3 MCC Toolset Update 9"), tag count. |
| `hgport list <map> <group>` | Tag names of a group. |
| `hgport extract <src> <out.tagc> <MCC halo3\maps> [--existing <dst>] <group:path>...` | Tags with everything they reference (tags, resource pages, predictions, sound gestalt entries) into a tag container. `--existing`: tags the destination has (same group and name) go in as a name only. |
| `hgport inject <dst> <in.tagc>` | Into a map, in place. Tags the map already has by name are reused, not overwritten. About a minute for a dozen vehicles. |
| `hgport rename <map> <group:path> <new path>` | Renames a tag, so a following injection brings in a replacement under the old name. |
| `hgport compare <a.tagc> <b.tagc> [names]` | Tag by tag: data bytes, pointed-to blocks, tag references by name, string ids by text, resources by type, definition and page bytes. Exit code 4 when anything differs. |
| `hgport fsb <in.tagc>` | Sound counts and the FMOD bank suffixes they name. |

Work files go in `H3EK\work\hgport\out`.

## Reading built maps

| Module | What it does |
| --- | --- |
| `h3kit/cache.py` | Reads and patches Halo 3 MCC cache files (version 13). |
| `h3kit/cache_resources.py` | The cache's resource system: zone gestalt, play layout, deflate pages. |
| `h3kit/bsp_terrain.py` | A stock map's ground from its BSP's collision geometry. |

The formats are documented in [halo3-formats.md](halo3-formats.md).

## Halo 3 Editing Kit

Run tools with H3EK as the working directory. Use `tool_fast.exe`, not `tool.exe`. Run it with no arguments for the full command list. The details are in [h3ek.md](h3ek.md).

| Command | Use |
| --- | --- |
| `tool_fast structure "levels\...\structure\x.ASS"` | Compiles a level `.ASS` (relative to `data\`) into `.scenario_structure_bsp` and `.scenario_structure_lighting_info`. Creates a scenario too if none exists, which is how test levels are made. About 25 s for a small test level; longer for a real one. |
| `tool_fast build-cache-file <scenario> pc` | Builds `maps\<name>.map`. About 4 min. |
| `tool_fast export-tag-to-xml "<abs tag>" "<abs out>"` | Dumps every field of a tag. Both paths must be absolute Windows paths. This is how field names are learned. |
| `py.exe -3 calc_lm_farm_local.py <scenario> <bsp> <quality> [light group]` | The kit's light bake: `faux_data_sync`, `faux_farm_begin`, then the dillum, pcast, radest, extillum and fgather stages on every core, then `faux_farm_finish` and the compression steps. Quality: draft, low, medium, high, super_slow, direct_only, debug. The job id (`blob_dir_name`, default 111) must be numeric. Logs go to `faux\<id>\logs\<stage><n>.txt`. |
| Guerilla, Sapien | The kit's tag editor and level viewer. Not needed: everything is scripted. |

## Excession

The MCC Workshop uploader; it has a GUI only, so the upload is done by hand. Open the package folder (`Mod.upload_dir`, filled by `release`). If it asks for the Scenario Tag Name, give the scenario's name. It may rewrite `ModInfo.json` with new GUIDs; if so, copy them into the map's `project.py` (`Mod`).

## Logs worth knowing

| Log | What it tells you |
| --- | --- |
| `H3EK\work\structure.log` | `tool structure`: open edges, coplanar faces, bad UVs. |
| `H3EK\work\lightmap.log` | The bake driver's output, with the time of each stage (`*** farm stage: ... ***`). |
| `H3EK\faux\111\logs\dillum0.txt` | The bake's first stage. `container [LIGHT_MAX_INSTANCE] using 0.000008MB` means no lights reached the bake. |
| `H3EK\work\build.log` | `build-cache-file`. `OUT OF MEMORY: object_header_new failed` lines mean the level's objects overflow the object pool, which the game has too: on MCC those objects won't be created in game (see [runtime-limits.md](runtime-limits.md); `--plan-only` shows the budget); "missing scenario resource" warnings for lights and structure lighting are expected too. |
| `H3EK\work\<name>_light_stamp.json` | What the map's last bake was made from (for `--reuse-light`). |
| `H3EK\work\<name>.txt`, `<name>_collision.txt` | The last build's mbedit script and the level's collision dump. |

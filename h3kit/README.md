# h3kit: building Halo 3 (MCC) multiplayer maps from code

`h3kit` builds a Halo 3 (MCC) multiplayer map with the Halo 3 Editing Kit from Python. It contains everything such a map needs that isn't specific to one map:

- the paths and the kit's tools;
- placements and the scenario edit;
- closed meshes and the level's `.ASS`, with lights;
- the light bake, and reusing it;
- static props as machines, the object-memory budget, decorators and a catalog of stock props;
- vehicles ported from other mods' built maps;
- the Workshop package.

A map is a folder under `maps/` that configures it. [`maps/example`](../maps/example/README.md) is the smallest complete map: copy it to start a new one.

## Setting up a machine

WSL on Windows, with:

- MCC with Halo 3;
- the Halo 3 Editing Kit, with its tags extracted (`H3EK (Extract).bat`);
- Windows Python, for the kit's bake script;
- Python 3 in WSL with `numpy` and `Pillow`.

Then:

```bash
tools/mbedit/build.sh        # the tag editor, into H3EK\work (once)
tools/hgport/build.sh        # only for maps with donors (needs the .NET SDK)
python3 -m h3kit             # checks all of it; add a map folder to check that map too
```

Paths default to a standard Steam install on C:. Override them in `local_paths.json` at the repository root (keys in `h3kit/env.py`) or with `H3KIT_*` environment variables.

## How a map fits together

| Piece | Where | What it is |
| --- | --- | --- |
| `project.py` | the map's folder | A `Project`: the scenario name and tag folders, the stock map it starts from (`BaseMap`; `bases.SIDEWINDER` is Avalanche), the map id, donors, budgets, and the Workshop metadata (`Mod`). It calls `use()`, and every other module imports it first. |
| `build.py` | the map's folder | A `build.Map` subclass (write the level, the terrain, the plan, and optionally tag scripts, scenario lines, split resources, a structure design (`design`) and cubemap points (`cubemap_points`)), then `build.main(MAP)`. |
| a level writer | the map's | Meshes (`mesh.Part`, `mesh.Frame`), ground (`ass.ground_tiles`), the structure (`ass.sky_box`), lights (`ass.fixture_lights`), all written by `ass.write`. |
| a look | the map's `look.py` | `SHADERS`, `UV_REPEAT`, `GROUND_UV`, `LIGHTING` (`look.emissive`), `FIXTURES`; plus tag recipes from `h3kit.look` (copied shaders, atmosphere, sky, cluster data). |
| a plan | the map's | A `scenario.Plan` subclass whose `build()` fills `items` with `Placement`s: `put`, `vehicle`, `weapon`, `equipment`, `spawn`, `teleporter`, `prop` (any tag; static scenery becomes machines), `ramp`. A placement's `games` (game engine flags, `scenario.ENGINE` bits) limits it to those game types; 0 is every type, `scenario.NOT_INFECTION` every type but Infection. |
| donors | the map's | `donor.Donor(...)` per mod to take vehicles from, listed in the project. |

The build (`h3kit/build.py`) then does the rest:

1. Compile the level.
2. Dump its collision.
3. Lay it out.
4. Write the scenario script: tag scripts first, then copies of the base map's scenario and split resources holding the new placements.
5. Bake the light.
6. Build the `.map`.
7. Check the placements.
8. Port the donors.
9. Copy the map into the package.

It takes the same command line for every map:

```bash
python3 maps/<map>/build.py --plan-only [--script-out x.txt]   # no kit changes: layout, budgets, memory, reuse check
python3 -u maps/<map>/build.py --light draft                   # full build, quick bake
python3 -u maps/<map>/build.py --light medium                  # full build for release
python3 -u maps/<map>/build.py --reuse-light                   # objects only, keeps the last bake
python3 -m h3kit.package maps/<map> meta|images|release [--yes]
python3 -m h3kit.pack packs/<pack> build-shared|build|release [--yes]   # map packs (shared: their own shared.map)
```

## Starting a new map

1. `cp -r maps/example maps/<new>` and delete its `ground.npz`.
2. In `project.py`, set a new `name`, `level_dir`, `map_id` and `Mod` (new GUIDs: `python3 -c "import uuid; print(uuid.uuid4())"`). Two maps with the same names overwrite each other's tags in the kit.
3. Shape the level (`level.py`) and the layout (`ExamplePlan.build` in `build.py`). Check them with `--plan-only` and the level writer's own run, which needs no kit.
4. Build with `--light draft` for a first look, then try lighting on a small test level (`lighting_test.floor_grid` and `run`) before a `--light medium` build. A full bake of a big level takes over an hour and uses every core.
5. Give it a package: `python3 -m h3kit.package maps/<new> meta`, an `images.py` with `ART` (and an optional `scene(w, h)` fallback), then `images`. Upload the folder with Excession; a `Mod.upload_dir` lets `release` fill it.

## Modules

| Module | What it does |
| --- | --- |
| `env.py` | Machine paths (kit, MCC, Workshop, .NET, optionally Reclaimer), WSL to Windows paths (`win`). |
| `project.py` | `Project`, `BaseMap`, `Mod`; `use()`, `active()`, `load(map folder)`. |
| `bases.py` | Known stock base maps: `SIDEWINDER` (Avalanche), with its leftover objects, kill volumes and the Forge entries it lacks. |
| `ek.py` | `tool`, `mbedit` (exits with the failing line), `export_xml` / `export_cached`, `tag_exists`, `bake` (the kit's farm script, any job id). |
| `stock.py` | Stock tags by name: gameplay pieces, vehicles (with resting heights and footprints), weapons, equipment; teams; priorities. Donors add their vehicles here. |
| `scenario.py` | `Placement`, `Plan`, `stock_state`, `script` (the placement blocks, palettes and Forge palette), `number_mv`, `built_counts`. |
| `collision.py` | Reads `mbedit bspdump`; the engine's point tests (`standing_room`, `blocked_teleporters`). |
| `terrain.py` | `Heightfield`: heights on a grid, read as the mesh triangulates them. |
| `mesh.py` | Closed shells: `Part` (box, ramp, ngon, prism, loft, arc walls), `Frame`, `check` (coplanar overlaps). |
| `ass.py` | The `.ASS` writer, `ground_tiles` from a heightfield, `sky_box`, `fixture_lights`. |
| `lights.py` | One generic light per light fixture, indoor first, capped; scaled for the bake's quality (`QUALITY`). |
| `look.py` | `emissive` strings; tag recipes: copied terrain shaders, atmosphere, a trimmed sky, cluster data. |
| `machines.py` | Static scenery and crates as device machines, which take no map-variant slot. |
| `jms.py` | The JMS 8213 writer (one-node static models): render triangles, closed collision boxes, physics box primitives. |
| `props.py` | Imported props: a textured OBJ (Z up, metres, front -y) becomes bitmaps, shaders, render/collision (and physics) models through `tool render`/`collision`/`physics`, a model and a scenery or crate tag cloned from stock ones. |
| `design.py` | The structure design `.ASS` (`tool structure-design`): soft ceilings (`+soft_ceiling:<name>` faces) and water physics volumes (`~<name>` convex instances). |
| `object_memory.py` | Bytes of object pool per placement (the engine's formula), `plan_bytes`, `report`. |
| `decorators.py` | Decorator placements (`Scatter`, `mirrored`) and the resource lines that carry them; the map's own sets (`tag_script`). |
| `catalog.py` | About 100 real Halo 3 props with bounds, collision and motion type (`python3 -m h3kit.catalog`). |
| `donor.py` | `Donor`: vehicles and crates from another built map (placeholders, then `tools/hgport`), with checks, seat fixes and sound banks. |
| `build.py` | `Map`, `Builder`, `main`: the build, `--reuse-light`, `--plan-only`. |
| `lighting_test.py` | Measuring floors, a test bake (job 222) and the light per floor. |
| `package.py` | ModInfo and map JSON, Workshop images, `release` to the Excession upload folder. |
| `pack.py` | Map packs: several projects' maps in one mod; a shared pack (`Pack(shared=True)`) rebuilds them with the kit's shared build (`build_shared`, steps 3-13 for its scenarios only, never deleting a built map) and ships its own `halo3\maps\shared.map`. |
| `strip.py` | `strip`, `verify`: drop chosen bitmaps' top mips (the armour's, `ARMOR`) from a shared pack's `shared.map` and repoint its maps; `Pack.strip_highres` runs it after `build_shared`. |
| `cache.py`, `cache_resources.py`, `bsp_terrain.py` | Reading (and patching) built `.map` files: tags, resources, a stock map's collision ground. |

## Things to know

- **One map per process.** The active project, the donors' vehicles in `stock`, the machines handed out and `lights.QUALITY` are module state. A script works on one map.
- **Byte-stable output.** The same code and inputs give the same `.ASS` and script byte for byte: the seeds come from the project (`map_id`) and from constants. `--reuse-light` depends on this, since it compares the regenerated level's hash with the bake's.
- **The engine's limits** (map-variant slots, machines, respawn tracking, object memory, network entities) are in [docs/runtime-limits.md](../docs/runtime-limits.md). The layout has to keep to them; `--plan-only` prints the budgets.
- **Lighting.** The bake finds lights only through the scenario's lighting-info reference, which `build.new_level_edits()` sets. About 15 minutes into a bake, `H3EK\faux\<job>\logs\dillum0.txt` shows `LIGHT_MAX_INSTANCE`: 0.000008 MB means no lights reached it, so stop it.
- **The kit itself** (tool, ManagedBlam, the scenario tag, the build log): [docs/h3ek.md](../docs/h3ek.md). Every tool and log: [docs/tools.md](../docs/tools.md).

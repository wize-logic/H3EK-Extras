# Halo 3 Editing Kit (H3EK): working guide

How `h3kit` uses the Halo 3 Editing Kit to build a standalone Halo 3 MCC multiplayer map from a copy of a stock map's scenario. The examples start from Avalanche (internal name `sidewinder`) and call the new map `my_map`; "the generator" is `h3kit/scenario.py`.

Conventions used below:

- `<EK>` is the kit folder, `C:\Program Files (x86)\Steam\steamapps\common\H3EK` (WSL: `/mnt/c/Program Files (x86)/Steam/steamapps/common/H3EK`).
- Tag paths use backslashes and no extension, plus the extension as a separate word (`levels\dlc\sidewinder\sidewinder scenario`).
- Items marked **(unverified)** were noted once and not re-checked against the kit.

Related file: [halo3-formats.md](halo3-formats.md) covers the compiled `.map` format and the terrain reader.

## 1. Installing and extracting

1. Install Steam app 1695791, "Halo 3 Mod Tools - MCC". It lands in `<EK>`.
2. The install ships `H3EK.7z` (about 7.4 GB packed, about 29 GB unpacked, 57,706 files) and `H3EK (Extract).bat`, which runs `bin\x64\7zr.exe x H3EK.7z`. Nothing is extracted automatically, so tool updates never overwrite your edits (`README_MODDING.txt`).
3. Run `H3EK (Extract).bat`. This creates `tags\` and `data\`.
4. The Workshop uploader, "Halo MCC Mod Uploader" (Steam app 1695795), is a separate install at `...\steamapps\common\Excession`.

The extracted tags include Avalanche in full: `tags\levels\dlc\sidewinder\` holds `sidewinder.scenario`, `sidewinder.scenario_structure_bsp` (about 57 MB), `sidewinder.scenario_lightmap_bsp_data`, `sidewinder.scenario_structure_lighting_info`, `sidewinder_design.structure_design`, `sidewinder_faux_lightmap.scenario_lightmap`, cubemap and lightmap bitmaps, `sky\`, `decorators\`, and so on. There is no raw source geometry (`.ASS` / `.JMS`) for Avalanche.

## 2. Folder layout

Top level of `<EK>` (as listed on disk):

| Path | Purpose |
|---|---|
| `tool.exe`, `tool_fast.exe` | Command-line build tool (see section 3) |
| `guerilla.exe`, `sapien.exe`, `halo3_tag_test.exe`, ... | Tag editor, world editor, test runtimes (not needed: everything is scripted) |
| `tags\` | Source tags (after extraction) |
| `data\` | Source data. In the shipped kit this only holds HaloScript sources (`data\levels\...`) |
| `maps\` | Build output of `tool build-cache-file` (`my_map.map` is here) |
| `bin\` | Kit binaries, including `bin\ManagedBlam.dll` and `bin\x64\7zr.exe` |
| `reports\`, `temp\`, `crash_report\`, `error_snapshot\` | Logs and crash dumps |
| `work\` | Created by `h3kit` (not part of the kit) |

`<EK>\work\` holds:

| File | What it is |
|---|---|
| `mbedit.exe`, `mbedit.cs`, `ManagedBlam.dll` | The compiled editor and a copy of the DLL beside it |
| `<name>.txt` | The generated mbedit script of the last build |
| `build.log` | Output of the last `tool build-cache-file` |
| `sidewinder_scenario.xml` | `export-tag-to-xml` dump of the stock scenario; the best reference for field names |

Key tag locations:

- Stock scenario: `tags\levels\dlc\sidewinder\sidewinder.scenario`
- New scenario (written by mbedit): `tags\levels\dlc\my_map\my_map.scenario`
- Build output: `maps\my_map.map` (about 1.1 GB, standalone)

Repository files: `tools/mbedit/mbedit.cs` (the editor), `h3kit/scenario.py` (placements and the script writer), `h3kit/build.py` (the build driver).

## 3. tool.exe

Run from `<EK>` as the working directory. Use `tool_fast.exe`, the optimized build; `tool.exe` is the slower debug build. Running `tool.exe` with no arguments prints every command.

### 3.1 Commands that worked

| Command | Syntax | Notes |
|---|---|---|
| `build-cache-file` | `tool build-cache-file levels\dlc\my_map\my_map pc` | Writes `maps\<name>.map`. Takes about 3.5 minutes (log shows total time 188.8 s) for a 1.1 GB map. Platform argument is `pc`. Ends with `successfully built cache file.` |
| `export-tag-to-xml` | `tool export-tag-to-xml <abs tag file> <abs output file>` | Both paths must be absolute, and the tag path must include the extension and sit inside `tags\`. Otherwise it fails with "Input tag path is not located in the tags directory structure". Output lists every field with name, value and type, plus block counts. This is how a tag's layout is learned. Example: `tool.exe export-tag-to-xml C:\...\H3EK\tags\levels\dlc\sidewinder\sidewinder.scenario C:\...\H3EK\work\sidewinder_scenario.xml` |
| `export-structure-mesh-obj` | `tool export-structure-mesh-obj <scenario>` | Prints an OBJ to stdout. Positions and faces only: 414,550 vertices and 354,686 faces for Avalanche, no UVs, no materials. Not usable to round-trip textured terrain |

### 3.2 Commands that failed or are limited

| Command | Problem |
|---|---|
| `export-structure-mesh` | Crashes: "not implemented for d3d11" |
| `patch-tag-field-batched <file>` | Works, but only sets existing fields; it cannot add block elements. Lines are TAB-separated: `<tag file relative path incl. extension>`, `<field path>`, `<value>`. Field paths look like `scenario_struct_definition[0].map id`. An unresolvable path prints every available path (about 65k lines for a scenario). This is why mbedit was written |

### 3.3 Other commands h3kit runs

`structure <ass>` (`h3kit/build.py`: a level `.ASS` into a structure BSP and its lighting info), `structure-design <ass>` (`h3kit/design.py`), `bitmaps`, `render`, `collision` and `physics` on a data folder (`h3kit/props.py`), `cubemaps`, and the `build-cache-file-*` steps of the kit's shared build (`h3kit/pack.py`). The light bake is the kit's `calc_lm_farm_local.py` (`h3kit.ek.bake`). Not tried: `bulk-import-crates`, `bulk-import-scenery`, `fbx-to-ass`, `fbx-to-jms`, `scenario-analyze`, `verify-tag-load`, `print-tag-to-xml`.

## 4. ManagedBlam

ManagedBlam is the kit's .NET API for editing tags (`<EK>\bin\ManagedBlam.dll`, namespaces `Bungie` and `Bungie.Tags`).

### 4.1 What works

- Initialise with `ManagedBlamSystem.InitializeProject(InitializationType.TagsOnly, ekPath)`. This is what `mbedit.cs` calls.
- Load, create, save and save-as tags: `new TagFile(TagPath.FromPathAndExtension(path, ext))`, `TagFile.New`, `Save`, `SaveAs`.
- Walk fields via `tag.Fields`; types used by mbedit: `TagFieldBlock` (`Elements`, `AddElement`, `RemoveElement`, `RemoveAllElements`), `TagFieldStruct`, `TagFieldArray`, `TagFieldReference` (`Path`), `TagFieldEnum` (`Value`, `Items` with `EnumIndex` / `EnumName`), `TagFieldFlags` (`RawValue`, `Items`), `TagFieldBlockFlags` (`Value`), `TagFieldBlockIndex` (`Value`), `TagFieldElement` and `TagFieldElementArray` (`GetStringData` / `SetStringData`).

### 4.2 What does not work

- `ManagedBlamSystem.Start(...)` throws `NotImplementedException` in this build. Use `InitializeProject`.
- Hosting ManagedBlam in PowerShell crashed when a scenario was loaded (assertion `port_64.h #117 result < 1ull<<32`; crash report written to `<EK>\crash_report`), and it hangs on assert dialogs.
- A compiled x64 C# console exe works, so `h3kit` uses `mbedit.exe`. Build with the platform forced to x64.

### 4.3 Why a compiled exe

PowerShell loads managed code in a way that triggers the 64-bit pointer assertion above. A plain x64 .NET Framework exe does not. A side benefit: a single exe with a line-based script language lets Python generate thousands of edits and run them in one process (one scenario load, one save).

## 5. mbedit

Source: `tools/mbedit/mbedit.cs` (about 350 lines; built by `tools/mbedit/build.sh`). Scripted tag editor over ManagedBlam.

### 5.1 Building

```
C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe /nologo /platform:x64 /out:mbedit.exe /r:"<EK>\bin\ManagedBlam.dll" mbedit.cs
```

Put `mbedit.exe` in `<EK>\work\` with a copy of `ManagedBlam.dll` beside it. `tools/mbedit/build.sh` does both.

### 5.2 Running

Run with the working directory set to `<EK>`:

```
work\mbedit.exe "C:\Program Files (x86)\Steam\steamapps\common\H3EK" work\my_map.txt
```

Arguments: the kit folder, then the script file. Exit code 1 and `line N: <message>` on stderr at the first error; the tag is not saved unless the script reached `save` / `saveas`.

### 5.3 Script language

One command per line, fields separated by TAB. Blank lines and lines starting with `#` are skipped.

| Command | Arguments | Effect |
|---|---|---|
| `load` | `<tag path>` TAB `<extension>` | Open an existing tag |
| `new` | `<tag path>` TAB `<extension>` | Create a blank tag in memory |
| `saveas` | `<tag path>` TAB `<extension>` | Write the tag to a new path |
| `save` | | Save in place |
| `dump` | `<field path>` [TAB `<depth>`] | Print fields. An empty path dumps the whole tag. Default depth 2. Blocks print their count and the first two elements |
| `count` | `<block path>` | Print the number of elements |
| `add` | `<block path>` | Append an element; prints its new index |
| `remove` | `<block path>` TAB `<index>` | Remove one element |
| `clear` | `<block path>` | Remove all elements |
| `set` | `<field path>` TAB `<value>` | Set a field. A missing value (trailing TAB, or none) is the empty string |
| `copyfrom` | `<src tag>` TAB `<src ext>` TAB `<src field path>` TAB `<dst field path>` [TAB `skip,field,names`] | Copy a struct, block or field from another tag, name by name |
| `bspdump` | `<structure bsp tag>` TAB `<output file>` | Write a structure BSP's collision (and its instanced geometry's) for `h3kit.collision.load_collision`; does not touch the open tag |

Only one tag is open at a time; `load` / `new` disposes the previous one.

### 5.4 Field path syntax

- Names are joined with `/`, matched case-insensitively against the field names shown by `export-tag-to-xml` (spaces included), for example `object data/position`.
- `block[i]` selects an element of a block, for example `crates[12]/object data/placement flags`.
- Structs are entered by their name (`object data`, `object id`, `multiplayer data`).
- Arrays can be indexed the same way.
- A wrong name prints the list of valid names at that level, so discovery is easy.
- A path ending at a block (no index) is what `add`, `count`, `clear`, `remove` need, e.g. `crates`.
- Palette elements appended with `add` get the next index; the script generator tracks the counts itself (`h3kit/scenario.py` reads them from the XML export).

### 5.5 Value formats

| Field type | Value to write |
|---|---|
| Tag reference | `path,extension`, e.g. `objects\vehicles\hornet\hornet,vehicle`. Empty value clears it |
| Enum | Item index or item name (case-insensitive). A bad name throws and prints all valid items: handy for discovery |
| Flags (word / long / byte) | Number, decimal or `0x` hex (raw value) |
| Block flags | Number, decimal or `0x` hex |
| Block index (short block index) | Integer; `-1` means none |
| Strings (string id), integers, reals | Plain text |
| Vectors, points, euler angles | Comma-separated, no spaces: `x,y,z` (rotation is yaw,pitch,roll in degrees) |
| Struct arrays of values | Comma-separated |

### 5.6 Example script

The shape of a generated script (lines shortened):

```
load	levels\dlc\sidewinder\sidewinder	scenario
set	map id	9000
set	structure bsps[0]/structure design	
set	trigger volumes[2]/name	open_zone
set	crates[0]/object data/placement flags	0x8
add	mv vehicle palette
set	mv vehicle palette[16]/name	objects\levels\multi\shrine\behemoth\behemoth,vehicle
set	mv vehicle palette[16]/display_name	elephant
set	mv vehicle palette[16]/maximum allowed	32
set	mv vehicle palette[16]/price per instance	10
add	crates
set	crates[91]/type	7
set	crates[91]/name	-1
set	crates[91]/object data/placement flags	32
set	crates[91]/object data/position	125.0000,-30.0000,12.3000
set	crates[91]/object data/rotation	180.000,0.000,0
set	crates[91]/object data/object id/unique id	123456789
set	crates[91]/object data/object id/origin bsp index	-1
set	crates[91]/object data/object id/type	crate
set	crates[91]/object data/object id/source	editor
set	crates[91]/object data/editor folder	-1
set	crates[91]/multiplayer data/owner team	defender
saveas	levels\dlc\my_map\my_map	scenario
```

(The index 91 and the palette index 7 are illustrative: the stock scenario has 91 crates; real indices come from the palette bookkeeping in `h3kit/scenario.py`. The real script edits copies of the split resources too: see 6.5.)

## 6. The scenario tag

Group `scnr`, extension `scenario`. The stock file is `levels\dlc\sidewinder\sidewinder`, field `map id` = 470, `sandbox budget` = 4500, `type` = multiplayer.

### 6.1 Placement blocks

Block names for placed objects: `scenery`, `crates`, `vehicles`, `weapons`, `equipment` (and others). Each has a matching palette block: `scenery palette`, `crate palette`, `vehicle palette`, `weapon palette`, `equipment palette`. A placement's `type` is an index into its palette; a palette entry's `name` is a tag reference. The generator appends palette entries on demand.

Element fields (from `sidewinder_scenario.xml`, crate element):

| Path | Type | Notes |
|---|---|---|
| `type` | short block index | Palette index |
| `name` | short block index | Index into the scenario's object names; `-1` for none. Stock flag crates have named objects (e.g. "ctf atk flag") that scripts reference |
| `object data/placement flags` | long flags | See 6.3 |
| `object data/position` | real point 3d | x,y,z, world units |
| `object data/rotation` | real euler angles 3d | Degrees. The generator writes `yaw,pitch,0` |
| `object data/scale` | real | 0 means 1 |
| `object data/object id/unique id` | long integer | Random positive integer in the generator |
| `object data/object id/origin bsp index` | short block index | `0` for scenery, `-1` for others in the generator; stock crates show -1, stock scenery shows 0 |
| `object data/object id/type` | char enum | `crate`, `scenery`, `vehicle`, `weapon`, `equipment` |
| `object data/object id/source` | char enum | `editor` |
| `object data/editor folder` | short block index | `-1` for none |
| `object data/bsp policy`, `transform flags`, `manual bsp flags`, `can attach to bsp flags`, `parent id/*` | various | Left default |
| `permutation data/*` | struct | Variant name and four colors; default |
| `multiplayer data/game engine symmetric placement` | long enum | `ignore`, `symmetric`, `asymmetric` (unverified) |
| `multiplayer data/game engine flags` | word flags | 0 = all |
| `multiplayer data/owner team` | short enum | `defender`, `attacker`, `third` ... `eighth party`, `neutral`. The generator writes `defender` (red, +x), `attacker` (blue, -x), `neutral` |
| `multiplayer data/spawn order`, `quota minimum`, `quota maximum`, `spawn flags` | ints / byte flags | Default 0 |
| `multiplayer data/spawn time` | short integer | Seconds; the generator sets it for weapons and vehicles |
| `multiplayer data/abandonment time` | short integer | |
| `multiplayer data/remapping policy` | char enum | default `normal-default` |
| `multiplayer data/boundary shape` | char enum | `unused`, `sphere`, `cylinder`, `box` |
| `multiplayer data/teleporter channel` | char enum | `alpha`, `bravo`, ...; the generator writes the channel as a number (red uses 2 and 3, blue 4 and 5) |
| `multiplayer data/boundary width or radius`, `boundary box length`, `boundary positive height`, `boundary negative height` | real | Used by respawn zones and similar |
| `multiplayer data/natural respawn weight` | real | |
| `multiplayer data/map variant parent/*` | struct | Parent object, marker, connection marker |

Vehicle and weapon elements additionally carry `vehicle data` / `weapon data` structs (not edited here).

### 6.2 Enums

Enum item names are case-insensitive. Setting an invalid name makes mbedit print the valid ones, which is how the lists above were gathered. Numeric values also work, but the numbering is not documented here.

### 6.3 Placement flags

Seen on stock objects: `0x20` is "create at rest" (the generator uses this for crates and scenery pieces; vehicles, weapons, equipment and spawns use 0). **Unverified against the kit**: `0x1` not automatically, `0x2` lock type, `0x4` lock transform, `0x8` never placed, `0x10` lock name, `0x20` create at rest, followed by store orientations, pvs bound, startup.

"Never placed" (`0x8`) is how the generator retires stock objects a new level must not create: Avalanche's CTF flag spawns and return areas (crates 0-3) and the stock respawn points at given spots (`scenario.stock_state`). They are not deleted, because the map's HaloScript refers to objects by index.

### 6.4 Palettes versus MV (Forge) palettes

- Regular palettes (`scenery palette`, `crate palette`, ...) list the object tags the scenario's own placements use. Scenery palette: spawn points, initial spawns, respawn zones. Crate palette (`bloc`): CTF flag spawn and return, teleporters, man cannons, Forge boxes and walls.
- MV palettes (`mv vehicle palette`, `mv weapon palette`, and equivalents up to a spawner palette) define the map-variant (Forge) object set: elements have `name` (tag reference), `display_name`, `maximum allowed`, `price per instance`. A scenario object whose tag is not in an MV palette is permanent: the stock man cannons behave that way.
- The generator adds MV entries (maximum 32, price 10) for the vehicles and weapons a project lists (`forge_vehicles`, `forge_weapons`; for Avalanche: elephant, hornet, `warthog_gauss`, `warthog_troop`, `wraith_anti_air`, shade, plasma cannon and flamethrower), so they can respawn.

### 6.5 Split resources: where placements really live

Avalanche's scenario keeps its placements in **split resource tags** in `levels\dlc\sidewinder\resources\`: `sidewinder.scenario_scenery_resource` (blocks `scenerys`, `crates` and their palettes, 175 scenery and 91 crates), `..._vehicles_resource` (`vehicles`), `..._weapons_resource` (`weapons`), `..._equipment_resource` (`equipments`), `..._trigger_volumes_resource` (`trigger volumes`) and others (lights, decals, decorators, cluster data, sky, cubemaps). The scenario points at them through `scenario resources[0]/new split resources[0]/<x> resource`.

`build-cache-file` loads the placements from those resources. **Edits to the placement blocks or trigger volumes inside the `.scenario` itself are ignored**, and the build log shows no error. (The copies in the scenario are stale anyway: 173 scenery against the resource's 175.) A build that edits only the scenario loses every new object and trigger volume rename this way, while its scenario-level edits (map id, structure design, MV palettes) go through.

`h3kit/scenario.py` therefore copies the scenery, vehicles, weapons, equipment and trigger volume resources to `levels\dlc\my_map\resources\my_map.*`, makes the edits there, and points the new scenario's split resource fields at the copies. It also reads the block sizes back out of the built `.map` (`built_counts`) and fails if any are smaller than expected. New placements also set `object data/can attach to bsp flags` = 1, as every stock placement has.

### 6.6 Object ids

`object id/unique id` is a long integer unique per object; the generator uses a seeded RNG (`random.Random(470)`) in `1..2^31-1`. `origin bsp index` ties scenery to BSP 0; `type` and `source` identify the object kind and that it was authored in the editor.

### 6.7 Map id

Give the new map a `map id` of its own (stock Avalanche is 470): no two installed maps may share one. `h3kit` sets it from the project's `map_id`.

## 7. Trigger volumes, kill and safe zones, soft ceilings

### 7.1 Trigger volumes

Block `trigger volumes` (6 elements in stock Avalanche). Each has `name` (string id), `object name`, `node name`, `forward`, `up`, `position` (the corner), `extents`, `kill trigger volume` (a postprocessed short block index) and `editor folder`.

| Index | Name | Corner (x, y, z) | Extents | Role |
|---|---|---|---|---|
| 0 | `kill_volumes_0` | -21.96, -65.55, -76.82 | 47.65, 98.86, 68.67 | Under the valley; slightly rotated (forward 0.9999, -0.0113, 0) |
| 1 | `kill_volumes_1` | -55.85, 46.64, -44.65 | 116.74, 68.02, 36.57 | North abyss |
| 2 | `safe_zone` | -53.79, -46.36, -12.94 | 110.95, 122.43, 31.44 | Playable area inside the horseshoe |
| 3 | `garbage` | -60.42, -14.85, -72.09 | 129.29, 133.43, 42.34 | Below the map (cleanup) |
| 4 | `kill_volumes_2` | -55.15, 65.76, -1.04 | 27.71, 10.80, 20.74 | North cliff edge |
| 5 | `kill_volumes_3` | 40.61, 53.62, -3.77 | 20.61, 23.64, 24.11 | North cliff edge |

The kill and safe-zone lists are built from the names: `build-cache-file` puts a volume whose name starts with `kill` in the scenario's kill trigger volumes, and one starting with `safe_zone` in the safe zones (verified in a built map). A new level needs them out of service: they fit Avalanche's old valley, and lower ground on a new level lies inside the "below the map" kills. `h3kit/bases.py` (`SIDEWINDER.retired_volumes`) renames 0 to `open_valley_0`, 1 to `open_abyss_1`, 2 to `open_zone`, 4 to `open_edge_2` and 5 to `open_edge_3`. `garbage` (3) is kept.

### 7.2 Soft ceilings and the structure design tag

The scenario's own `soft ceilings` block is empty (count 0). The soft ceilings live in the structure design tag, `levels\dlc\sidewinder\sidewinder_design.structure_design` (group `sddt`), under `physics/soft ceilings block`, with a MOPP. Avalanche has three kinds: "slippery" (slip surfaces, 3,116 triangles), "negabyte" (acceleration / push-back, 260 triangles) and a third **(unverified)**.

Clearing the reference removes all of them:

```
set	structure bsps[0]/structure design	
```

(an empty value clears a tag reference). A new level gets its own design from `h3kit/design.py` (soft ceilings and water volumes), or none.

## 8. Available object tags

Names are paths under `tags\` without extension. All piece origins are at the bottom centre of the model.

### 8.1 Sandbox Forge pieces

`objects\levels\dlc\sandbox\<name>\<name>` (crates). Directory contents on disk: `sand_1x1_lilramp`, `sand_2x2_lilramp`, `sand_archtop`, `sand_block`, `sand_block_flat`, `sand_block_large`, `sand_block_ramp`, `sand_block_wittle`, `sand_bridge`, `sand_column_short`, `sand_column_short_red`, `sand_column_tt`, `sand_cylinder`, `sand_cylinder_end`, `sand_cylinder_lturn`, `sand_cylinder_threeway`, `sand_gatehouse`, `sand_large_cube`, `sand_large_cube_pillar`, `sand_large_cubex2`, `sand_large_halfcube`, `sand_large_halfcubex2`, `sand_large_wood_bridge`, `sand_long_cuberamp`, `sand_mast_house`, `sand_pyr_bridge`, `sand_pyr_corner`, `sand_pyr_corner_extender`, `sand_ramp`, `sand_scaffold`, `sand_slant_cube`, `sand_slant_cube_corner`, `sand_small_cuberamp`, `sand_small_wood_bridge`, `sand_wall`, `sand_wall_forge`, `sand_wall_halfdoor`, `sand_wall_lowdoor`, `sand_wall_lsection`, `sand_wall_slit`, `sand_wall_tsection`, `sand_wallx2`, `stone_column_damaged`, `stone_column_short`, `stone_column_tall`, plus `teleporter_2way_sandbox`, `sandbox_defender`, `sandbox_light_blue`, `sandbox_light_red`.

### 8.2 Avalanche pieces

`objects\levels\dlc\sidewinder\`: `fore_wall`, `fore_ramp`, `fore_wallcorner`, `fore_fightposition`, `fore_wall_sheild` (sic), `tower_of_power`, `lift_sidewinder`, `man_cannon_sidewinder_01` to `_08`, `hornet_lite`, `sw_forge_door_lg`, `sw_forge_door_sm`.

Shared: `objects\levels\dlc\shared\man_cannon_forge\man_cannon_forge` (the Forge man cannon), plus shield doors, `water_barrels`, `forge_ball` and others in that folder.

### 8.3 Gameplay objects the generator uses

| Kind | Tags |
|---|---|
| CTF | `objects\multi\ctf\ctf_flag_spawn_point`, `ctf_flag_return_area`, `ctf_initial_spawn_point`, `ctf_respawn_zone` |
| Spawning | `objects\multi\spawning\respawn_point` |
| Start points | Each game type has its own initial spawn point tag, and stock Avalanche puts one of each at every start spot: `objects\multi\koth\koth_initial_spawn_point`, `slayer\slayer_initial_spawn_point` (every Slayer variant, Fiesta included), `infection\infection_initial_spawn_point`, besides CTF's, plus oddball, territories, assault and VIP ones. `stock.INITIAL_PIECES` places the CTF, King of the Hill, Slayer and Infection ones. |
| Teleporter | `objects\multi\teleporter_2way\teleporter_2way` |
| Grav lift (permanent) | `objects\equipment\gravlift_permanent\gravlift_permanent` |
| Powerups | `objects\multi\powerups\powerup_red\powerup_red` (overshield), `powerup_blue\powerup_blue` (camo) |
| Equipment | bubble shield, regenerator, power drain, trip mine, grav lift, instant cover (`_mp`), super flare under `objects\equipment\<name>_equipment\` |

### 8.4 Vehicles

| Key | Tag | Spawn s |
|---|---|---|
| elephant | `objects\levels\multi\shrine\behemoth\behemoth` | 120 |
| scorpion | `objects\vehicles\scorpion\scorpion_snow` | 90 |
| wraith | `objects\vehicles\wraith\wraith` | 90 |
| wraith_aa | `objects\vehicles\wraith\wraith_anti_air` | 90 |
| hornet | `objects\vehicles\hornet\hornet` | 60 |
| banshee | `objects\vehicles\banshee\banshee` | 60 |
| gauss | `objects\vehicles\warthog\warthog_gauss_snow` | 45 |
| troop | `objects\vehicles\warthog\warthog_troop` (no snow variant) | 45 |
| warthog | `objects\vehicles\warthog\warthog_snow` | 45 |
| ghost | `objects\vehicles\ghost\ghost_snow` | 30 |
| mongoose | `objects\vehicles\mongoose\mongoose_snow` | 20 |
| chopper | `objects\vehicles\brute_chopper\brute_chopper` | 30 |
| shade | `objects\vehicles\shade\shade` | 60 |

Pelican, Phantom, Longsword and Covenant cruiser tags also exist but are unused.

### 8.5 Weapons

Under `objects\weapons\`: `rifle\{battle_rifle, covenant_carbine, assault_rifle, sniper_rifle, beam_rifle, shotgun}`, `support_high\{rocket_launcher, spartan_laser, flak_cannon}`, `melee\{energy_blade, gravity_hammer}`, `support_low\{brute_shot, sentinel_gun}`, `turret\{missile_pod, plasma_cannon, flamethrower}`. Each lives at `<dir>\<name>\<name>` with the extension `weapon`. Respawn seconds used by the generator range from 15 (rifles) to 120 (flamethrower).

## 9. Piece bounds

A piece's bounds are `[x0, x1, y0, y1, z0, z1]` in world units: the model-space bounding box relative to the object's origin.

How to measure them: each piece's `render_model` tag has `render geometry/compression info`, with `position bounds 0` (x0, x1, y0) and `position bounds 1` (y1, z0, z1); mbedit's `dump` prints them. The crate's `object/bounding radius` is 0 in tags (computed at build), so it can't be used. `h3kit/catalog.py` holds the bounds of about 100 props.

Selected values (size x, y, z; all origins at bottom centre):

| Piece | x range | y range | z range | Size |
|---|---|---|---|---|
| sand_wall | -0.89 .. 0.911 | -0.099 .. 0.085 | 0 .. 1.794 | 1.8 x 0.18 x 1.79 |
| sand_wallx2 | -1.82 .. 1.788 | -0.092 .. 0.095 | 0 .. 1.794 | 3.61 x 0.19 x 1.79 |
| sand_large_wood_bridge | -2.17 .. 2.159 | -0.907 .. 0.898 | -0.007 .. 0.099 | 4.33 x 1.81 x 0.11 |
| sand_large_cube | -0.923 .. 0.888 | -0.946 .. 0.863 | 0 .. 1.804 | 1.8 cube |
| sand_large_cubex2 | -1.734 .. 1.893 | -0.931 .. 0.873 | 0 .. 1.801 | 3.6 x 1.8 x 1.8 |
| sand_gatehouse | -0.704 .. 0.702 | -0.508 .. 0.507 | 0 .. 3.14 | 1.4 x 1.0 x 3.14 |
| sand_column_tt | -0.307 .. 0.286 | -0.412 .. 0.415 | 0 .. 3.592 | 3.6 tall |
| fore_wall | -0.038 .. 0.042 | -0.886 .. 0.888 | 0 .. 1.803 | 1.77 long along y |
| fore_ramp | -1.0 .. 1.0 | -1.492 .. 2.497 | 0 .. 1.467 | 2 x 4, rises 1.47 along +y |
| tower_of_power | -2.216 .. 2.21 | -2.053 .. 2.213 | 0 .. 1.904 | 4.43 x 4.27 x 1.90 |

Scale reference: 1 world unit is about 10 ft; a Spartan is about 0.7 units tall.

## 10. Building and the build log

Command: `tool_fast build-cache-file levels\dlc\my_map\my_map pc` (section 3). Output goes to `<EK>\maps\my_map.map`; the log is `work\build.log`.

- A 1.1 GB map takes 3 to 4 minutes. The log ends with `total tag size is ...M`, `total time ...` and `successfully built cache file.`
- `h3kit/build.py` treats the build as successful only if "successfully built" appears in the last lines of the log.

Messages seen that do not stop the build:

| Message | Meaning |
|---|---|
| `WARNING did not find .mapinfo file for scenario ...` | Fine; MCC mods use the package's JSON instead |
| `-ERROR- decorators: scenario cannot find decorator set 4 (levels\dlc\sidewinder\decorators\packed_snow\packed_snow) - ignoring placements` | Present on the untouched stock scenario too; harmless |
| Three `-ERROR- (group_postprocessing ...)` lines about animation graphs for `powerup_red`, `gravlift_permanent`, `gravity_hammer` models | A mismatch inside the stock tags, not caused by the scenario edits. The build succeeds; those objects just don't animate |
| `WARNING ... respawn_point ... bounding sphere ...` | Cosmetic |
| `WARNING ... cannot find permutation 'destroyed'/'default'` (ghost, warthog_snow models) | Cosmetic |
| `Property particle_axis_angle uses forbidden state(s)` (warthog destruction effects), sound promotion-rule warnings, `particle system is invalid` | Cosmetic |

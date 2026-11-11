# Engine limits

These are the limits a big map runs into. Most were found by reverse engineering `halo3_tag_test.exe` (H3EK); function addresses are given so they can be found again. `h3kit`'s layout helpers and `--plan-only` report against them.

## Summary

| Limit | Stock Halo 3 | Effect when exceeded |
| --- | --- | --- |
| Map-variant slots: vehicles, weapons, equipment, scenery, crates (machines don't count) | 640 | Release build writes past the slot array into the start-index table: memory corruption. Leave a margin (620, say). |
| Object datums | 2048 | Objects fail to create |
| Object memory pool | 1.5 MB (0x180000) | "OUT OF MEMORY: object_header_new failed"; the object isn't created |
| Network entities | 1024 |  |
| Respawn-tracked objects (candy monitor): vehicles, weapons, equipment, crates with multiplayer properties | 512 | Objects past it exist but never respawn |
| Spawners (candy monitor) | 512 |  |
| Quotas (one per Forge palette entry) | 256 |  |
| Scenario weapon placement block | 128 | mbedit dies without a message adding the 129th |
| Scenario vehicle placement block | at least 256 |  |
| Tag section (header `+0x14`, the tags loaded into memory) | at least 170 MB | `halo3.dll` 0x1800a6250 compares it with its tag memory region and refuses the map: "tag memory size invalid (%u, should be within [0, %u])" |

The build tool (`tool_fast build-cache-file`) keeps the stock 1.5 MB pool and logs OUT OF MEMORY for objects past it. MCC's `halo3.dll` has the same pool, so the objects the tool can't create aren't created in game either, and the players, their weapons, bodies, dropped weapons and projectiles need room in it too. `--plan-only` checks the level against `object_memory.MCC_LEVEL_BUDGET`: the pool less 16 players and about 23.6 KB of headroom each, about 978 KB.

## Tag memory

`halo3.dll` (MCC, 0x1800a619c, which validates a cache header) refuses a map whose header `+0x14` (the tag section's size) exceeds its tag memory region. The region's size is set at run time, so it isn't read statically; the maps that load bound it from below. Stock multiplayer maps reach 71 MB (`sidewinder`), and campaign maps reach 170 MB (`070_waste`) in the same DLL. Tags ported from another map (`h3kit/donor.py`) add to it: tens of megabytes for a set of vehicles.

## Which placements the game creates

Scenario object creation filter: `FUN_140a7af20`, called by `FUN_140a47700` from `FUN_140a7a580` and `FUN_140a7abf0`.

- **Placement flags.** Bit 3 ("never placed") skips the placement. Bit 7 ("editor only") skips it in release builds (`FUN_140148a50` returns 0). Bit 0 is handled by the caller.
- **Symmetric placement.** In the multiplayer data, 1 means only in symmetric games, 2 only in asymmetric games, 0 always.
- **Game engine flags.** A word in the multiplayer data with bits ctf 0, slayer 1, oddball 2, king 3, juggernaut 4, territories 5, assault 6, vip 7, infection 8. 0 means all; otherwise it must include the current engine (`FUN_140602fa0` maps the engine id to its bit).
- **Grenades.** Grenade definitions (globals `+0x41c` block) are skipped if the game variant's "grenades on map" (`+0x130` bit 0) is off.
- **The tag's own multiplayer block.** Its engine flags (`& 0x3ff` nonzero) must include the current engine (`FUN_1403fc480`).
- **Weapon and vehicle sets.** The game variant's sets (`+0x150` weapons, `+0x152` vehicles; `FUN_1403ecfd0`, `FUN_1403ecf20`) remap tags. Remapped to NONE, the object isn't created.
- **Not checked at creation:** quota, maximum allowed, budget and team.

## The map variant

`c_map_variant` is 0xE0A0 bytes. `FUN_1403f6eb0` builds the runtime variant from the scenario.

- **Slots.** Object type mask 0x44e: vehicle, weapon, equipment, scenery, crate, in that order. Each type's start index is the running sum of the scenario block counts, and slot = start + placement index. There is no clamp at 640: `0x130 + 640 * 0x54 = 0xD330` is where the start-index table begins, so overflow corrupts it in release builds. Device machines (type 7) are not in the mask; that is why `machines.py` turns static props into machines.
- **Quotas.** One per MV (Forge) palette entry, max 256, at `0xd34c`. Each is 12 bytes: definition index u32, min u8, max u8, placed u8, maximum allowed u8, price float. Maximum allowed is stored as a u8, so 0 means 255 and 256 becomes 0. Duplicate entries are separate quotas, and the lookup (`FUN_1403f56e0`) returns the first match. Placed tags in no MV palette get a new quota at registration (`FUN_1403fa3d0`).
- **Registration.** Objects are registered only if they have multiplayer properties (object `+0x150 != -1`, `FUN_140a44120`).

## Object memory

The details are in `h3kit/object_memory.py`'s header.

- **Pool and datums.** `objects_initialize` (`FUN_140a51950`) makes the object datum array (0x800) and the "objects" pool (0x180000).
- **What an object costs.** `object_new` (`FUN_140a460a0`) allocates the type struct from the pool, then grows it per block (nodes, regions, attachments, animation, multiplayer object...). Child objects come along: a unit's weapons, and a model variant's objects (Warthog → chaingun turret → chaingun weapon).
- **Failures.** On a failure the tool writes `H3EK\<map>_object_memory<N>.txt`. The build (`h3kit/build.py`) deletes these.

## CTF flags

`verify_state` (`FUN_14078bc60`) creates and deletes flags through the CTF vtable `+0x2d8` (`FUN_14078b410`).

- A team's flag exists only while that team has a player (`game_engine_is_team_active`, `FUN_14042be30`). In a test with one player, only one flag shows. That is not a bug.
- In single-flag mode only the defending team's flag exists; in neutral mode only flag 8.

## Halo 3 tag details found along the way

- **The sky.** Avalanche's sky (`sidewinder` sky render model) includes world-scale regions 0-7: the old valley cliffs, drawn without collision. On a bigger map they show as a rock wall you can walk through. `h3kit.look` has a recipe for a trimmed copy with those regions' mesh index set to -1.
- **Vehicles.** At map start they are physics-asleep: placed too high, they float until something touches them. `h3kit.stock.VEHICLE_REST` holds each one's resting height.
- **The campaign Pelican and Phantom.** They ship with every player-usable seat flagged "invalid for player" (bit 0x10000); a copy with that flag cleared on the pilot, gunner and passenger seats is flyable. The Scarab can't be made drivable this way.
- **Seat animations.** A player in a seat plays the seat's animation mode (`seat animation`, for example `pelican_d`) from the biped's animation graph. The stock Spartan and Elite graphs lack the modes a mod's new vehicles use, so a donor port brings the donor's graphs too (`Donor(replaced=...)`, `donor.PLAYER_GRAPHS`).

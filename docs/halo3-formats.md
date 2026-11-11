# Halo 3 MCC cache format (version 13)

Reference for the cache (`.map`) format read by `h3kit/cache.py`, `h3kit/cache_resources.py` and `h3kit/bsp_terrain.py`. Target build: Update 14 and later, header version 13. Layouts follow Assembly's Blamite `Formats/Halo3MCC/LayoutsU13` and the Halo3MCC plugins. All values are little-endian. Where the code gives an offset, the code's value is used here.

Related: [h3ek.md](h3ek.md) covers the Editing Kit, which builds these files.

## 1. Header

The header is `0x4000` bytes (`HEADER_SIZE`).

| Offset | Type | Meaning |
|---|---|---|
| `0x00` | 4 bytes | Magic `daeh` (reads "head" reversed) |
| `0x04` | i32 | Version, must be 13 |
| `0x20` | 4 x u32 | Tag name table: count, data offset, data size, index offset (debug section offsets) |
| `0x30` | 4 x u32 | String ID table: count, data offset, data size, index offset |
| `0x40` | i32, u32 | String namespace table: count, offset (debug section) |
| `0xC0` | 32 bytes | Internal name (NUL terminated) |
| `0xE0` | 256 bytes | Scenario path (NUL terminated) |
| `0x2E0` | u64 | Virtual base address |
| `0x2E8` | u64 | Tag index virtual address |
| `0x4CC` | 4 x u32 | Section masks |
| `0x4DC` | 4 x (u32, u32) | Sections: (virtual address, size) |

`h3kit.cache.Cache` raises if the magic or version do not match.

## 2. Sections and address translation

- File offset of section i = `(vaddr[i] + mask[i]) mod 2^32`, where `vaddr` is the first value of the section entry and `mask[i]` the matching u32 at `0x4CC`.
- Section indices used: tag section = 2 (`TAG_SECTION`); resource section = 1 (`RESOURCE_SECTION`, in `h3kit/cache_resources.py`). The other two (0 = debug, 3 = unused here) are not decoded by the code.
- Tag data addresses are 64-bit virtual addresses. Pointers inside tag data are 32-bit and stored shifted: the address is `pointer << 2` (`Cache.expand`).
- Tag address to file offset: `offset = address - virtual_base + tag_section_offset`. The result must fall inside `[tag_section_offset, tag_section_offset + tag_section_size)`, otherwise `ValueError`.
- Debug-section offsets (the string and tag-name tables) are `(value + mask[0]) mod 2^32` (`debug_offset`).
- A tag block field is `i32 count` followed by `u32 pointer` (8 bytes). `Cache.block(base, field_offset)` returns `(count, file offset of element 0)` and `(0, None)` for empty blocks.

## 3. Tag index

At the tag index address (`0x2E8` in the header) there is a `0x48`-byte structure read as:

| Offset | Type | Meaning |
|---|---|---|
| `0x00` | i32 | Group count |
| `0x08` | u64 | Groups address |
| `0x10` | i32 | Tag count |
| `0x18` | u64 | Tag table address |

- Group entries are 16 bytes each; the first 4 bytes are the group tag, stored reversed (so `sbsp`, `scnr`, `zone`, `play` appear after reversing).
- Tag table entries are 8 bytes: `i16 group index`, `u16 salt`, `u32 pointer` (expanded with `<< 2`). A negative group index or zero pointer marks an unused slot.
- Datum (tag id) = `(salt << 16) | index`. `tag_by_datum` uses the low 16 bits as the table index; `0xFFFFFFFF` means none.
- Tag names come from the tag-name table at header `0x20`, indexed by tag index.
- `Cache.by_name` maps `(group, name)` to `Tag`; `find(group, name)` looks one up.

## 4. String ids and string tables

Both tables use the same read pattern: header gives (count, data offset, data size, index offset); the index is `count` i32 offsets into the data blob (negative means empty), each pointing at a NUL-terminated latin-1 string.

String id (u32) layout, as implemented in `Cache.string`:

| Bits | Meaning |
|---|---|
| 31..24 | Length of the string (8 bits) |
| 23..21 | Namespace (3 bits) |
| 20..0 | Index within the namespace (21 bits) |

Real table index = `index + sum(namespace_counts[:namespace])`. Special case: for namespace 0, an index at or beyond `counts[0]` maps after all namespaces, to `index - counts[0] + sum(counts)`. Namespace counts are read from the table at header `0x40`. An out-of-range index returns `<sid 0x...>`.

## 5. Scenario (`scnr`) offsets used

Offsets are within the tag's data. Element sizes in parentheses.

| Field | Offset | Element size |
|---|---|---|
| Map id | `0x0C` | (i32) |
| Scenery block / palette | `0xB4` / `0xC0` | `0xB4` |
| Vehicles block / palette | `0xE4` / `0xF0` | `0xA8` |
| Equipment block / palette | `0xFC` / `0x108` | `0x8C` |
| Weapons block / palette | `0x114` / `0x120` | `0xA8` |
| Crates block / palette | `0x5BC` / `0x5C8` | `0xB0` |
| MV palettes | `0x1E0` (vehicle) through `0x228` (spawner) | `0x1C`; maximum allowed at `+0x14`, price at `+0x18` |
| Soft ceilings | `0x234` | `0xC` (flags) |
| Trigger volumes | `0x258` | `0x44`: name sid at start, forward `0xC`, up `0x18`, position (corner) `0x24`, extents `0x30` |
| Kill trigger volumes | `0x484` | short indices |
| Safe zone triggers | `0x490` | |

## 6. Structure BSP (`sbsp`)

- Pathfinding data (block at `0x100`) is empty in MCC caches, which is why terrain is built from collision geometry instead.
- Instanced geometry instances: block at `SBSP_INSTANCES = 0x1C0`, element size `INSTANCE_SIZE = 0x78`. Fields read by `bsp_terrain.py`:

| Offset | Type | Meaning |
|---|---|---|
| `0x00` | f32 | Scale |
| `0x04` | 9 x f32 | Axes: forward, left, up (3 x 3) |
| `0x28` | 3 x f32 | Position |
| `0x34` | i16 | Instance definition index |
| `0x36` | u16 | Flags; bit 1 (`INSTANCE_RENDER_ONLY`) means no collision, skipped |

Transform: `world = definition_triangles @ (scale * axes) + position` (row vectors).

### 6.1 Collision geometry

Collision data is not in the sbsp tag itself; it lives in the BSP's `structure_bsp_tag_resources` resource (section 7). In that resource's definition, at the resource's root structure (`res.base`):

| Offset | Block | Element size |
|---|---|---|
| `0x00` (`TAG_RESOURCES_COLLISION`) | collision bsps | `0x60` (`COLLISION_BSP_SIZE`) |
| `0x18` (`TAG_RESOURCES_INSTANCES`) | instanced geometry definitions | `0xC4` (`INSTANCE_DEFINITION_SIZE`); the instance's collision bsp is at `+0x14` (`INSTANCE_COLLISION`) |

Blocks inside a collision bsp (offsets from its start): planes `0xC`, surfaces `0x3C`, edges `0x48`, vertices `0x54`. Their data lives in the resource's data segment (address kind 2).

| Record | Layout (numpy dtype in `bsp_terrain.py`) | Size |
|---|---|---|
| Surface | u16 plane, u16 first edge, i16 material, i16 set, i16 breakable, u8 flags, u8 best plane | 12 |
| Edge | 2 x u16 vertices, u16 forward, u16 reverse, u16 left surface, u16 right surface | 12 |
| Vertex | 3 x f32 point, u16 edge, u16 sink | 16 |

Surface flag bits: `1 << 0` two-sided, `1 << 1` invisible (`SURFACE_TWO_SIDED`, `SURFACE_INVISIBLE`).

Surface to polygon: starting at the surface's first edge, if the edge's left surface is this surface, take its first vertex and follow `forward`; otherwise take its second vertex and follow `reverse`; stop when the walk returns to the first edge (capped at 64 steps). Polygons with fewer than 3 vertices are dropped, then fan-triangulated.

## 7. Resource system

### 7.1 Zone (`zone`) and play (`play`) tags

`h3kit.cache_resources.Resources(cache)` finds the first `zone` and first `play` tag.

Zone tag (gestalt), offsets in the tag data:

| Offset | Meaning |
|---|---|
| `0x04` | Resource types block (`0x1C` bytes each; string id of the type name at `+0x18`) |
| `0x64` | Resources block (`0x40` bytes each) |
| `0x148` | Size of the definition info buffer (i32) |
| `0x154` | Address of the definition info buffer (u32 pointer, `<< 2`) |

Resource entry (0x40 bytes):

| Offset | Type | Meaning |
|---|---|---|
| `0x0C` | u32 | Owning tag datum |
| `0x12` | u8 | Resource type index |
| `0x14` | i32, i32 | Offset and size of the definition inside the info buffer |
| `0x22` | i16 | Raw segment index |
| `0x24` | u32 | Root structure offset in the definition (masked `& 0x1FFFFFFF`) |
| `0x28` | i32, u32 | Fixup count, fixup array pointer |

Fixup entries are 8 bytes: `i32 offset in the definition`, `u32 address`. The address's top 3 bits give its kind (`address >> 29`): 1 means a pointer into the definition buffer, 2 (`ADDRESS_DATA`) means a pointer into the resource's data segment. The low 29 bits are the offset. A block inside a definition is `i32 count` at `offset`, with its pointer fixup keyed at `offset + 4` (`Resource.block`).

Play tag (layout table), offsets in the tag data:

| Offset | Meaning |
|---|---|
| `0x0C` | External cache files (`0x108` bytes each; NUL terminated path, backslash separated) |
| `0x18` | Pages (`0x58` bytes each) |
| `0x3C` | Segments (`0x10` bytes each) |

Segment record: `<hhiihh`: page index (i16), unknown i16, offset in page (i32), plus fields not used. The primary data of a segment is `page[offset:]`.

Page record: `i8` at `+3` is the codec (negative means stored uncompressed), `i16` at `+4` is the shared (external) file index (negative means this file), then `i32` offset at `+8`, compressed size at `+0xC`, uncompressed size at `+0x10`.

### 7.2 Pages and deflate

- Page bytes live in the resource section (section 1) of the page's file, starting at `section_offset + max(offset, 0)`.
- If the page's shared index is non-negative, the file is the external cache named in the play tag, resolved relative to the parent of the `maps` directory; otherwise the map itself.
- Pages are raw deflate: `zlib.decompressobj(-15).decompress(raw, uncompressed)`. If the codec byte is negative, the first `uncompressed` bytes are used as stored.
- Decoded pages are cached per `Resources` instance.

### 7.3 Using it

```python
cache = h3cache.Cache(path)
res = Resources(cache)
for r in res.owned_by(sbsp_tag):        # resources owned by one tag
    if r.kind == "structure_bsp_tag_resources":
        data = r.data                    # data segment (memoryview)
        n, kind, at = r.block(r.base + 0x0)
```

`Resource` fields: `owner` (Tag), `index`, `kind` (type name), `definition` (bytes), `fixups`, `base`, `data`.

## 8. bsp_terrain.py

Purpose: a stock map's ground as height grids, from the collision BSP (no pathfinding mesh exists). Run `python3 -m h3kit.bsp_terrain [map] [out.png]`; the default map is the MCC stock `halo3/maps/sidewinder.map` (Avalanche).

### 8.1 Build

1. For each `sbsp` tag, find its `structure_bsp_tag_resources` resource.
2. Collision bsps: for each, `floor_triangles` walks every non-invisible surface, rebuilds its polygon, computes the face normal, and keeps the surface if `nz > 0.3` (`FLOOR_NORMAL_Z`), or if it is two-sided and `nz < -0.3`. Kept polygons are fan-triangulated.
3. Instanced geometry: each definition's collision triangles are transformed by every instance that is not render-only and has a valid, non-empty definition.
4. All triangles are concatenated and rasterized onto a grid of `cell` world units (default 1.0): the grid origin is the floor of the minimum x and y, size is extent / cell + 2.
5. Per cell, each triangle that overlaps the cell centre (barycentric tolerance -0.02) contributes its interpolated z. Two grids result: `top` (maximum z) and `bottom` (minimum z). Cells without coverage are NaN. Triangles spanning 3 cells or fewer are processed in one vectorised batch; larger ones one at a time. Takes about 9 s.

### 8.2 API

| Member | Meaning |
|---|---|
| `Terrain(path, cell=1.0)` | Load and rasterize |
| `.triangles` | `(n, 3, 3)` array of floor triangles |
| `.top`, `.bottom` | Grids `(h, w)`, row = y index, column = x index |
| `.x0`, `.y0`, `.w`, `.h`, `.cell` | Grid origin, size and cell size |
| `.height(x, y, radius=0)` | Highest walkable surface at (x, y), searching `radius` world units (converted to cells); `None` off the ground |
| `.ground(x, y, radius=0)` | Lowest walkable surface (terrain under bridges and roofs); `None` off the ground |
| `.slope(x, y, d=3.0)` | Worst rise-over-run of `ground` over four points `d` away; `None` if any is off the map |
| `.image(scale=3, marks=())` | `(PIL image, (min, max))`: height-coloured map of `bottom` with a 50-unit grid and optional `(x, y, colour)` marks |

`h3kit.scenario.Plan` places pieces at `min(height under footprint) - 0.05`, so a piece never floats over a slope.

## 9. Units and scale

- Positions are in Halo world units: 1 unit is about 10 feet. A Spartan is about 0.7 units tall.
- Rotations in scenario tags are degrees (yaw, pitch, roll) and in the cache are stored as the same Euler fields.

## 10. Avalanche (`sidewinder`) geography

Measured with `bsp_terrain.py` on the stock `sidewinder.map`; the trigger volumes are from the scenario's tag export. Coordinates are `(x, y)` in world units, z up. Red (team 0, "defender") is at +x, blue (team 1, "attacker") at -x.

| Feature | Location / height |
|---|---|
| Collision extent | x -184..206, y -234..115, z -65.8..88.5 |
| Stock flags | (+-27, -31.7, -0.8) |
| Stock flag returns | (+-27, -39.5) |
| Base teleporter pads (stock respawn points) | (+-35.7 and +-18.3, -31.3, -4.4) |
| Valley floor | about -4.5; horseshoe x -50..55, y -30..60 |
| Rim cliffs | x about +-50, rise to 13-15 |
| East plateau | very flat, z 9-13, x 75..175, y -100..40 |
| West plateau | z 0 at x -175, rising to about 12 at x -75 |
| Fields behind the bases | z 11-15, x +-25..75, y -50..-120 |
| Central ridge | z 19-25 along x about 0, south to y -234; flat crest about 22 at x 5..17 |
| Abyss floor | z -65.7 north of y about 65 |
| South-east corner | no ground |

Trigger volumes (corner, then far corner = corner + extents; from the tag export):

| Volume | x | y | z |
|---|---|---|---|
| `kill_volumes_0` | -22.0 .. 25.7 | -65.6 .. 33.3 | -76.8 .. -8.1 |
| `kill_volumes_1` | -55.9 .. 60.9 | 46.6 .. 114.7 | -44.7 .. -8.1 |
| `safe_zone` | -53.8 .. 57.2 | -46.4 .. 76.1 | -12.9 .. 18.5 |
| `garbage` | -60.4 .. 68.9 | -14.9 .. 118.6 | -72.1 .. -29.7 |
| `kill_volumes_2` | -55.2 .. -27.4 | 65.8 .. 76.6 | -1.0 .. 19.7 |
| `kill_volumes_3` | 40.6 .. 61.2 | 53.6 .. 77.3 | -3.8 .. 20.3 |

Note: the volumes are boxes defined by corner, extents and orientation vectors; `kill_volumes_0` is rotated slightly about z, so the axis-aligned ranges above are approximate for it.

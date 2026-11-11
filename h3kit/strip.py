"""Shrink a shared map pack's built maps: drop chosen bitmaps' high-res data (the top mip, which a Halo 3
MCC cache keeps in the resource's optional, secondary, segment) and cut chosen bitmaps down to a largest
size (their base data's top mips, rewriting the page that holds them).

Why: about 600 MB of every map is MCC's armour customisation (objects\\characters\\masterchief and
elite bitmaps: every helmet, chest, coating...). Stock maps read it from MCC's own shared.map; a map
built with the kit can't (MCC compiled it differently, so almost nothing is byte-identical), so a
pack's shared.map carries it. The customisation itself stays: every armour piece is still there,
only smaller.

What it does to a chosen bitmap resource (bitmap_texture_interop_resource):
  * high-res drop: the definition says a texture half as wide and high with one mip fewer and no
    secondary data (+0x14 size 0, the +0x20 address fixup gone), as stock bitmaps without high-res data
    look; the segment loses its secondary page (page, offset and size index -1). The base data already
    holds exactly those mips;
  * shrink: the base data (its mips largest first, tightly packed: checked by decoding) loses its first
    k mips, so the largest side is at most `largest`; width, height, mip count and the base data's size
    (+0x0) follow. The page holding it is rebuilt: each shrunk resource's slot keeps its start and
    shrinks by whole 4 KB, so every later segment keeps its alignment; every map's segment offsets into
    the page and the page's record (sizes, CRC, SHA-1s) follow;
  * a page no segment of any map uses any more leaves the file; every map's page records follow the
    pages that stay (a dropped one becomes an empty record).
Only 2D, one-deep textures of a known format whose data is exactly their mip chain, whose segment no
other resource shares and whose pages are in shared.map are touched.

Page records (0x58): flags +2, codec +3, shared file +4, offset +8, compressed +0xC, uncompressed +0x10,
CRC +0x14 (~crc32 of the uncompressed page), SHA-1 of the uncompressed page +0x18, of its first 1 KB
+0x2C, of its last 1 KB +0x40, resource count +0x54 (checked against the pack's own pages).

    python3 -m h3kit.strip <folder with the pack's level maps and shared.map> [--out <folder>]
"""

import argparse
import hashlib
import shutil
import struct
import zlib
from pathlib import Path

from . import cache as h3cache

ARMOR = ("objects\\characters\\masterchief\\", "objects\\characters\\elite\\")
# everything else whose high-res mips can go without anyone noticing much (not weapons: they're in your
# face in first person)
SMALL_STUFF = ("objects\\vehicles\\", "fx\\", "objects\\gear\\")
FIRST_PERSON = ("\\fp_", "\\fp\\", "_fp_", "\\efp_", "fp_arms", "fp_body")
SECONDARY_SIZE, SECONDARY_ADDRESS = 0x14, 0x20
WIDTH, HEIGHT, DEPTH, MIPS, TYPE, FORMAT = 0x28, 0x2A, 0x2C, 0x2D, 0x2E, 0x30   # TYPE 0: 2D (2: cube)
PAGE, SEGMENT, ENTRY = 0x58, 0x10, 0x40
ALIGN = 0x1000
CHUNK = 0x400
# DXGI formats (the definition's +0x30): bytes a pixel, block compressed (4 x 4 blocks)
DXGI = {**{c: (0.5, True) for c in (0x46, 0x47, 0x48, 0x4F, 0x50, 0x51)},                    # BC1, BC4
        **{c: (1.0, True) for c in (0x49, 0x4A, 0x4B, 0x4C, 0x4D, 0x4E, 0x52, 0x53, 0x54,     # BC2, BC3, BC5
                                    0x5E, 0x5F, 0x60, 0x61, 0x62, 0x63)},                     # BC6H, BC7
        0x3C: (1.0, False), 0x3D: (1.0, False), 0x41: (1.0, False),                            # R8, A8
        0x31: (2.0, False), 0x33: (2.0, False), 0x38: (2.0, False),                            # R8G8, R16
        0x1C: (4.0, False), 0x1D: (4.0, False), 0x57: (4.0, False), 0x5A: (4.0, False), 0x5B: (4.0, False)}


def mip_size(w, h, level, fmt):
    bpp, block = DXGI[fmt]
    x, y = max(1, w >> level), max(1, h >> level)
    if block:
        x, y = max(4, (x + 3) // 4 * 4), max(4, (y + 3) // 4 * 4)
    return int(x * y * bpp)


def chain(w, h, mips, fmt, first=0):
    return sum(mip_size(w, h, lv, fmt) for lv in range(first, mips))


class Level:
    """A level map built against a shared.map: its play (layout) and zone (gestalt) tables, as file offsets."""

    def __init__(self, path):
        self.path = Path(path)
        c = self.c = h3cache.Cache(str(path))
        zone = next(t for t in c.tags if t and t.group == "zone")
        play = next((t for t in c.tags if t and t.group == "play"), None)
        if play is None:
            raise SystemExit(f"strip: {path.name} is a standalone build (no play tag): only shared packs are handled")
        z, p = c.read(zone.offset, 0x220), c.read(play.offset, 0x50)
        self.count, self.entries = self._block(z, 0x64)
        size, = struct.unpack_from("<i", z, 0x148)
        address, = struct.unpack_from("<I", z, 0x154)
        self.info = c.offset_of(c.expand(address))
        self.info_size = size
        n, base = self._block(p, 0xC)
        self.external = [c.read(base + i * 0x108, 0x108).split(b"\0")[0].decode() for i in range(n)]
        self.page_count, self.pages = self._block(p, 0x18)
        self.segment_count, self.segments = self._block(p, 0x3C)

    def _block(self, data, offset):
        n, address = struct.unpack_from("<iI", data, offset)
        return n, (self.c.offset_of(self.c.expand(address)) if n > 0 else None)

    def page(self, i):
        e = self.c.read(self.pages + i * PAGE, PAGE)
        shared, = struct.unpack_from("<h", e, 4)
        offset, comp, unc = struct.unpack_from("<iii", e, 8)
        return shared, offset, comp, unc

    def file_of(self, shared):
        return self.path.name if shared < 0 else self.external[shared].split("\\")[-1]

    def key(self, i):
        """A page as (file name, offset): the same page in every map of the set."""
        sh, off, *_ = self.page(i)
        return self.file_of(sh), off

    def segment(self, i):
        return list(struct.unpack("<hhiihh", self.c.read(self.segments + i * SEGMENT, SEGMENT)))

    def resources(self):
        """(index, owner tag, segment index, definition offset, size, fixup count, fixup array offset)."""
        for i in range(self.count):
            e = self.c.read(self.entries + i * ENTRY, ENTRY)
            datum, = struct.unpack_from("<I", e, 0xC)
            off, size = struct.unpack_from("<ii", e, 0x14)
            seg, = struct.unpack_from("<h", e, 0x22)
            n, address = struct.unpack_from("<iI", e, 0x28)
            fix = self.c.offset_of(self.c.expand(address)) if n > 0 else None
            yield i, self.c.tag_by_datum(datum), seg, off, size, n, fix


def fixup_arrays(level):
    """{fixup list: (count, stored pointer)} of every resource's fixup array. Arrays are shared: many
    resources point at one list (one has 1,688 users), so a list is never written; a changed resource is
    pointed at an existing array holding exactly its new list."""
    out = {}
    for i in range(level.count):
        e = level.c.read(level.entries + i * ENTRY, ENTRY)
        n, address = struct.unpack_from("<iI", e, 0x28)
        if n <= 0:
            continue
        raw = level.c.read(level.c.offset_of(level.c.expand(address)), 8 * n)
        out.setdefault(tuple(struct.unpack_from("<iI", raw, 8 * k) for k in range(n)), (n, address))
    return out


class Pages:
    """Uncompressed pages of the set's files, read once each."""

    def __init__(self, folder):
        self.folder = Path(folder)
        self._start, self._data = {}, {}

    def path(self, name):
        p = self.folder / name
        return p if p.exists() else self.folder.parent / "halo3" / "maps" / name    # an installed mod

    def start(self, name, level=None):
        if name not in self._start:
            if level is not None and name == level.path.name:
                self._start[name] = level.c.section_offsets[1]
            else:
                with open(self.path(name), "rb") as f:
                    h = f.read(0x4000)
                self._start[name] = (struct.unpack_from("<2I", h, 0x4DC + 8)[0]
                                     + struct.unpack_from("<4I", h, 0x4CC)[1]) & 0xFFFFFFFF
        return self._start[name]

    def raw(self, level, k):
        e = level.c.read(level.pages + k * PAGE, PAGE)
        sh, = struct.unpack_from("<h", e, 4)
        off, comp, unc = struct.unpack_from("<iii", e, 8)
        name = level.file_of(sh)
        with open(self.path(name), "rb") as f:
            f.seek(self.start(name, level) + off)
            return e, f.read(comp)

    def data(self, level, k, keep=False):
        key = level.key(k)
        if key in self._data:
            return self._data[key]
        e, raw = self.raw(level, k)
        unc, = struct.unpack_from("<i", e, 0x10)
        data = raw[:unc] if struct.unpack_from("<b", e, 3)[0] < 0 else zlib.decompressobj(-15).decompress(raw, unc)
        if keep:
            self._data[key] = data
        return data


def checks(data):
    """A page record's CRC and SHA-1s of its uncompressed data."""
    return (struct.pack("<I", zlib.crc32(data) ^ 0xFFFFFFFF) + hashlib.sha1(data).digest()
            + hashlib.sha1(data[:CHUNK]).digest() + hashlib.sha1(data[-CHUNK:]).digest())


def _plan(level, pages, highres, shrink, largest, keep_full):
    """Each changed resource of `level`: {entry index: (segment, definition file offset, new definition,
    fixup count, fixup array offset, kept fixups, drop secondary?, (page key, slot offset, new data) or None)}."""
    c = level.c
    users = {}
    rows = list(level.resources())
    for i, t, seg, *_ in rows:
        if seg >= 0:
            users[seg] = users.get(seg, 0) + 1
    arrays = fixup_arrays(level)
    out = {}
    for i, t, seg, off, size, n, fix in rows:
        if seg < 0 or t is None or t.group != "bitm" or users[seg] != 1 or size < FORMAT + 4:
            continue
        hi = t.name.startswith(highres)
        sh = t.name.startswith(shrink) and not any(k in t.name for k in keep_full)
        if not (hi or sh):
            continue
        s = level.segment(seg)
        d = bytearray(c.read(level.info + off, size))
        fixups = [struct.unpack_from("<iI", c.read(fix + 8 * k, 8)) for k in range(n)]
        w, h = struct.unpack_from("<HH", d, WIDTH)
        depth, mips, fmt = d[DEPTH], d[MIPS], d[FORMAT]
        if depth != 1 or d[TYPE] != 0 or fmt not in DXGI:
            continue
        drop2 = False
        if hi and s[1] >= 0 and level.page(s[1])[0] >= 0:          # its high-res data in shared.map
            ssize, = struct.unpack_from("<i", d, SECONDARY_SIZE)
            without = tuple((o, a) for o, a in fixups if not (o == SECONDARY_ADDRESS and a >> 29 == 3))
            if (ssize > 0 and mips >= 2 and w >= 2 and h >= 2 and ssize == mip_size(w, h, 0, fmt)
                    and len(without) == len(fixups) - 1 and without in arrays):
                struct.pack_into("<i", d, SECONDARY_SIZE, 0)
                w, h, mips = w // 2, h // 2, mips - 1
                fixups = [(o, a) for o, a in fixups if not (o == SECONDARY_ADDRESS and a >> 29 == 3)]
                drop2 = True
        cut = None
        psize, = struct.unpack_from("<i", d, 0)
        data_fix = dict(fixups).get(0xC)
        if (sh and (s[1] < 0 or drop2) and s[0] >= 0 and level.page(s[0])[0] >= 0 and data_fix == 2 << 29
                and psize == chain(w, h, mips, fmt)):
            block = DXGI[fmt][1]
            k = 0
            while max(w >> k, h >> k) > largest and mips - k > 1 and min(w >> (k + 1), h >> (k + 1)) >= (4 if block else 1):
                k += 1
            if k:
                skip = chain(w, h, k, fmt)
                base = pages.data(level, s[0], keep=True)[s[2]:s[2] + psize]
                cut = (level.key(s[0]), s[2], bytes(base[skip:]))
                w, h, mips, psize = w >> k, h >> k, mips - k, psize - skip
                struct.pack_into("<i", d, 0, psize)
        if not drop2 and cut is None:
            continue
        struct.pack_into("<HH", d, WIDTH, w, h)
        d[MIPS] = mips
        out[i] = (seg, level.info + off, bytes(d), arrays[tuple(fixups)] if drop2 else None, drop2, cut)
    return out


def _rebuild(levels, pages, cuts):
    """New contents of the pages holding shrunk resources: {page key: (data, {old offset: new offset})}."""
    out = {}
    for key, slots in cuts.items():
        lv, k = next((lv, k) for lv in levels for k in range(lv.page_count) if lv.key(k) == key)
        old = pages.data(lv, k, keep=True)
        starts = set()
        for lv2 in levels:
            for s in range(lv2.segment_count):
                g = lv2.segment(s)
                for p, o in ((g[0], g[2]), (g[1], g[3])):
                    if p >= 0 and lv2.key(p) == key:
                        starts.add(o)
        starts = sorted(starts)
        new, moved = bytearray(old[:starts[0]]), {}
        for j, o in enumerate(starts):
            end = starts[j + 1] if j + 1 < len(starts) else len(old)
            moved[o] = len(new)
            if o in slots:
                data = slots[o]
                shrink = (end - o - len(data)) // ALIGN * ALIGN
                new += data + bytes(end - o - shrink - len(data))
            else:
                new += old[o:end]
        out[key] = (bytes(new), moved)
    return out


def strip(folder, out=None, highres=ARMOR + SMALL_STUFF, shrink=ARMOR, largest=128, keep_full=FIRST_PERSON, log=print):
    """Strip the level maps in `folder` and their shared.map; write the set to `out` (default: in place,
    through a copy). Returns {file name: (old size, new size)}."""
    folder = Path(folder)
    out = Path(out) if out else folder
    work = out.parent / (out.name + ".strip_tmp")
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    names = sorted(p.name for p in folder.glob("*.map") if p.name not in ("shared.map", "campaign.map"))
    levels = [Level(folder / n) for n in names]
    pages = Pages(folder)
    shared_path = folder / "shared.map"

    plans = {lv.path.name: _plan(lv, pages, highres, shrink, largest, keep_full) for lv in levels}
    # the shrunk resources' new base data: the same in every map (they share the page)
    cuts = {}
    for name, plan in plans.items():
        for seg, doff, d, array, drop2, cut in plan.values():
            if cut:
                key, o, data = cut
                if cuts.setdefault(key, {}).setdefault(o, data) != data:
                    raise SystemExit(f"strip: the maps disagree about the resource at {key} {o:#x}")
    rebuilt = _rebuild(levels, pages, cuts)

    dropped_seg = {name: {seg for seg, _, _, _, drop2, _ in plan.values() if drop2} for name, plan in plans.items()}
    used, dropped = set(), set()
    for lv in levels:
        for s in range(lv.segment_count):
            p1, p2 = lv.segment(s)[:2]
            if p1 >= 0:
                used.add(lv.key(p1))
            if p2 >= 0:
                (dropped if s in dropped_seg[lv.path.name] else used).add(lv.key(p2))
    dropped -= used
    if any(f != "shared.map" for f, _ in dropped):
        raise SystemExit("strip: a dropped page is in a level map's own pages: only shared.map pages are dropped")

    # shared.map, compacted: every page any level map lists, in file order; dropped ones out, rebuilt ones new
    sizes_in = {}
    for lv in levels:
        for k in range(lv.page_count):
            sh, off, comp, unc = lv.page(k)
            if sh >= 0 and lv.file_of(sh) == "shared.map" and off >= 0 and comp > 0:
                sizes_in[off] = max(sizes_in.get(off, 0), comp)
    start = pages.start("shared.map")
    with open(shared_path, "rb") as f:
        head = bytearray(f.read(0x4000))
        sections = [struct.unpack_from("<2I", head, 0x4DC + 8 * i) for i in range(4)]
        end = start + sections[1][1]
        if any(sections[i][1] for i in (0, 2, 3)) or end != shared_path.stat().st_size:
            raise SystemExit("strip: shared.map isn't one resource section to the end of the file")
        cursor = 0                         # nothing outside a listed page may be lost: the gaps must be empty
        for off in sorted(sizes_in):
            if off > cursor:
                f.seek(start + cursor)
                if any(f.read(off - cursor)):
                    raise SystemExit(f"strip: shared.map has data at {cursor:#x}..{off:#x} that no page lists")
            cursor = max(cursor, off + sizes_in[off])
        if cursor < end - start:
            f.seek(start + cursor)
            if any(f.read(end - start - cursor)):
                raise SystemExit("strip: shared.map has data after its last listed page")
        moved, records, pos = {}, {}, 0
        with open(work / "shared.map", "wb") as o:
            o.write(head)
            for off in sorted(sizes_in):
                if ("shared.map", off) in dropped:
                    continue
                pad = (-pos) % ALIGN
                o.write(bytes(pad))
                pos += pad
                if ("shared.map", off) in rebuilt:
                    data = rebuilt[("shared.map", off)][0]
                    z = zlib.compressobj(6, zlib.DEFLATED, -15)
                    blob = z.compress(data) + z.flush()
                    records[off] = (len(blob), len(data), checks(data))
                    log(f"strip: rebuilt page at {off:#x}: {sizes_in[off] / 2**20:,.0f} -> {len(blob) / 2**20:,.0f} MB")
                else:
                    f.seek(start + off)
                    blob = f.read(sizes_in[off])
                o.write(blob)
                moved[off] = pos
                pos += len(blob)
            pad = (-pos) % ALIGN
            o.write(bytes(pad))
            pos += pad
    struct.pack_into("<I", head, 0x8, 0x4000 + pos)
    struct.pack_into("<I", head, 0x4DC + 8 + 4, pos)
    with open(work / "shared.map", "r+b") as o:
        o.write(head)

    # each level map: a copy patched in place (its size never changes)
    for lv in levels:
        name = lv.path.name
        shutil.copyfile(lv.path, work / name)
        w = h3cache.Cache(str(work / name), writable=True)
        for i, (seg, doff, d, array, drop2, cut) in plans[name].items():
            w.write(doff, d)
            if array:                       # an existing array with its new fixups (never one written to)
                w.write(lv.entries + i * ENTRY + 0x28, struct.pack("<iI", *array))
        for s in range(lv.segment_count):
            g = lv.segment(s)
            new = list(g)
            if s in dropped_seg[name]:
                new[1], new[3], new[5] = -1, -1, -1
            for slot, (p, o) in enumerate(((new[0], new[2]), (new[1], new[3]))):
                if p >= 0 and lv.key(p) in rebuilt:
                    new[2 + slot] = rebuilt[lv.key(p)][1][o]
            if new != g:
                w.write(lv.segments + s * SEGMENT, struct.pack("<hhiihh", *new))
        for k in range(lv.page_count):
            sh, off, comp, unc = lv.page(k)
            if sh < 0 or lv.file_of(sh) != "shared.map" or off < 0 or comp <= 0:
                continue
            rec = lv.pages + k * PAGE
            if off not in moved:
                w.write(rec + 8, struct.pack("<iii", -1, 0, 0))
                continue
            w.write(rec + 8, struct.pack("<i", moved[off]))
            if off in records:
                comp2, unc2, chk = records[off]
                w.write(rec + 0xC, struct.pack("<ii", comp2, unc2) + chk)
        w.close()
        lv.c.close()
        n_hi = sum(1 for p in plans[name].values() if p[4])
        n_cut = sum(1 for p in plans[name].values() if p[5])
        log(f"strip: {name}: {n_hi} bitmaps lose their high-res mip, {n_cut} are cut to {largest} px at most")

    sizes = {}
    for p in sorted(work.iterdir()):
        sizes[p.name] = ((folder / p.name).stat().st_size, p.stat().st_size)
    out.mkdir(parents=True, exist_ok=True)
    for p in work.iterdir():
        shutil.move(str(p), str(out / p.name))
    if out != folder:
        for p in folder.glob("*.map"):
            if not (out / p.name).exists():
                shutil.copyfile(p, out / p.name)
    work.rmdir()
    log(f"strip: {len(dropped)} shared.map pages dropped, {len(rebuilt)} rebuilt: shared.map "
        f"{sizes['shared.map'][0] / 2**20:,.0f} -> {sizes['shared.map'][1] / 2**20:,.0f} MB")
    return sizes


def verify(folder, prefixes=ARMOR + SMALL_STUFF, log=print):
    """Read back a pack's build: every page each level map's segments use decompresses from its file to its
    recorded size, CRC and SHA-1s; every chosen bitmap's base data is exactly its mip chain and lies inside
    its page. Returns the number of problems."""
    folder = Path(folder)
    problems = 0
    levels = [p for p in sorted(folder.glob("*.map")) if p.name not in ("shared.map", "campaign.map")]
    if not levels:
        log(f"verify: no level maps in {folder} (give the folder that holds them, e.g. <mod>/maps)")
        return 1
    for p in levels:
        lv = Level(p)
        pages = Pages(folder)
        seen = {}
        for s in range(lv.segment_count):
            for k in lv.segment(s)[:2]:
                if k < 0 or k in seen:
                    continue
                try:
                    e, raw = pages.raw(lv, k)
                    unc, = struct.unpack_from("<i", e, 0x10)
                    data = raw[:unc] if struct.unpack_from("<b", e, 3)[0] < 0 else zlib.decompressobj(-15).decompress(raw, unc)
                    if len(data) != unc:
                        raise ValueError(f"{len(data)} of {unc} bytes")
                    if checks(data) != e[0x14:0x54]:
                        raise ValueError("CRC or SHA-1 doesn't match")
                    seen[k] = unc
                except Exception as x:          # noqa: BLE001  (any failure is a problem to report)
                    seen[k] = -1
                    problems += 1
                    log(f"verify: {p.name}: page {k}: {x}")
        checked = 0
        for i, t, seg, off, size, n, fix in lv.resources():
            if seg < 0 or t is None or t.group != "bitm" or size < FORMAT + 4:
                continue
            g = lv.segment(seg)
            d = lv.c.read(lv.info + off, size)
            fx = [struct.unpack_from("<iI", lv.c.read(fix + 8 * k, 8)) for k in range(n)] if n > 0 else []
            ssize, = struct.unpack_from("<i", d, SECONDARY_SIZE)
            has3 = any(o == SECONDARY_ADDRESS and a >> 29 == 3 for o, a in fx)
            if (any(a == 0 for o, a in fx) or not any(o == 0xC and a >> 29 == 2 for o, a in fx)
                    or has3 != (g[1] >= 0 and ssize > 0)):
                problems += 1
                if problems < 20:
                    log(f"verify: {p.name}: {t.name}: fixups {fx} don't fit its definition (secondary {ssize}, segment {g})")
            if not t.name.startswith(prefixes):
                continue
            g = lv.segment(seg)
            d = lv.c.read(lv.info + off, size)
            psize, = struct.unpack_from("<i", d, 0)
            w, h = struct.unpack_from("<HH", d, WIDTH)
            if g[1] < 0 and d[FORMAT] in DXGI and d[DEPTH] == 1 and d[TYPE] == 0 and psize != chain(w, h, d[MIPS], d[FORMAT]):
                problems += 1
                log(f"verify: {p.name}: {t.name}: base data {psize} isn't its {w} x {h} x {d[MIPS]} chain")
            if g[0] < 0 or seen.get(g[0], -1) < 0 or g[2] + psize > seen[g[0]]:
                problems += 1
                log(f"verify: {p.name}: {t.name}: base data {psize} at {g[2]} past its page")
            checked += 1
        lv.c.close()
        log(f"verify: {p.name}: {len(seen)} pages read and checked, {checked} chosen bitmaps checked")
    return problems


def main(argv=None):
    ap = argparse.ArgumentParser(description="Drop chosen bitmaps' high-res mips and shrink the armour in a shared pack.")
    ap.add_argument("folder", type=Path, help="the pack's built maps (packs/<pack>/shared)")
    ap.add_argument("--out", type=Path, help="write the set here (default: in place)")
    ap.add_argument("--verify", action="store_true", help="only read the set back")
    args = ap.parse_args(argv)
    if args.verify:
        raise SystemExit(1 if verify(args.folder) else 0)
    strip(args.folder, args.out)
    raise SystemExit(1 if verify(args.out or args.folder) else 0)


if __name__ == "__main__":
    main()

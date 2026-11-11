"""Halo 3 MCC (cache v13) resource reader: the zone gestalt, the play layout
table and the raw-deflate pages behind them.

Layouts follow Assembly's H3MCC_Layouts_Resources.xml. A resource's
definition sits in the gestalt's info buffer; pointers in it are fixed up from
its fixup list, where the top three bits of an address give its kind
(1: the definition itself, 2: the resource's data segment).
"""

import os
import struct
import zlib

from . import cache as h3cache

RESOURCE_SECTION = 1
ADDRESS_DEFINITION = 1
ADDRESS_DATA = 2


class Resource:
    def __init__(self, owner, index, kind, definition, fixups, base, data):
        self.owner = owner
        self.index = index
        self.kind = kind
        self.definition = definition
        self.fixups = fixups      # {offset in definition: address}
        self.base = base          # offset of the root structure in the definition
        self._data = data         # callable returning the data segment bytes

    @property
    def data(self):
        return self._data()

    def block(self, offset):
        """(count, kind, offset) of a tag block at `offset` in the definition."""
        count, = struct.unpack_from("<i", self.definition, offset)
        address = self.fixups.get(offset + 4, 0)
        return count, address >> 29, address & 0x1FFFFFFF


class Resources:
    def __init__(self, cache):
        self.c = cache
        self.maps_dir = os.path.dirname(os.path.abspath(cache.path))
        zone = next(t for t in cache.tags if t and t.group == "zone")
        play = next((t for t in cache.tags if t and t.group == "play"), None)
        z = cache.read(zone.offset, 0x220)
        # a play tag holds the shared files, pages and segments; a standalone map has none and
        # keeps the same records in its zone tag
        p, files, pages, segments = (cache.read(play.offset, 0x50), 0xC, 0x18, 0x3C) if play else (z, 0x28, 0x34, 0x58)
        self.absolute_pages = play is None      # (and their pages' offsets count from the start of the file)

        n, base = self._block(z, 0x4)
        self.types = [cache.string(struct.unpack("<I", cache.read(base + i * 0x1C + 0x18, 4))[0]) for i in range(n)]
        self.count, self._entries = self._block(z, 0x64)
        size, = struct.unpack_from("<i", z, 0x148)
        address, = struct.unpack_from("<I", z, 0x154)
        self.info = cache.read(cache.offset_of(cache.expand(address)), size)

        n, base = self._block(p, files)
        self.external = [cache.read(base + i * 0x108, 0x108).split(b"\0")[0].decode() for i in range(n)]
        self.page_count, self._pages = self._block(p, pages)
        self.segment_count, self._segments = self._block(p, segments)
        self._page_cache = {}

    def _block(self, data, offset):
        n, address = struct.unpack_from("<iI", data, offset)
        return n, (self.c.offset_of(self.c.expand(address)) if n > 0 else None)

    def __iter__(self):
        for i in range(self.count):
            yield self.resource(i)

    def owned_by(self, tag):
        for i in range(self.count):
            datum, = struct.unpack("<I", self.c.read(self._entries + i * 0x40 + 0xC, 4))
            if datum == tag.datum:
                yield self.resource(i)

    def resource(self, i):
        e = self.c.read(self._entries + i * 0x40, 0x40)
        datum, = struct.unpack_from("<I", e, 0xC)
        kind = self.types[e[0x12]] if e[0x12] < len(self.types) else None
        info_offset, info_size = struct.unpack_from("<ii", e, 0x14)
        segment, = struct.unpack_from("<h", e, 0x22)
        base, = struct.unpack_from("<I", e, 0x24)
        n, address = struct.unpack_from("<iI", e, 0x28)
        fixups = {}
        if n > 0:
            raw = self.c.read(self.c.offset_of(self.c.expand(address)), 8 * n)
            fixups = dict(struct.unpack_from("<iI", raw, 8 * k) for k in range(n))
        definition = self.info[info_offset:info_offset + info_size] if info_size > 0 else b""
        return Resource(self.c.tag_by_datum(datum), i, kind, definition, fixups, base & 0x1FFFFFFF,
                        lambda: self.segment(segment))

    def segment(self, index):
        """The primary data of a raw segment."""
        if index < 0:
            return b""
        page, _, offset, _, _, _ = struct.unpack("<hhiihh", self.c.read(self._segments + index * 0x10, 0x10))
        return memoryview(self.page(page))[offset:]

    def page(self, index):
        if index in self._page_cache:
            return self._page_cache[index]
        e = self.c.read(self._pages + index * 0x58, 0x58)
        codec, shared = struct.unpack_from("<bh", e, 3)
        offset, compressed, uncompressed = struct.unpack_from("<iii", e, 8)
        if shared >= 0:
            path = os.path.join(os.path.dirname(self.maps_dir), *self.external[shared].split("\\"))
            other = h3cache.Cache(path)
            start = other.section_offsets[RESOURCE_SECTION]
            other.close()
        else:
            path, start = self.c.path, 0 if self.absolute_pages else self.c.section_offsets[RESOURCE_SECTION]
        with open(path, "rb") as f:
            f.seek(start + max(offset, 0))
            raw = f.read(compressed)
        data = raw[:uncompressed] if codec < 0 else zlib.decompressobj(-15).decompress(raw, uncompressed)
        self._page_cache[index] = data
        return data

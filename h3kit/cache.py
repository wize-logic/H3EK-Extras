"""Minimal reader/patcher for Halo 3 MCC cache files (version 13, Update 14+).

Layouts follow Assembly's Blamite/Formats/Halo3MCC/LayoutsU13 and the
Halo3MCC plugins. Tag data pointers are 32-bit, stored as (address >> 2).
Patches overwrite bytes in place, so file size and layout never change.
"""

import struct

HEADER_SIZE = 0x4000
TAG_SECTION = 2


class Tag:
    def __init__(self, cache, index, group, salt, address, name):
        self.cache = cache
        self.index = index
        self.group = group
        self.datum = (salt << 16) | index
        self.address = address
        self.name = name

    @property
    def offset(self):
        return self.cache.offset_of(self.address)

    def __repr__(self):
        return f"<{self.group} {self.name} 0x{self.datum:08x}>"


class Cache:
    def __init__(self, path, writable=False):
        self.path = path
        self.f = open(path, "r+b" if writable else "rb")
        h = self.f.read(HEADER_SIZE)
        if h[:4] != b"daeh" or struct.unpack_from("<i", h, 4)[0] != 13:
            raise ValueError(f"{path}: not a Halo 3 MCC version 13 cache")
        self.header = h
        self.internal_name = h[0xC0:0xE0].split(b"\0")[0].decode()
        self.scenario_name = h[0xE0:0x1E0].split(b"\0")[0].decode()
        self.virtual_base = struct.unpack_from("<Q", h, 0x2E0)[0]
        index_address = struct.unpack_from("<Q", h, 0x2E8)[0]
        masks = struct.unpack_from("<4I", h, 0x4CC)
        sections = [struct.unpack_from("<2I", h, 0x4DC + 8 * i) for i in range(4)]
        self.section_offsets = [(sections[i][0] + masks[i]) & 0xFFFFFFFF for i in range(4)]
        self.tag_section_offset = self.section_offsets[TAG_SECTION]
        self.tag_section_size = sections[TAG_SECTION][1]
        self._read_strings(h)
        self._read_index(index_address)

    # -- addressing --------------------------------------------------------

    def offset_of(self, address):
        off = address - self.virtual_base + self.tag_section_offset
        if not self.tag_section_offset <= off < self.tag_section_offset + self.tag_section_size:
            raise ValueError(f"address 0x{address:x} is outside the tag section")
        return off

    def expand(self, pointer):
        return pointer << 2

    def read(self, offset, size):
        self.f.seek(offset)
        return self.f.read(size)

    def read_at(self, address, size):
        return self.read(self.offset_of(address), size)

    def write(self, offset, data):
        self.f.seek(offset)
        self.f.write(data)

    def debug_offset(self, debug_virtual):
        return (debug_virtual + struct.unpack_from("<I", self.header, 0x4CC)[0]) & 0xFFFFFFFF

    # -- tables ------------------------------------------------------------

    def _read_strings(self, h):
        count, table, size, index = struct.unpack_from("<4I", h, 0x30)
        offsets = struct.unpack("<%di" % count, self.read(self.debug_offset(index), 4 * count))
        data = self.read(self.debug_offset(table), size)
        self.strings = [data[o:data.index(b"\0", o)].decode("latin-1") if o >= 0 else "" for o in offsets]
        count, table, size, index = struct.unpack_from("<4I", h, 0x20)
        offsets = struct.unpack("<%di" % count, self.read(self.debug_offset(index), 4 * count))
        data = self.read(self.debug_offset(table), size)
        self.tag_names = [data[o:data.index(b"\0", o)].decode("latin-1") if o >= 0 else "" for o in offsets]

    def _read_index(self, index_address):
        ih = self.read_at(index_address, 0x48)
        ngroups, gaddr = struct.unpack_from("<i4xQ", ih, 0)
        ntags, taddr = struct.unpack_from("<i4xQ", ih, 0x10)
        groups = self.read_at(gaddr, 16 * ngroups)
        self.groups = [struct.unpack_from("<4s", groups, 16 * i)[0][::-1].decode("latin-1") for i in range(ngroups)]
        table = self.read_at(taddr, 8 * ntags)
        self.tags = []
        for i in range(ntags):
            gi, salt, ptr = struct.unpack_from("<hHI", table, 8 * i)
            if gi < 0 or ptr == 0:
                self.tags.append(None)
                continue
            name = self.tag_names[i] if i < len(self.tag_names) else ""
            self.tags.append(Tag(self, i, self.groups[gi], salt, self.expand(ptr), name))
        self.by_name = {}
        for t in self.tags:
            if t:
                self.by_name[(t.group, t.name)] = t

    # -- helpers -----------------------------------------------------------

    def find(self, group, name):
        return self.by_name.get((group, name))

    def tag_by_datum(self, datum):
        if datum in (0xFFFFFFFF, -1):
            return None
        i = datum & 0xFFFF
        return self.tags[i] if i < len(self.tags) else None

    def block(self, base_offset, field_offset):
        """(count, file offset of first element) of a tag block field."""
        count, ptr = struct.unpack("<iI", self.read(base_offset + field_offset, 8))
        if count <= 0 or ptr == 0:
            return 0, None
        return count, self.offset_of(self.expand(ptr))

    def string(self, sid):
        """Resolve a string id (8-bit length, 3-bit namespace, 21-bit index)."""
        if not hasattr(self, "_ns_counts"):
            count, offset = struct.unpack_from("<iI", self.header, 0x40)
            self._ns_counts = struct.unpack("<%di" % count, self.read(self.debug_offset(offset), 4 * count))
        ns = (sid >> 21) & 0x7
        idx = sid & 0x1FFFFF
        counts = self._ns_counts
        if ns == 0 and idx >= counts[0]:
            real = idx - counts[0] + sum(counts)
        else:
            real = idx + sum(counts[:ns])
        return self.strings[real] if 0 <= real < len(self.strings) else f"<sid 0x{sid:08x}>"

    def close(self):
        self.f.close()


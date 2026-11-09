"""Find Shift-JIS strings in the decrypted EBOOT that the code really references.

Uses the ELF relocation sections (R_MIPS_32 in data, HI16/LO16 pairs in code) so every
string comes with the exact list of places that point at it.
"""
import os, re, struct, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EBOOT = os.path.join(ROOT, "eboot", "EBOOT_dec.BIN")
FILE_DELTA = 0x80  # file offset = vaddr + 0x80 for the first LOAD segment


def sections(eb):
    shoff, = struct.unpack_from("<I", eb, 0x20)
    shentsize, shnum, shstrndx = struct.unpack_from("<HHH", eb, 0x2E)
    secs = [struct.unpack_from("<10I", eb, shoff + i * shentsize) for i in range(shnum)]
    strtab = secs[shstrndx][4]
    out = {}
    for s in secs:
        name = eb[strtab + s[0]:eb.index(b"\0", strtab + s[0])].decode()
        out[name] = dict(type=s[1], addr=s[3], off=s[4], size=s[5], info=s[7])
    return out


def relocs(eb, secs):
    """Yield (kind, where_vaddr, target_vaddr, extra) for every pointer relocation."""
    for name, s in secs.items():
        if not name.startswith(".rel.") or s["size"] == 0:
            continue
        hi = None
        for i in range(s["off"], s["off"] + s["size"], 8):
            r_off, r_info = struct.unpack_from("<II", eb, i)
            typ = r_info & 0xFF
            fo = r_off + FILE_DELTA
            if fo + 4 > len(eb):
                continue
            w, = struct.unpack_from("<I", eb, fo)
            if typ == 2:  # R_MIPS_32
                yield "abs32", r_off, w, None
            elif typ == 5:  # HI16
                hi = (r_off, w & 0xFFFF)
            elif typ == 6 and hi:  # LO16
                lo = w & 0xFFFF
                tgt = (hi[1] << 16) + (lo - 0x10000 if lo & 0x8000 else lo)
                yield "hilo", r_off, tgt & 0xFFFFFFFF, hi[0]


def read_sjis(eb, vaddr, limit=512):
    fo = vaddr + FILE_DELTA
    i = fo
    while i < len(eb) and eb[i] != 0 and i - fo < limit:
        c = eb[i]
        i += 2 if (0x81 <= c <= 0x9F or 0xE0 <= c <= 0xFC) else 1
    raw = eb[fo:i]
    if i >= len(eb) or eb[i] != 0:
        return None
    try:
        return raw.decode("cp932")
    except UnicodeDecodeError:
        return None


JP = re.compile(r"[぀-ヿ一-鿿　-〿！-ﾟ]")


def find_strings(eb=None):
    eb = eb or open(EBOOT, "rb").read()
    secs = sections(eb)
    ro, da = secs[".rodata"], secs[".data"]
    lo, hi = ro["addr"], da["addr"] + da["size"]
    refs = collections.defaultdict(list)
    for kind, where, tgt, extra in relocs(eb, secs):
        if lo <= tgt < hi:
            refs[tgt].append((kind, where, extra))
    out = {}
    for tgt, rl in refs.items():
        s = read_sjis(eb, tgt)
        if s and JP.search(s):
            out[tgt] = dict(text=s, refs=rl, nbytes=len(s.encode("cp932")))
    return out


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    st = find_strings()
    kinds = collections.Counter(k for v in st.values() for k, _, _ in v["refs"])
    print(len(st), "referenced Japanese strings;", sum(len(v["text"]) for v in st.values()), "chars; ref kinds", kinds)

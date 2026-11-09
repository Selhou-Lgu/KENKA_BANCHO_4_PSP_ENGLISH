"""Write translated strings into the decrypted EBOOT.

In place when the new text fits the old slot; otherwise the string is moved into free
space and every pointer to it is updated (R_MIPS_32 words and exclusive HI16/LO16 pairs).
"""
import os, sys, struct, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eboot_strings as es

D = es.FILE_DELTA


def _capacity(eb, vaddr, nbytes, starts):
    """Bytes available at vaddr (incl. terminator) without touching other data."""
    fo = vaddr + D
    end = fo + nbytes + 1
    nxt = min((s for s in starts if s > vaddr), default=None)
    lim = (nxt + D) if nxt is not None else end + 4
    while end < lim and end % 4 and eb[end] == 0:
        end += 1
    return end - fo


def apply(eb, strings, translations, encode, free_ranges, log=print):
    """strings: from eboot_strings.find_strings(); translations: {vaddr: english}.
    encode(english) -> bytes (no terminator). free_ranges: [(file_start, file_end)]."""
    eb = bytearray(eb)
    starts = sorted(strings)
    hi_users = collections.defaultdict(set)  # hi16 location -> targets using it
    for tgt, v in strings.items():
        for kind, where, hi in v["refs"]:
            if kind == "hilo":
                hi_users[hi].add(tgt)
    pool = [list(r) for r in free_ranges]
    stats = collections.Counter()
    problems = []

    def alloc(n):
        for r in pool:
            a = (r[0] + 3) & ~3
            if a + n <= r[1]:
                r[0] = a + n
                return a
        return None

    for vaddr, en in sorted(translations.items()):
        v = strings[vaddr]
        try:
            new = (encode(vaddr, en) if getattr(encode, "by_addr", False) else encode(en)) + b"\x00"
        except Exception as e:
            problems.append((hex(vaddr), v["text"], f"encode: {e}")); continue
        cap = _capacity(eb, vaddr, v["nbytes"], starts)
        if len(new) <= cap:
            fo = vaddr + D
            eb[fo:fo + cap] = new + b"\x00" * (cap - len(new))
            stats["in place"] += 1
            continue
        shared = [hi for k, w, hi in v["refs"] if k == "hilo" and len(hi_users[hi]) > 1]
        if shared:
            problems.append((hex(vaddr), v["text"], f"too long ({len(new)}>{cap}) and code-shared pointer"))
            continue
        fo = alloc(len(new))
        if fo is None:
            problems.append((hex(vaddr), v["text"], "out of free space")); continue
        eb[fo:fo + len(new)] = new
        na = fo - D
        for kind, where, hi in v["refs"]:
            if kind == "abs32":
                struct.pack_into("<I", eb, where + D, na)
            else:
                lo_w, = struct.unpack_from("<I", eb, where + D)
                hi_w, = struct.unpack_from("<I", eb, hi + D)
                lo = na & 0xFFFF
                h = ((na + 0x8000) >> 16) & 0xFFFF
                struct.pack_into("<I", eb, where + D, (lo_w & 0xFFFF0000) | lo)
                struct.pack_into("<I", eb, hi + D, (hi_w & 0xFFFF0000) | h)
        stats["moved"] += 1
    left = sum(r[1] - r[0] for r in pool)
    log(f"EBOOT strings: {dict(stats)}, problems {len(problems)}, free space left {left} bytes")
    return bytes(eb), problems

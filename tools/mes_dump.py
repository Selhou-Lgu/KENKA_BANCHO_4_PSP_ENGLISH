"""Dump *Mes.bin message files (u32 pointer table + NUL-terminated cp932 strings).

Non-printable / non-cp932 bytes are kept as {XX} hex escapes so the text round-trips.
usage: python -I mes_dump.py <file.bin>  -> prints stats; use as module for dumping
"""
import struct, sys


def read_mes(d):
    first = struct.unpack_from("<I", d, 0)[0]
    n = first // 4
    ptrs = list(struct.unpack_from(f"<{n}I", d, 0))
    assert all(ptrs[i] <= ptrs[i + 1] for i in range(n - 1)), "pointers not monotonic"
    out = []
    for p in ptrs:
        # pair-aware scan: 0xC8-0xE4 and 0xF5 consume a second byte that may be 0x00
        i = p
        while d[i] != 0:
            i += 2 if (0xC8 <= d[i] <= 0xE4 or d[i] == 0xF5) else 1
        out.append(d[p:i])
    return out


def decode(b):
    s, i = [], 0
    while i < len(b):
        c = b[i]
        if (0x81 <= c <= 0x9F or 0xE0 <= c <= 0xFC) and i + 1 < len(b):
            try:
                s.append(b[i:i + 2].decode("cp932")); i += 2; continue
            except UnicodeDecodeError:
                pass
        if 0x20 <= c < 0x7F and c not in (0x7B, 0x7D):
            s.append(chr(c))
        elif 0xA1 <= c <= 0xDF:
            s.append(bytes([c]).decode("cp932"))
        else:
            s.append("{%02X}" % c)
        i += 1
    return "".join(s)


def encode(s):
    out, i = bytearray(), 0
    while i < len(s):
        if s[i] == "{" and i + 3 < len(s) and s[i + 3] == "}":
            out.append(int(s[i + 1:i + 3], 16)); i += 4; continue
        out += s[i].encode("cp932"); i += 1
    return bytes(out)


def write_mes(strings):
    n = len(strings)
    hdr = bytearray(n * 4)
    body = bytearray()
    base = n * 4
    for i, b in enumerate(strings):
        struct.pack_into("<I", hdr, i * 4, base + len(body))
        body += b + b"\x00"
    return bytes(hdr + body)


if __name__ == "__main__":
    d = open(sys.argv[1], "rb").read()
    strs = read_mes(d)
    rt = all(encode(decode(b)) == b for b in strs)
    rebuilt = write_mes(strs)
    print(f"{len(strs)} strings, roundtrip={rt}, rebuild_identical={rebuilt == d[:len(rebuilt)]}, "
          f"size {len(d)} vs {len(rebuilt)}")
    import collections, re
    codes = collections.Counter()
    for b in strs:
        codes.update(re.findall(r"\{[0-9A-F]{2}\}", decode(b)))
    print("control codes:", codes.most_common(15))

"""Recursively unpack the inner archive format used by .lzs / .pac files.

Table of 0x40-byte records at file start:
  u16 count_or_0, u16 type, u32 offset, u32 size, u32 index, char name[0x30]
(count lives in record 0's first u16).

usage: python -I sub_unpack.py <in_root> <out_root>
"""
import os, struct, sys, json


def parse(d):
    if len(d) < 0x40:
        return None
    n = struct.unpack_from("<H", d, 0)[0]
    if n == 0 or n > 4096 or n * 0x40 > len(d):
        return None
    recs = []
    for i in range(n):
        a, t, off, size, idx = struct.unpack_from("<HHIII", d, i * 0x40)
        raw = d[i * 0x40 + 0x10: i * 0x40 + 0x40].split(b"\x00")[0]
        if idx != i or off + size > len(d) or not raw:
            return None
        try:
            name = raw.decode("ascii")
        except UnicodeDecodeError:
            return None
        if not all(32 < ord(c) < 127 for c in name):
            return None
        recs.append(dict(type=t, off=off, size=size, name=name))
    return recs


def walk(path, out, depth=0, log=None):
    d = open(path, "rb").read()
    recs = parse(d)
    if recs is None:
        return False
    os.makedirs(out, exist_ok=True)
    log.append(dict(src=path, out=out, recs=recs))
    for r in recs:
        dst = os.path.join(out, r["name"])
        blob = d[r["off"]: r["off"] + r["size"]]
        open(dst, "wb").write(blob)
        if depth < 6 and (r["name"].endswith((".pac", ".lzs", ".bin")) or True):
            sub = dst + "_"
            if walk(dst, sub, depth + 1, log):
                pass
    return True


def main():
    src, dst = sys.argv[1], sys.argv[2]
    log = []
    for root, _, files in os.walk(src):
        for fn in files:
            if fn.endswith((".lzs", ".pac")):
                p = os.path.join(root, fn)
                rel = os.path.relpath(p, src)
                walk(p, os.path.join(dst, rel + "_"), 0, log)
    json.dump(log, open(os.path.join(dst, "_sub_manifest.json"), "w"), indent=1)
    print("archives unpacked:", len(log))


if __name__ == "__main__":
    main()

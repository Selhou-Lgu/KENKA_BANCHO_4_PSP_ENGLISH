"""Unpack Kenka Banchou 4 PAC0 index + PAC1/PAC2 data into a folder tree.

usage: python -I pac_unpack.py <USRDIR> <outdir>
"""
import os, struct, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lzss


def read_index(path):
    d = open(path, "rb").read()
    ndirs, nfiles, strsize, _ = struct.unpack_from("<IIII", d, 0)
    dirs = [struct.unpack_from("<iiiiii", d, 0x20 + i * 0x20) for i in range(ndirs)]
    ebase = 0x20 + ndirs * 0x20
    ebase = (ebase + 0xFF) & ~0xFF  # entries start 0x100 here
    sbase = ebase + nfiles * 0x40
    assert sbase + strsize == len(d), (hex(sbase), hex(strsize), hex(len(d)))

    def name(o, n):
        return d[sbase + o: sbase + o + n].decode("ascii", "replace")

    ents = []
    for i in range(nfiles):
        # flag: 1 = LZSS (u32 size + stream), 6 = stored raw
        pac, kind, no, nl, off, csz, _z, flag, alloc = struct.unpack_from("<HHIIIIIII", d, ebase + i * 0x40)
        ents.append(dict(i=i, pac=pac, kind=kind, name=name(no, nl), off=off,
                         csize=csz, flag=flag, alloc=alloc))
    return dirs, ents


def entries_with_paths(pac0_path):
    """Return (raw PAC0 bytes, entry list with 'rel' path and 'eoff' entry offset)."""
    d = open(pac0_path, "rb").read()
    dirs, ents = read_index(pac0_path)
    path_of, owner = {}, {}
    for did, parent, first, cnt, _, nent in dirs:
        nm = ents[nent]["name"] if nent >= 0 else ""
        path_of[did] = os.path.join(path_of.get(parent, ""), nm) if parent >= 0 else nm
    for did, parent, first, cnt, _, nent in dirs:
        for k in range(first, first + cnt):
            owner[k] = did
    ebase = ((0x20 + len(dirs) * 0x20) + 0xFF) & ~0xFF
    for e in ents:
        e["rel"] = os.path.join(path_of.get(owner.get(e["i"]), ""), e["name"]).replace("\\", "/")
        e["eoff"] = ebase + e["i"] * 0x40
    return d, ents


def main():
    usr, out = sys.argv[1], sys.argv[2]
    dirs, ents = read_index(os.path.join(usr, "PAC0.BIN"))
    # dir record: id, parent, first, count, count2, name_entry
    path_of = {}
    for did, parent, first, cnt, _, nent in dirs:
        nm = ents[nent]["name"] if nent >= 0 else ""
        path_of[did] = os.path.join(path_of.get(parent, ""), nm) if parent >= 0 else nm
    owner = {}
    for did, parent, first, cnt, _, nent in dirs:
        for k in range(first, first + cnt):
            owner[k] = did
    pacs = {n: open(os.path.join(usr, f"PAC{n}.BIN"), "rb") for n in (1, 2)}
    manifest = []
    for e in ents:
        if e["kind"] != 1 or e["pac"] not in pacs:
            continue
        rel = os.path.join(path_of.get(owner.get(e["i"]), ""), e["name"])
        f = pacs[e["pac"]]
        dst = os.path.join(out, rel)
        only = os.environ.get("ONLY_FLAG")
        if only and str(e["flag"]) != only:
            continue
        f.seek(e["off"]); raw = f.read(e["csize"])
        if e["flag"] == 6:
            data, usize = raw, len(raw)
        else:
            usize = struct.unpack_from("<I", raw, 0)[0]
            data, _ = lzss.decompress(raw, start=4, out_limit=usize)
        ok = len(data) == usize
        os.makedirs(os.path.dirname(dst) or out, exist_ok=True)
        open(dst, "wb").write(data)
        e.update(rel=rel.replace("\\", "/"), usize=usize, ok=ok)
        manifest.append(e)
    json.dump(dict(dirs=dirs, entries=ents), open(os.path.join(out, "_manifest.json"), "w"), indent=1)
    bad = [m["rel"] for m in manifest if not m["ok"]]
    print(f"unpacked {len(manifest)} files, {len(bad)} size mismatches")
    for b in bad[:10]:
        print("  mismatch:", b)


if __name__ == "__main__":
    main()

"""Verify a built ISO: hashes, and every message string == original or expected English.

usage: python -E -P tools/verify_build.py [--sheet X.xlsx] [--wrap 20]
"""
import os, sys, struct, hashlib, argparse, subprocess, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pac_unpack, lzss, sub_unpack, mes_dump, kb4text, build_patch as bp

os.chdir(kb4text.ROOT)
ap = argparse.ArgumentParser()
ap.add_argument("--sheet", default="translation/kb4_translation.xlsx")
ap.add_argument("--wrap", type=int, default=None)
ap.add_argument("--font", choices=["bigram", "fullwidth"], default="bigram")
args = ap.parse_args()
if args.wrap is None:
    args.wrap = 38 if args.font == "bigram" else 20
if args.font == "bigram":
    import json, bigram_font
    _m = json.load(open(os.path.join("build", "bigram_map.json"), encoding="utf-8"))
    _enc = bigram_font.BigramEncoder(_m).encode
else:
    _enc = kb4text.encode

V = os.path.join("build", "verify")
shutil.rmtree(V, ignore_errors=True)
subprocess.run(["7z", "x", bp.OUT_ISO, "-o" + V, "PSP_GAME/USRDIR/PAC0.BIN", "PSP_GAME/USRDIR/PAC1.BIN",
                "PSP_GAME/USRDIR/PAC2.BIN", "-y"], check=True, stdout=subprocess.DEVNULL)
VU = os.path.join(V, "PSP_GAME", "USRDIR")
p0n, new = pac_unpack.entries_with_paths(os.path.join(VU, "PAC0.BIN"))
_, old = pac_unpack.entries_with_paths(os.path.join(bp.USR, "PAC0.BIN"))
pn = {n: open(os.path.join(VU, f"PAC{n}.BIN"), "rb") for n in (1, 2)}
po = {n: open(os.path.join(bp.USR, f"PAC{n}.BIN"), "rb") for n in (1, 2)}
tr = {k: _enc(v[0]) for k, v in bp.load_translations(True, None, args.sheet, args.wrap).items()}


def get(f, e):
    f[e["pac"]].seek(e["off"]); return f[e["pac"]].read(e["csize"])


def unz(b):
    d, _ = lzss.decompress(b, 4, struct.unpack_from("<I", b)[0]); return d


def walk(do, dn, stat):
    ro, rn = sub_unpack.parse(do), sub_unpack.parse(dn)
    if ro is None:
        stat["other"] += do != dn; return
    for a, b in zip(ro, rn):
        xo, xn = do[a["off"]:a["off"] + a["size"]], dn[b["off"]:b["off"] + b["size"]]
        if a["name"].endswith("Mes.bin"):
            so, sn = mes_dump.read_mes(xo), mes_dump.read_mes(xn)
            if len(so) != len(sn):
                stat["count_mismatch"] += 1; continue
            for s1, s2 in zip(so, sn):
                exp = tr.get(kb4text.decode(s1), s1)
                stat["wrong" if s2 != exp else ("translated" if s2 != s1 else "kept")] += 1
        elif a["name"].endswith(".tm2") and xo != xn:
            stat["textures"] += 1
            if TEX.get(hashlib.md5(xo).digest()) != xn:
                stat["tex_wrong"] += 1
        elif sub_unpack.parse(xo) is not None:
            walk(xo, xn, stat)
        else:
            stat["other"] += xo != xn


import tex_edit
TEX = {}
for _pth, _nd in tex_edit.build_all().items():
    TEX[hashlib.md5(open(_pth, "rb").read()).digest()] = _nd
stat = dict(hash_bad=0, moved=0, translated=0, kept=0, wrong=0, other=0, count_mismatch=0, textures=0, tex_wrong=0)
for a, b in zip(old, new):
    if b["kind"] != 1:
        continue
    blob = get(pn, b)
    if hashlib.sha256(blob).digest() != p0n[b["eoff"] + 0x20:b["eoff"] + 0x40]:
        stat["hash_bad"] += 1
    if (a["off"], a["csize"]) != (b["off"], b["csize"]):
        stat["moved"] += 1
        walk(unz(get(po, a)), unz(blob), stat)
print(stat)
print("RESULT:", "PASS" if not (stat["hash_bad"] or stat["wrong"] or stat["other"] or stat["count_mismatch"] or stat["tex_wrong"]) else "FAIL")

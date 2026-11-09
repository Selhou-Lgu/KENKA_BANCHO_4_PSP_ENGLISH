"""Build a translated ISO.

  python -E -P tools/build_patch.py [--extra translation/test_lines.json] [--no-sheet]

Reads English from translation/kb4_translation.xlsx (column D) and, optionally, a JSON
file {"<japanese>": "<english>"}; rewrites every *Mes.bin copy, repacks the containing
archives, appends them to PAC1/PAC2, fixes PAC0 (offset/size/sha256) and writes
build/Kenka Banchou 4 (English).iso.
"""
import os, sys, json, glob, struct, hashlib, argparse, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mes_dump, kb4text, lzss, pac_unpack, iso_patch

ROOT = kb4text.ROOT
os.chdir(ROOT)
USR = os.path.join("extracted", "PSP_GAME", "USRDIR")
SRC_ISO = "Kenka Banchou 4 - Ichinen Sensou (Japan, Asia).iso"
OUT_DIR = "build"
OUT_ISO = os.path.join(OUT_DIR, "Kenka Banchou 4 (English).iso")


def norm(p):
    return os.path.normpath(p)


TAG = __import__("re").compile(r"\{[^{}]*\}")


def vlen(s):
    return len(TAG.sub("", s))


def wrap(text, width, reflow):
    """Word-wrap to `width` visible chars; tags count as zero width.
    reflow=True joins the translator's own breaks first (dialogue)."""
    paras = [text.replace("\n", " ")] if reflow else text.split("\n")
    out = []
    for p in paras:
        line = ""
        for w in p.split(" "):
            if not w:
                continue
            cand = f"{line} {w}" if line else w
            if vlen(cand) <= width or not line:
                line = cand
            else:
                out.append(line); line = w
        out.append(line)
    return "\n".join(out)


def load_translations(use_sheet, extra, sheet_path="translation/kb4_translation.xlsx", width=20):
    tr = {}
    if use_sheet and os.path.exists(sheet_path):
        from openpyxl import load_workbook
        wb = load_workbook(sheet_path, read_only=True)
        for name in ("Menus & UI", "Dialogue"):
            if name not in wb.sheetnames:
                continue
            for row in wb[name].iter_rows(min_row=2, values_only=True):
                if row and len(row) >= 4 and row[2] and row[3] and str(row[3]).strip():
                    en = str(row[3]).replace("\r\n", "\n").strip()
                    if width:
                        en = wrap(en, width, reflow=(name == "Dialogue"))
                    tr[str(row[2])] = (en, row[0])
    if extra:
        for jp, en in json.load(open(extra, encoding="utf-8")).items():
            tr[jp] = (en, "extra")
    return tr


def align_of(off):
    a = 0x20
    while a < 0x800 and off % (a * 2) == 0:
        a *= 2
    return a


def rebuild_archive(orig, recs, replace):
    """replace: {index: new_bytes}. Keeps table, record order and alignment."""
    first = min(r["off"] for r in recs)
    out = bytearray(orig[:first])
    order = sorted(range(len(recs)), key=lambda i: recs[i]["off"])
    end_orig = max(r["off"] + r["size"] for r in recs)
    for i in order:
        r = recs[i]
        blob = replace.get(i, orig[r["off"]:r["off"] + r["size"]])
        a = align_of(r["off"])
        out += b"\x00" * ((-len(out)) % a)
        struct.pack_into("<II", out, i * 0x40 + 4, len(out), len(blob))
        out += blob
    tail = orig[end_orig:]
    out += tail
    out += b"\x00" * ((-len(out)) % 0x20)
    return bytes(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--extra")
    ap.add_argument("--no-sheet", action="store_true")
    ap.add_argument("--sheet", default="translation/kb4_translation.xlsx")
    ap.add_argument("--no-tex", action="store_true")
    ap.add_argument("--no-tanka", action="store_true", help="keep smack-talk battle text Japanese")
    ap.add_argument("--wrap", type=int, default=None, help="line width in chars, 0 = off")
    ap.add_argument("--font", choices=["bigram", "fullwidth"], default="bigram",
                    help="bigram = half-width English (patches EBOOT font)")
    args = ap.parse_args()
    if args.wrap is None:
        args.wrap = 38 if args.font == "bigram" else 20
    t0 = time.time()

    tr = load_translations(not args.no_sheet, args.extra, args.sheet, args.wrap)
    eboot_new = None
    encode = lambda s: kb4text.encode(s)
    if args.font == "bigram":
        import bigram_font
        import eboot_strings, eboot_patch
        eb = open(os.path.join("eboot", "EBOOT_dec.BIN"), "rb").read()
        # EBOOT string translations: translation/eboot_*.json  {japanese: english}
        etr = {}
        for jf in sorted(glob.glob(os.path.join("translation", "eboot_*.json"))):
            etr.update(json.load(open(jf, encoding="utf-8")))
        estr = eboot_strings.find_strings(eb)
        etrans = {a: etr[v["text"]] for a, v in estr.items() if v["text"] in etr}
        epieces = [p for a, en in etrans.items() if not (0x2611C8 <= a < 0x262700)
                   for p in bigram_font.BigramEncoder.pairable_text(en)]
        bigrams = bigram_font.collect_bigrams([en for en, _ in tr.values()] + epieces)
        free = bigram_font.free_slots(set(tr), eb)
        if len(bigrams) > len(free):
            sys.exit(f"need {len(bigrams)} letter-pair glyphs but only {len(free)} free slots")
        mapping = dict(zip(bigrams, free))
        eboot_new, _ = bigram_font.build_font_eboot(eb, mapping)
        benc = bigram_font.BigramEncoder(mapping)
        encode = benc.encode
        if etrans:
            MJ = (0x2611C8, 0x262700)  # mahjong minigame text: drawn with its own ASCII font

            def eenc(vaddr, en):
                if MJ[0] <= vaddr < MJ[1]:
                    return en.replace("　", " ").encode("ascii")
                return benc.sjis(en)
            eenc.by_addr = True
            eboot_new, probs = eboot_patch.apply(
                eboot_new, estr, etrans, eenc,
                [(bigram_font.build_font_eboot.free_start, bigram_font.FONT_REGION[1])])
            for p in probs[:20]:
                print("  EBOOT string skipped:", *p)
        os.makedirs(OUT_DIR, exist_ok=True)
        json.dump(mapping, open(os.path.join(OUT_DIR, "bigram_map.json"), "w", encoding="utf-8"),
                  ensure_ascii=False)
        print(f"half-width font: {len(bigrams)} letter pairs drawn into free glyph slots")
    over = [rid for en, rid in tr.values() if str(rid).startswith("DL") and en.count("\n") >= 3]
    print(f"{len(over)} dialogue lines need more than 3 rows at width {args.wrap}")
    print(f"{len(tr)} translated lines loaded")
    if not tr:
        print("nothing to do"); return

    # 1. rewrite message files
    changed = {}
    errors = []
    cache = {}
    for f in glob.glob("inner/**/*Mes.bin", recursive=True):
        if args.no_tanka and os.path.basename(f) == "DYTankaMes.bin":
            continue
        d = open(f, "rb").read()
        h = hashlib.md5(d).digest()
        if h not in cache:
            strs = mes_dump.read_mes(d)
            new, hit = [], 0
            for b in strs:
                s = kb4text.decode(b)
                if s in tr:
                    en, rid = tr[s]
                    try:
                        new.append(encode(en.replace("\r\n", "\n"))); hit += 1
                        continue
                    except Exception as e:
                        errors.append(f"{rid}: {e}")
                new.append(b)
            cache[h] = mes_dump.write_mes(new) if hit else None
        if cache[h] is not None:
            changed[norm(f)] = cache[h]
    for e in sorted(set(errors))[:30]:
        print("  ENCODE ERROR", e)
    print(f"{len(changed)} message files changed")

    # 1b. edited textures (tex/spec.json) -> every identical copy
    if os.path.exists(os.path.join("tex", "spec.json")) and not args.no_tex:
        import tex_edit
        tex = tex_edit.build_all()
        for pth, data in tex.items():
            changed[norm(pth)] = data
        print(f"{len(tex)} texture copies with English text")

    # 2. propagate up through nested archives (deepest first)
    manifest = json.load(open("inner/_sub_manifest.json"))
    manifest.sort(key=lambda a: -len(norm(a["out"]).split(os.sep)))
    for a in manifest:
        out = norm(a["out"])
        rep = {}
        for i, r in enumerate(a["recs"]):
            p = os.path.join(out, r["name"])
            if p in changed:
                rep[i] = changed[p]
        if rep:
            orig = open(a["src"], "rb").read()
            changed[norm(a["src"])] = rebuild_archive(orig, a["recs"], rep)

    # 3. top-level files -> PAC append + PAC0 fix
    pac0, ents = pac_unpack.entries_with_paths(os.path.join(USR, "PAC0.BIN"))
    pac0 = bytearray(pac0)
    by_rel = {norm(os.path.join("unpacked", e["rel"])): e for e in ents if e["kind"] == 1}
    tops = [(p, by_rel[p]) for p in changed if p in by_rel]
    print(f"{len(tops)} top-level files to recompress")
    pac_size = {n: os.path.getsize(os.path.join(USR, f"PAC{n}.BIN")) for n in (1, 2)}
    appended = {1: bytearray(), 2: bytearray()}
    for k, (p, e) in enumerate(sorted(tops), 1):
        payload = lzss.pack(changed[p])
        n = e["pac"]
        off = pac_size[n] + len(appended[n])
        off_al = (off + 0x7FF) & ~0x7FF
        appended[n] += b"\x00" * (off_al - off)
        appended[n] += payload
        alloc = (len(payload) + 0x7FF) & ~0x7FF
        appended[n] += b"\x00" * (alloc - len(payload))
        struct.pack_into("<II", pac0, e["eoff"] + 0x0C, off_al, len(payload))
        struct.pack_into("<I", pac0, e["eoff"] + 0x1C, alloc)
        pac0[e["eoff"] + 0x20:e["eoff"] + 0x40] = hashlib.sha256(payload).digest()
        if k % 20 == 0 or k == len(tops):
            print(f"  compressed {k}/{len(tops)}")

    # 4. write ISO
    os.makedirs(OUT_DIR, exist_ok=True)
    files = {"/PSP_GAME/USRDIR/PAC0.BIN": bytes(pac0)}
    if eboot_new is not None:
        # decrypted ELF works in PPSSPP / CFW; same size so it is patched in place
        open(os.path.join(OUT_DIR, "EBOOT.BIN"), "wb").write(eboot_new)
        files["/PSP_GAME/SYSDIR/EBOOT.BIN"] = eboot_new
    for n in (1, 2):
        if appended[n]:
            src = open(os.path.join(USR, f"PAC{n}.BIN"), "rb").read()
            files[f"/PSP_GAME/USRDIR/PAC{n}.BIN"] = src + bytes(appended[n])
    iso_patch.patch_iso(SRC_ISO, OUT_ISO, files)
    print(f"done in {time.time() - t0:.0f}s -> {OUT_ISO}")


if __name__ == "__main__":
    main()

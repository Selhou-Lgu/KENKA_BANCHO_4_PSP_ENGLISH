"""Half-width English via two-letter tiles ("bigrams").

Each free kanji slot in the game font is redrawn as two 8x16 letters. Text is encoded
as pairs of letters -> one glyph, so lines hold ~38 letters instead of 19.
"""
import os, re, sys, glob, hashlib, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kb4text, mes_dump, lzss, font_tool, halfwidth, eboot_strings

FONT_REGION = (0x2F7610, 0x34EB10)   # file range holding the 4 compressed fonts
FONT_PTRS = [0x2DD2C8, 0x2DD2D0, 0x2DD2D8, 0x2DD2E0]  # (ptr, name_ptr) entries
TTF = "C:/Windows/Fonts/consolab.ttf"
TTF_FALLBACK = "C:/Windows/Fonts/seguisym.ttf"
TTF_SIZE = 13

TAG = re.compile(r"(\{[^{}]*\})")
HALF_SUBST = {"…": "...", "’": "'", "”": '"', "“": '"', "‘": "'",
              "―": "-", "—": "-", "–": "-", "\t": " ", "\u00a0": " "}


def halfable(ch):
    return 0x20 <= ord(ch) <= 0x7E or ch in "♪÷"


def norm_half(s):
    return "".join(HALF_SUBST.get(c, c) for c in s)


def split_units(line):
    """Split one text line into units: ('tag', '{..}'), ('pair', 'ab'), ('full', 'あ')."""
    out = []
    for seg in TAG.split(line):
        if not seg:
            continue
        if TAG.fullmatch(seg):
            out.append(("tag", seg)); continue
        seg = norm_half(seg)
        run = ""
        for ch in seg:
            if halfable(ch):
                run += ch
            else:
                if run:
                    out += _pairs(run); run = ""
                out.append(("full", ch))
        if run:
            out += _pairs(run)
    return out


def _pairs(run):
    if len(run) % 2:
        run += " "
    return [("pair", run[i:i + 2]) for i in range(0, len(run), 2)]


def collect_bigrams(texts):
    bg = set()
    for s in texts:
        for line in s.split("\n"):
            for k, v in split_units(line):
                if k == "pair":
                    bg.add(v)
    return sorted(bg)


def free_slots(translated_jp, eboot_bytes):
    """Kanji glyph slots used by no Japanese text that will remain in the game."""
    t = kb4text.table()
    first = t.index("亜")
    used, seen = set(), set()
    root = kb4text.ROOT
    for f in glob.glob(os.path.join(root, "inner", "**", "*Mes.bin"), recursive=True):
        d = open(f, "rb").read(); h = hashlib.md5(d).digest()
        if h in seen:
            continue
        seen.add(h)
        for b in mes_dump.read_mes(d):
            s = kb4text.decode(b)
            if s not in translated_jp:
                used |= {kb4text._rev[c] for c in s if c in kb4text._rev}
    for v in eboot_strings.find_strings(eboot_bytes).values():
        used |= {kb4text._rev[c] for c in v["text"] if c in kb4text._rev}
    return [i for i in range(first, len(t)) if i not in used]


class BigramEncoder:
    def __init__(self, mapping):
        self.map = mapping  # "ab" -> glyph index

    def encode(self, s):
        out = bytearray()
        for li, line in enumerate(s.split("\n")):
            if li:
                out.append(0xFE)
            for k, v in split_units(line):
                if k == "tag":
                    out += kb4text.encode(v)
                elif k == "pair":
                    out += kb4text.idx_to_bytes(self.map[v])
                else:
                    out += kb4text.encode(v)
        return bytes(out)

    RAW = re.compile(r"(%[-+ 0-9.]*[dsxXcfu]|\^[A-Za-z])")

    def sjis(self, s):
        """Same text as Shift-JIS using the glyph table (for EBOOT strings).
        printf specifiers (%d, %3d, %s) and ^x colour codes stay raw ASCII."""
        t = kb4text.table()
        out = bytearray()
        for li, line in enumerate(s.split("\n")):
            if li:
                out += b"\n"
            for piece in self.RAW.split(line):
                if not piece:
                    continue
                if self.RAW.fullmatch(piece):
                    out += piece.lstrip("^").encode("ascii"); continue
                for k, v in split_units(piece):
                    if k == "pair":
                        out += t[self.map[v]].encode("cp932")
                    elif k == "full":
                        out += kb4text.SUBST.get(v, v).encode("cp932")
                    else:
                        raise ValueError("tags not allowed in EBOOT strings")
        return bytes(out)

    @classmethod
    def pairable_text(cls, s):
        """Text pieces of an EBOOT string that get letter-pair glyphs."""
        return [p for p in cls.RAW.split(s) if p and not cls.RAW.fullmatch(p)]


def _glyph(ch, cache={}):
    if ch not in cache:
        from PIL import ImageFont
        f = ImageFont.truetype(TTF, TTF_SIZE)
        path = TTF if (ch == " " or f.getmask(ch).getbbox()) else TTF_FALLBACK
        cache[ch] = halfwidth.render_char(ch, path, TTF_SIZE) if ch != " " else [[0] * 8 for _ in range(16)]
    return cache[ch]


def build_font_eboot(eb, mapping):
    """Return patched EBOOT bytes with bigram glyphs drawn into the given slots."""
    eb = bytearray(eb)
    texes = []
    for off in [p for p in FONT_PTRS]:
        ptr, = struct.unpack_from("<I", eb, off)
        d, _ = font_tool.load_tim2(bytes(eb), ptr + eboot_strings.FILE_DELTA)
        texes.append(bytearray(d))
    info = font_tool.tim2_info(bytes(texes[0]))
    for pair, n in mapping.items():
        tex = texes[n // 2048]; layer = (n // 1024) % 2; c = n % 1024
        x0, y0 = (c % 32) * 16, (c // 32) * 16
        cell = [l + r for l, r in zip(_glyph(pair[0]), _glyph(pair[1]))]
        shift = 2 if layer else 0
        mask = 3 << shift
        for y in range(16):
            for x in range(16):
                p = (y0 + y) * 512 + x0 + x
                bi = info["img"] + p // 2
                nib_shift = 4 if p & 1 else 0
                v = (tex[bi] >> nib_shift) & 15
                v = (v & ~mask) | (cell[y][x] << shift)
                tex[bi] = (tex[bi] & ~(15 << nib_shift)) | (v << nib_shift)
    pos = FONT_REGION[0]
    for i, tex in enumerate(texes):
        blob = struct.pack("<I", len(tex)) + lzss.compress_optimal(bytes(tex))
        if pos + len(blob) > FONT_REGION[1]:
            raise RuntimeError("fonts do not fit in the original region")
        eb[pos:pos + len(blob)] = blob
        struct.pack_into("<I", eb, FONT_PTRS[i], pos - eboot_strings.FILE_DELTA)
        pos = (pos + len(blob) + 15) & ~15
    eb[pos:FONT_REGION[1]] = b"\x00" * (FONT_REGION[1] - pos)
    build_font_eboot.free_start = pos  # space after the fonts is reusable
    return bytes(eb), texes


def preview_texts(texes, mapping, sample, path):
    from PIL import Image
    enc = BigramEncoder(mapping)
    lines = sample.split("\n")
    im = Image.new("L", (16 * 22, 18 * len(lines)), 255)
    t = kb4text.table()
    for li, line in enumerate(lines):
        x = 0
        for k, v in split_units(line):
            n = mapping.get(v) if k == "pair" else kb4text._rev.get(v)
            if n is None:
                x += 16
                continue
            tex = texes[n // 2048]; layer = (n // 1024) % 2; c = n % 1024
            x0, y0 = (c % 32) * 16, (c // 32) * 16
            for y in range(16):
                for xx in range(16):
                    p = (y0 + y) * 512 + x0 + xx
                    b = tex[64 + p // 2]; v4 = (b >> 4) if p & 1 else (b & 15)
                    val = (v4 >> 2) if layer else (v4 & 3)
                    im.putpixel((x + xx, li * 18 + y), 255 - val * 85)
            x += 16
    im.resize((im.width * 3, im.height * 3), Image.NEAREST).save(path)

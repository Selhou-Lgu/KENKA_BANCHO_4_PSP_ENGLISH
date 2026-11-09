"""Kenka Banchou 4 text codec.

Encoding (glyph indices into the table in the decrypted EBOOT at 0x26B260):
  0x01-0xC7          -> table[b - 1]
  0xC8-0xE4, q       -> table[0xC7 + (b - 0xC8) * 256 + q]
  0xFE               -> newline  (shown as \\n)
  0xF5, arg          -> {F5:xx}
  other 0xE5-0xFF    -> {XX} control tag
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TABLE_OFF, TABLE_N = 0x26B260, 7488

_table = None
_rev = None


def table():
    global _table, _rev
    if _table is None:
        eb = open(os.path.join(ROOT, "eboot", "EBOOT_dec.BIN"), "rb").read()
        _table = eb[TABLE_OFF:TABLE_OFF + TABLE_N * 2].decode("cp932")
        _rev = {}
        for i, ch in enumerate(_table):
            if ch != "　" or i == _table.index("　"):
                _rev.setdefault(ch, i)
    return _table


def idx_to_bytes(i):
    if i < 0xC7:
        return bytes([i + 1])
    j = i - 0xC7
    return bytes([0xC8 + j // 256, j % 256])


def decode(b):
    t = table()
    out, i, n = [], 0, len(b)
    while i < n:
        c = b[i]
        if 0x01 <= c <= 0xC7:
            ch = t[c - 1]
            # keep exact code for duplicate glyphs (e.g. padding spaces)
            out.append(ch if _rev.get(ch) == c - 1 and ch not in "{}\\" else "{=%04X}" % (c - 1))
            i += 1
        elif 0xC8 <= c <= 0xE4 and i + 1 < n:
            ix = 0xC7 + (c - 0xC8) * 256 + b[i + 1]
            ch = t[ix] if ix < TABLE_N else None
            out.append(ch if ch is not None and _rev.get(ch) == ix and ch not in "{}\\" else "{=%04X}" % ix)
            i += 2
        elif c == 0xFE:
            out.append("\n"); i += 1
        elif c == 0xF5 and i + 1 < n:
            out.append("{F5:%02X}" % b[i + 1]); i += 2
        else:
            out.append("{%02X}" % c); i += 1
    return "".join(out)


# characters the font lacks -> closest glyph it has
SUBST = {"'": "’", '"': "”", "—": "―", "–": "－", "¥": "￥", "‘": "‘", "’": "’",
         "“": "“", "”": "”", "é": "e", "è": "e", "à": "a", "ü": "u", "ö": "o", " ": " ",
         "\t": " "}


def encode(s, ascii_fullwidth=True):
    table()
    out, i = bytearray(), 0
    while i < len(s):
        ch = SUBST.get(s[i], s[i])
        if ch == "\n":
            out.append(0xFE); i += 1; continue
        if ch == "{":
            j = s.index("}", i)
            tag = s[i + 1:j]
            if tag.startswith("="):
                out += idx_to_bytes(int(tag[1:], 16))
            elif tag.startswith("F5:"):
                out += bytes([0xF5, int(tag[3:], 16)])
            else:
                out.append(int(tag, 16))
            i = j + 1; continue
        if ascii_fullwidth and 0x21 <= ord(ch) <= 0x7E:
            ch = chr(ord(ch) + 0xFEE0)
        elif ch == " ":
            ch = "　"
        if ch not in _rev:
            raise ValueError(f"character {ch!r} (U+{ord(ch):04X}) not in font")
        out += idx_to_bytes(_rev[ch]); i += 1
    return bytes(out)

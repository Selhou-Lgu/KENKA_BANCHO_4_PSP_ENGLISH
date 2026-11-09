"""TIM2 (.tm2) reader/writer for 4bpp/8bpp paletted and 32/16-bit textures."""
import struct
from PIL import Image


def parse(d):
    assert d[:4] == b"TIM2", "not TIM2"
    n_pics = struct.unpack_from("<H", d, 6)[0]
    pics, off = [], 0x10
    for _ in range(n_pics):
        total, clut_sz, img_sz, hdr_sz, clut_n, fmt, mip, clut_t, img_t, w, h = struct.unpack_from(
            "<IIIHHBBBBHH", d, off)
        img = off + hdr_sz
        pics.append(dict(off=off, total=total, clut_sz=clut_sz, img_sz=img_sz, hdr_sz=hdr_sz, clut_n=clut_n,
                         clut_t=clut_t, img_t=img_t, w=w, h=h, img=img, clut=img + img_sz, fmt=fmt,
                         swizzled=bool(fmt & 0x80)))
        off += total
    return pics


def _clut(d, p):
    ct = p["clut_t"] & 0x3F
    n = p["clut_n"]
    cols = []
    for i in range(n):
        if ct == 3:  # 32-bit
            r, g, b, a = d[p["clut"] + i * 4:p["clut"] + i * 4 + 4]
        elif ct == 1:  # 16-bit
            v, = struct.unpack_from("<H", d, p["clut"] + i * 2)
            r, g, b, a = (v & 31) << 3, (v >> 5 & 31) << 3, (v >> 10 & 31) << 3, 255 if v & 0x8000 else 0
        else:
            raise ValueError(f"clut type {ct}")
        cols.append((r, g, b, min(255, a * 2) if a <= 0x80 else a))
    # CSM1 swizzle for 256-colour PS2-style palettes
    if n == 256 and not (p["clut_t"] & 0x80):
        sw = cols[:]
        for i in range(256):
            j = (i & ~0x18) | ((i & 0x08) << 1) | ((i & 0x10) >> 1)
            sw[i] = cols[j]
        cols = sw
    return cols


BPP = {4: 4, 5: 8, 3: 32, 1: 16}


def _rowbytes(p):
    return p["w"] * BPP[p["img_t"]] // 8


def unswizzle(buf, rowbytes, h):
    """PSP GE swizzle: 16-byte x 8-row blocks stored contiguously, row-major."""
    out = bytearray(len(buf))
    bw = rowbytes // 16
    src = 0
    for by in range(0, h, 8):
        for bx in range(bw):
            for r in range(8):
                y = by + r
                if y >= h:
                    src += 16; continue
                d = y * rowbytes + bx * 16
                out[d:d + 16] = buf[src:src + 16]
                src += 16
    return bytes(out)


def swizzle(buf, rowbytes, h):
    hp = (h + 7) // 8 * 8
    buf = bytes(buf) + bytes(max(0, rowbytes * hp - len(buf)))
    out = bytearray(rowbytes * hp)
    bw = rowbytes // 16
    dst = 0
    for by in range(0, h, 8):
        for bx in range(bw):
            for r in range(8):
                y = by + r
                if y < h:
                    s = y * rowbytes + bx * 16
                    out[dst:dst + 16] = buf[s:s + 16]
                dst += 16
    return bytes(out)


def pixels(d, p):
    """Linear (unswizzled) pixel bytes."""
    px = d[p["img"]:p["img"] + p["img_sz"]]
    if p["swizzled"] and _rowbytes(p) % 16 == 0:
        px = unswizzle(px, _rowbytes(p), p["h"])
    return px


def indices(d, p):
    w, h, px = p["w"], p["h"], pixels(d, p)
    if p["img_t"] == 4:
        out = []
        for b in px:
            out.append(b & 15); out.append(b >> 4)
        return out[:w * h]
    if p["img_t"] == 5:
        return list(px[:w * h])
    raise ValueError("not paletted")


def to_image(d, p=None):
    p = p or parse(d)[0]
    w, h = p["w"], p["h"]
    if p["img_t"] in (4, 5):
        pal = _clut(d, p)
        idx = indices(d, p)
        im = Image.new("RGBA", (w, h))
        im.putdata([pal[i] if i < len(pal) else (255, 0, 255, 255) for i in idx])
        return im
    if p["img_t"] == 3:
        px = pixels(d, p)[:w * h * 4]
        im = Image.frombytes("RGBA", (w, h), px)
        a = im.getchannel("A").point(lambda v: min(255, v * 2) if v <= 0x80 else v)
        im.putalpha(a)
        return im
    if p["img_t"] == 1:
        im = Image.new("RGBA", (w, h))
        vals = []
        for i in range(w * h):
            v, = struct.unpack_from("<H", d, p["img"] + i * 2)
            vals.append(((v & 31) << 3, (v >> 5 & 31) << 3, (v >> 10 & 31) << 3, 255 if v & 0x8000 else 0))
        im.putdata(vals)
        return im
    raise ValueError(f"image type {p['img_t']}")

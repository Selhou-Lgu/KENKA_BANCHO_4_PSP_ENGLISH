"""Replace Japanese text in TIM2 textures with English, keeping the original CLUT.

Spec (tex/spec.json):  { "<inner relpath of one copy>": {
    "labels": ["Status", ...],          # one per detected box, reading order
    "font": "impact" | "narrow" | "hatten" | "print" | "black",
    "mode": "sprite" (clear to transparent) | "bg" (clear with surrounding colour),
    "boxes": [[x0,y0,x1,y1], ...]       # optional manual boxes (override detection)
    "fill": [r,g,b], "outline": [r,g,b], "stroke": n   # optional style overrides
    "keep": [i, ...]                     # optional: detected boxes to leave untouched
}}
Every copy with identical bytes gets the same edit.
"""
import os, sys, json, glob, hashlib, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tim2
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
F = "C:/Windows/Fonts/"
FONTS = {"impact": F + "impact.ttf", "narrow": F + "ARIALNB.TTF", "hatten": F + "HATTEN.TTF",
         "print": F + "segoeprb.ttf", "black": F + "ariblk.ttf", "bold": F + "arialbd.ttf",
         "serif": F + "georgiab.ttf"}


def load(path):
    d = open(path, "rb").read()
    p = tim2.parse(d)[0]
    return d, p, tim2.to_image(d, p)


def detect_boxes(img, thr=60, grow=2, min_px=6):
    """Connected blobs of opaque pixels, merged when close; returns sorted boxes."""
    a = img.getchannel("A").point(lambda v: 255 if v > thr else 0)
    a = a.filter(ImageFilter.MaxFilter(grow * 2 + 1))
    w, h = a.size
    px = a.load()
    seen = bytearray(w * h)
    boxes = []
    for y in range(h):
        for x in range(w):
            if px[x, y] and not seen[y * w + x]:
                st = [(x, y)]; seen[y * w + x] = 1
                x0 = x1 = x; y0 = y1 = y; n = 0
                while st:
                    cx, cy = st.pop(); n += 1
                    x0, x1, y0, y1 = min(x0, cx), max(x1, cx), min(y0, cy), max(y1, cy)
                    for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                        if 0 <= nx < w and 0 <= ny < h and px[nx, ny] and not seen[ny * w + nx]:
                            seen[ny * w + nx] = 1; st.append((nx, ny))
                if n >= min_px:
                    boxes.append([max(0, x0 - grow + 1), max(0, y0 - grow + 1), min(w, x1 - grow + 2), min(h, y1 - grow + 2)])
    # reading order: rows by centre y, then x
    boxes.sort(key=lambda b: ((b[1] + b[3]) // 2 // 8, b[0]))
    return boxes


def _style(img, box):
    reg = img.crop(box)
    pix = [p for p in reg.getdata() if p[3] > 160]
    if not pix:
        return (255, 255, 255), (0, 0, 0)
    lum = lambda p: p[0] * 0.3 + p[1] * 0.59 + p[2] * 0.11
    pix.sort(key=lum)
    k = max(1, len(pix) // 4)
    def med(ps):
        ps = sorted(ps, key=lum); return tuple(ps[len(ps) // 2][:3])
    return med(pix[-k:]), med(pix[:k])


def _interp_clear(img, box):
    """Erase by blending each row from the colour just left of the box to just right of it."""
    x0, y0, x1, y1 = box
    W = img.width
    lx, rx = max(0, x0 - 1), min(W - 1, x1)
    for y in range(y0, min(y1, img.height)):
        a, b = img.getpixel((lx, y)), img.getpixel((rx, y))
        n = max(1, x1 - x0)
        for x in range(x0, min(x1, W)):
            t = (x - x0 + 0.5) / n
            img.putpixel((x, y), tuple(int(a[i] * (1 - t) + b[i] * t) for i in range(4)))


def _bg_colour(img, box):
    x0, y0, x1, y1 = box
    x1, y1 = min(x1, img.width - 1), min(y1, img.height - 1)
    edge = []
    for x in range(x0, x1):
        for y in (max(0, y0 - 1), min(img.height - 1, y1)):
            edge.append(img.getpixel((x, y)))
    for y in range(y0, y1):
        for x in (max(0, x0 - 1), min(img.width - 1, x1)):
            edge.append(img.getpixel((x, y)))
    from collections import Counter
    return Counter(edge).most_common(1)[0][0]


def fit_size(text, box, font_key, stroke):
    """Largest font size whose rendered text fits the box (height, and width up to 25% squeeze)."""
    bw, bh = box[2] - box[0], box[3] - box[1]
    lines = text.split("\n")
    dummy = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    for size in range(max(6, int(bh * 1.4)), 5, -1):
        f = ImageFont.truetype(FONTS[font_key], size)
        s = stroke if stroke is not None else max(1, size // 9)
        bbs = [dummy.textbbox((0, 0), l, font=f, stroke_width=s) for l in lines]
        tw = max(b[2] - b[0] for b in bbs)
        th = max(b[3] - b[1] for b in bbs) * len(lines) + (len(lines) - 1) * max(1, size // 8)
        if th <= bh and tw <= bw * 1.6:
            return size
    return 6


def render_text(text, box, font_key, fill, outline, stroke, size_cap=None):
    bw, bh = box[2] - box[0], box[3] - box[1]
    path = FONTS[font_key]
    lines = text.split("\n")
    best = None
    for size in range(min(size_cap or 999, max(6, int(bh * 1.4))), 5, -1):
        f = ImageFont.truetype(path, size)
        s = stroke if stroke is not None else max(1, size // 9)
        dummy = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        bbs = [dummy.textbbox((0, 0), l, font=f, stroke_width=s) for l in lines]
        tw = max(b[2] - b[0] for b in bbs)
        lh = max(b[3] - b[1] for b in bbs)
        th = lh * len(lines) + (len(lines) - 1) * max(1, size // 8)
        if th <= bh:
            best = (f, s, tw, th, lh, bbs)
            if tw <= bw:
                break
    f, s, tw, th, lh, bbs = best
    canvas = Image.new("RGBA", (tw + 4, th + 4), (0, 0, 0, 0))
    dr = ImageDraw.Draw(canvas)
    y = 2
    for l, b in zip(lines, bbs):
        lw = b[2] - b[0]
        dr.text((2 - b[0] + (tw - lw) // 2, y - b[1]), l, font=f, fill=fill + (255,),
                stroke_width=s, stroke_fill=outline + (255,))
        y += lh + max(1, f.size // 8)
    if canvas.width > bw:  # squeeze horizontally to fit the sprite box
        canvas = canvas.resize((bw, canvas.height), Image.LANCZOS)
    return canvas


def _expand(boxes, W, frac):
    """Grow boxes sideways into free space: up to the midpoint of the gap to a
    same-row neighbour (or the texture edge), at most frac * width per side."""
    out = []
    for i, b in enumerate(boxes):
        x0, y0, x1, y1 = b
        left, right = 0, W
        for j, o in enumerate(boxes):
            if j == i or o[3] <= y0 or o[1] >= y1:
                continue
            if o[2] <= x0: left = max(left, (o[2] + x0) // 2)
            if o[0] >= x1: right = min(right, (x1 + o[0]) // 2)
        m = int((x1 - x0) * frac) + 2
        out.append([max(left, x0 - m), y0, min(right, x1 + m), y1])
    return out


def apply_spec(img, spec):
    img = img.copy()
    if "grid" in spec:  # [x0, y0, cell_w, cell_h, cols, rows]
        x0, y0, cw, ch, cols, rows = spec["grid"]
        boxes = [[x0 + c * cw, y0 + r * ch, x0 + (c + 1) * cw, y0 + (r + 1) * ch]
                 for r in range(rows) for c in range(cols)]
    else:
        boxes = spec.get("boxes") or detect_boxes(img)
    if spec.get("expand"):
        boxes = _expand(boxes, img.width, spec.get("expand_max", 0.25))
    keep = set(spec.get("keep", []))
    todo = [b for i, b in enumerate(boxes) if i not in keep]
    labels = spec["labels"]
    if len(labels) != len(todo):
        raise ValueError(f"{len(todo)} boxes but {len(labels)} labels: {todo}")
    cap = None
    if spec.get("uniform", True):
        sizes = [fit_size(t, b, spec.get("font", "narrow"), spec.get("stroke"))
                 for b, t in zip(todo, labels) if t]
        cap = min(sizes) if sizes else None
        # don't let one very long label shrink everything below 70% of the typical size
        if sizes:
            typical = sorted(sizes)[len(sizes) // 2]
            cap = max(cap, int(typical * 0.7))
    for box, text in zip(todo, labels):
        if text is None:
            continue
        fill, outline = _style(img, box)
        fill = tuple(spec.get("fill", fill)); outline = tuple(spec.get("outline", outline))
        if "fill_first" in spec and box is todo[0]:
            fill = outline = tuple(spec["fill_first"])
        mode = spec.get("mode", "sprite")
        if mode == "interp":
            _interp_clear(img, box)
        elif mode == "mask":  # erase only bright text pixels, keep panel art
            clr = tuple(spec.get("clear", (30, 34, 30, 255)))
            lm = spec.get("lum_min", 110)
            for yy in range(box[1], min(box[3], img.height)):
                for xx in range(box[0], min(box[2], img.width)):
                    r, g, b, a = img.getpixel((xx, yy))
                    if a > 40 and r * 0.3 + g * 0.59 + b * 0.11 > lm:
                        img.putpixel((xx, yy), clr)
        else:
            clear = (0, 0, 0, 0) if mode == "sprite" else _bg_colour(img, box)
            ImageDraw.Draw(img).rectangle([box[0], box[1], box[2] - 1, box[3] - 1], fill=clear)
        t = render_text(text, box, spec.get("font", "narrow"), fill, outline, spec.get("stroke"), cap)
        if "outline2" in spec:  # outer halo (e.g. red burst behind brush words)
            hp = spec.get("halo", 5)
            big = Image.new("RGBA", (t.width + 2 * hp, t.height + 2 * hp), (0, 0, 0, 0))
            big.paste(t, (hp, hp)); t = big
            m = t.getchannel("A").filter(ImageFilter.MaxFilter(hp * 2 + 1))
            halo = Image.new("RGBA", t.size, tuple(spec["outline2"]) + (255,))
            halo.putalpha(m)
            halo.alpha_composite(t)
            t = halo
        bw, bh = box[2] - box[0], box[3] - box[1]
        if t.width > bw or t.height > bh:  # never spill outside the sprite cell
            k = min(bw / t.width, bh / t.height)
            t = t.resize((max(1, int(t.width * k)), max(1, int(t.height * k))), Image.LANCZOS)
        ox = box[0] + (box[2] - box[0] - t.width) // 2
        oy = box[1] + (box[3] - box[1] - t.height) // 2
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        layer.paste(t, (ox, oy))
        img.alpha_composite(layer)
    return img


def encode_into(d, p, img):
    """Map RGBA image onto the texture's existing palette and return new TIM2 bytes."""
    d = bytearray(d)
    w, h = p["w"], p["h"]
    if p["img_t"] not in (4, 5):
        raise ValueError("only paletted textures supported")
    pal = tim2._clut(bytes(d), p)
    n = 16 if p["img_t"] == 4 else 256
    pal = pal[:n]
    cache = {}
    def nearest(c):
        if c in cache:
            return cache[c]
        r, g, b, a = c
        best, bi = None, 0
        for i, (pr, pg, pb, pa) in enumerate(pal):
            dd = (pr * pa - r * a) ** 2 + (pg * pa - g * a) ** 2 + (pb * pa - b * a) ** 2
            dd = dd / 65025.0 + 3 * (pa - a) ** 2
            if best is None or dd < best:
                best, bi = dd, i
        cache[c] = bi
        return bi
    orig_idx = tim2.indices(bytes(d), p)
    orig_img = tim2.to_image(bytes(d), p).getdata()
    # unchanged pixels keep their exact original index (matters for multi-palette textures)
    new_px = list(img.getdata()); orig_px = list(orig_img)
    idx = [orig_idx[i] if i < len(orig_idx) and i < len(orig_px) and c == orig_px[i] else nearest(c)
           for i, c in enumerate(new_px)]
    if p["img_t"] == 4:
        raw = bytearray((w * h + 1) // 2)
        for i in range(0, w * h, 2):
            raw[i // 2] = idx[i] | ((idx[i + 1] if i + 1 < len(idx) else 0) << 4)
    else:
        raw = bytearray(idx)
    if p["swizzled"] and tim2._rowbytes(p) % 16 == 0:
        raw = tim2.swizzle(bytes(raw), tim2._rowbytes(p), h)
        full = (h // 8) * 8 * tim2._rowbytes(p)  # partial last block row: keep original bytes
        raw = raw[:full] + bytes(d[p["img"] + full:p["img"] + p["img_sz"]])
    raw = bytes(raw)[:p["img_sz"]]
    if len(raw) < p["img_sz"]:  # keep original padding bytes
        raw = raw + bytes(d[p["img"] + len(raw):p["img"] + p["img_sz"]])
    d[p["img"]:p["img"] + p["img_sz"]] = raw
    return bytes(d)


def build_all(spec_path=None, out_json=None, preview_dir=None):
    spec_path = spec_path or os.path.join(ROOT, "tex", "spec.json")
    specs = json.load(open(spec_path, encoding="utf-8"))
    md5_to_paths = {}
    for f in glob.glob(os.path.join(ROOT, "inner", "**", "*.tm2"), recursive=True):
        md5_to_paths.setdefault(hashlib.md5(open(f, "rb").read()).hexdigest(), []).append(os.path.normpath(os.path.relpath(f, ROOT)))
    result = {}
    for rel, spec in specs.items():
        if rel.startswith("_"):
            continue
        src = os.path.join(ROOT, rel)
        d, p, img = load(src)
        new = apply_spec(img, spec)
        nd = encode_into(d, p, new)
        if preview_dir:
            os.makedirs(preview_dir, exist_ok=True)
            back = tim2.to_image(nd)
            pv = Image.new("RGBA", (img.width * 2 + 4, img.height), (120, 120, 130, 255))
            pv.alpha_composite(img, (0, 0)); pv.alpha_composite(back, (img.width + 4, 0))
            pv.save(os.path.join(preview_dir, os.path.basename(rel) + ".png"))
        for cp in md5_to_paths[hashlib.md5(d).hexdigest()]:
            result[cp] = nd
    return result


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["boxes", "preview"])
    ap.add_argument("paths", nargs="*")
    a = ap.parse_args()
    if a.cmd == "boxes":
        for pth in a.paths:
            _, p, img = load(pth)
            print(os.path.basename(pth), p["w"], p["h"], detect_boxes(img))
    else:
        r = build_all(preview_dir=os.path.join(ROOT, "tex", "preview"))
        print(len(r), "texture copies edited")

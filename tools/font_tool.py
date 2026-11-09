"""Extract / render the kenka_font_jis00-03 textures embedded (LZSS) in the EBOOT."""
import os, sys, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lzss
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EBOOT = os.path.join(ROOT, "eboot", "EBOOT_dec.BIN")
# file offset of the u32 size header in front of each compressed TIM2
FONT_OFFS = [0x2F7615 - 5, 0x30E595 - 5, 0x322505 - 5, 0x33BAD5 - 5]


def load_tim2(eb, off):
    usz = struct.unpack_from("<I", eb, off)[0]
    d, used = lzss.decompress(eb[off + 4:off + 4 + 0x40000], 0, usz)
    return d, used + 4


def tim2_info(d):
    total, clut_sz, img_sz, hdr_sz, clut_n, fmt, mip, clut_t, img_t, w, h = struct.unpack_from(
        "<IIIHHBBBBHH", d, 0x10)
    img = 0x10 + hdr_sz
    return dict(w=w, h=h, img=img, img_sz=img_sz, clut=img + img_sz, clut_sz=clut_sz, img_t=img_t)


def to_image(d, scale=1):
    t = tim2_info(d)
    w, h = t["w"], t["h"]
    px = d[t["img"]:t["img"] + t["img_sz"]]
    im = Image.new("L", (w, h))
    vals = bytearray()
    for b in px:
        vals.append((b & 15) * 17); vals.append((b >> 4) * 17)
    im.putdata(vals[:w * h])
    if scale != 1:
        im = im.resize((w * scale, h * scale), Image.NEAREST)
    return im


if __name__ == "__main__":
    eb = open(EBOOT, "rb").read()
    os.makedirs(os.path.join(ROOT, "font"), exist_ok=True)
    for i, off in enumerate(FONT_OFFS):
        d, used = load_tim2(eb, off)
        open(os.path.join(ROOT, "font", f"kenka_font_jis{i:02d}.tm2"), "wb").write(d)
        to_image(d).save(os.path.join(ROOT, "font", f"jis{i:02d}.png"))
        print(i, tim2_info(d), "compressed", hex(used))

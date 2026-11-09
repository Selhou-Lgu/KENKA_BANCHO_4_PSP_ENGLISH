"""Render 8x16, 2-bit (0..3) half-width glyphs from a TrueType font."""
from PIL import Image, ImageDraw, ImageFont

SS = 4  # supersampling


def render_char(ch, font_path, size, base_y=12, x_off=0, bold=0):
    W, H = 8 * SS, 16 * SS
    im = Image.new("L", (W, H), 0)
    f = ImageFont.truetype(font_path, size * SS)
    dr = ImageDraw.Draw(im)
    adv = f.getlength(ch)
    x = (W - adv) / 2 + x_off * SS
    dr.text((x, base_y * SS), ch, fill=255, font=f, anchor="ls",
            stroke_width=bold, stroke_fill=255)
    small = im.resize((8, 16), Image.BOX)
    px = list(small.getdata())
    # quantize to 4 levels, slightly biased up for legibility
    return [[min(3, int(v / 255 * 3 + 0.35)) for v in px[y * 8:(y + 1) * 8]] for y in range(16)]


def preview(text, font_path, size, path, **kw):
    cols = len(text)
    im = Image.new("L", (cols * 8, 16), 255)
    for i, ch in enumerate(text):
        g = render_char(ch, font_path, size, **kw)
        for y in range(16):
            for x in range(8):
                im.putpixel((i * 8 + x, y), 255 - g[y][x] * 85)
    return im

"""Render contact sheets of UI textures so text-bearing ones can be found by eye."""
import os, sys, glob, hashlib, re, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tim2
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEEP = re.compile(r"(menu|pause|status|title|shop|list|option|name_|net_|skill|route|sakusen|album|edit_|"
                  r"phone_(menu|win|bar|huki|panel|frame|border)|main_|month|myroom|repo|ath_|eva_|episode|"
                  r"end_|tramp|goods|b_help|item00|item_icon|minmap|tango|tan_|tanka|metsubushi|shabai|asahi|"
                  r"subspace|keepout|base_frame|wide_win|winbar|winframe|winbg|timing|new_flash|"
                  r"shiori|mj_|nas_|hpmp|gauge|onijima|iyokan|mango|morobosi|yagami|tex_ohsho|reflex)", re.I)


def collect():
    seen, out = set(), []
    for f in sorted(glob.glob(os.path.join(ROOT, "inner", "**", "*.tm2"), recursive=True)):
        n = os.path.basename(f)
        if not KEEP.search(n) or os.sep + "map_" in f or "parts_" in f:
            continue
        d = open(f, "rb").read()
        h = hashlib.md5(d).hexdigest()
        if h in seen:
            continue
        seen.add(h)
        out.append(f)
    return out


def sheet(files, path, cell=240):
    cols = 4
    rows = (len(files) + cols - 1) // cols
    im = Image.new("RGB", (cols * cell, rows * (cell + 14)), (60, 60, 70))
    dr = ImageDraw.Draw(im)
    for i, f in enumerate(files):
        x, y = (i % cols) * cell, (i // cols) * (cell + 14)
        try:
            t = tim2.to_image(open(f, "rb").read())
        except Exception as e:
            dr.text((x + 4, y + 4), f"ERR {e}", fill=(255, 80, 80)); continue
        t.thumbnail((cell - 4, cell - 4))
        bg = Image.new("RGBA", t.size, (120, 120, 130, 255))
        bg.alpha_composite(t)
        im.paste(bg.convert("RGB"), (x + 2, y + 14))
        dr.text((x + 2, y + 1), f"{i}:{os.path.basename(f)[:30]}", fill=(255, 255, 0))
    im.save(path)


if __name__ == "__main__":
    fs = collect()
    os.makedirs(os.path.join(ROOT, "tex"), exist_ok=True)
    json.dump([os.path.relpath(f, ROOT) for f in fs], open(os.path.join(ROOT, "tex", "ui_list.json"), "w"), indent=0)
    per = 16
    for k in range(0, len(fs), per):
        sheet(fs[k:k + per], os.path.join(ROOT, "tex", f"sheet_{k // per:02d}.png"))
    print(len(fs), "textures,", (len(fs) + per - 1) // per, "sheets")

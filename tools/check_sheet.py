"""Lint a filled translation sheet.  usage: python -E -P tools/check_sheet.py <xlsx>"""
import sys, re, os, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
import kb4text
from openpyxl import load_workbook

TAG = re.compile(r"\{[^{}]*\}")
JP = re.compile(r"[぀-ヿ一-鿿]")
wb = load_workbook(sys.argv[1], read_only=True)
issues = collections.defaultdict(list)
badchars = collections.Counter()
stats = {}
for name in ("Menus & UI", "Dialogue"):
    n = 0
    for r in wb[name].iter_rows(min_row=2, values_only=True):
        rid, jp, en = r[0], str(r[2] or ""), r[3]
        if en is None or not str(en).strip():
            issues["empty"].append(rid); continue
        en = str(en).replace("\r\n", "\n"); n += 1
        tj, te = TAG.findall(jp), TAG.findall(en)
        if sorted(tj) != sorted(te):
            issues["tags differ"].append(rid)
        if re.search(r"\{\s|\s\}|｛|｝", en) or en.count("{") != en.count("}"):
            issues["mangled tag"].append(rid)
        if JP.search(TAG.sub("", en)):
            issues["japanese left in english"].append(rid)
        try:
            kb4text.encode(en)
        except ValueError as e:
            issues["char not in font"].append(rid)
            badchars[str(e).split("'")[1] if "'" in str(e) else str(e)] += 1
        except Exception:
            issues["bad tag syntax"].append(rid)
        longest = max(len(TAG.sub("", l)) for l in en.split("\n"))
        if longest > 28:
            issues["line > 28 chars"].append(rid)
        jl = len(TAG.sub("", jp).replace("\n", ""))
        el = len(TAG.sub("", en).replace("\n", ""))
        if jl >= 6 and (el < jl * 0.4 or el > jl * 6):
            issues["length looks off (shifted row?)"].append(rid)
    stats[name] = n
print("filled:", stats)
for k, v in sorted(issues.items(), key=lambda t: -len(t[1])):
    print(f"{k:34s} {len(v):6d}   e.g. {v[:6]}")
print("chars not in font:", badchars.most_common(25))

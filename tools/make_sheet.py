"""Build translation/kb4_translation.xlsx: one row per unique Japanese string.

Sheets: "Menus & UI" (DY*/DN* files) and "Dialogue" (DTEventMes).
Fill the English column; keep {..} tags and line breaks where they make sense.
"""
import os, sys, glob, hashlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mes_dump as m, kb4text as k
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

ROOT = k.ROOT
os.chdir(ROOT)
OUT = "translation/kb4_translation.xlsx"
if os.path.exists(OUT) and "--force" not in sys.argv:
    from openpyxl import load_workbook
    _wb = load_workbook(OUT, read_only=True)
    if any(r[3] for n in ("Menus & UI", "Dialogue") if n in _wb.sheetnames
           for r in _wb[n].iter_rows(min_row=2, values_only=True) if len(r) > 3):
        sys.exit(f"{OUT} already has English filled in; refusing to overwrite (use --force)")

rows = {}  # japanese -> dict
seen = set()
for f in sorted(glob.glob("inner/**/*Mes.bin", recursive=True)):
    d = open(f, "rb").read()
    h = hashlib.md5(d).hexdigest()
    if h in seen:
        continue
    seen.add(h)
    base = os.path.basename(f)
    sheet = "Dialogue" if base == "DTEventMes.bin" else "Menus & UI"
    for i, b in enumerate(m.read_mes(d)):
        s = k.decode(b)
        if not s.strip():
            continue
        r = rows.setdefault(s, dict(sheet=sheet, src=set(), first=(base, i)))
        r["src"].add(base)

wb = Workbook()
wb.remove(wb.active)
head = ["ID", "Source file", "Japanese", "English", "Notes"]
for name in ("Menus & UI", "Dialogue"):
    ws = wb.create_sheet(name)
    ws.append(head)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="333333")
    items = [(s, r) for s, r in rows.items() if r["sheet"] == name]
    items.sort(key=lambda t: (t[1]["first"][0], t[1]["first"][1]))
    for n, (s, r) in enumerate(items, 1):
        ws.append([f"{'UI' if name.startswith('M') else 'DL'}{n:05d}",
                   ", ".join(sorted(r["src"])), s, "", ""])
    for col, w in zip("ABCDE", (10, 22, 60, 60, 30)):
        ws.column_dimensions[col].width = w
    for row in ws.iter_rows(min_row=2):
        for c in row[2:4]:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "C2"
    print(f"{name}: {len(items)} unique lines, {sum(len(s) for s, _ in items)} chars")

ws = wb.create_sheet("README", 0)
for line in [
    "Kenka Banchou 4 translation sheet",
    "",
    "Fill in column D (English). Leave a cell empty to keep the Japanese.",
    "Line breaks in the Japanese cell are real in-game line breaks; keep lines short (~20 chars for now).",
    "Tags like {F3}{F5:0C} are control codes (colors, pauses, names). Copy them across as-is,",
    "in roughly the same position. Machine translators sometimes break them - double-check.",
    "Each unique line appears once even if it shows up in many scenes.",
]:
    ws.append([line])
ws.column_dimensions["A"].width = 110

os.makedirs("translation", exist_ok=True)
wb.save("translation/kb4_translation.xlsx")
print("saved translation/kb4_translation.xlsx")

"""Scan files for Shift-JIS text runs; report which files hold the most text."""
import os, sys, re, collections

# a run of >=3 SJIS double-byte chars (kana/kanji/fullwidth)
RUN = re.compile(rb"(?:[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc]){3,}")


def score(path):
    d = open(path, "rb").read()
    runs = RUN.findall(d)
    good = 0
    for r in runs:
        try:
            r.decode("cp932"); good += len(r) // 2
        except UnicodeDecodeError:
            pass
    return good, len(runs)


root = sys.argv[1]
by_ext = collections.Counter()
res = []
for dp, _, fs in os.walk(root):
    for f in fs:
        if f.endswith((".tm2", ".gmo", ".at3", ".PNG", ".json")):
            continue
        p = os.path.join(dp, f)
        g, n = score(p)
        if g:
            res.append((g, n, os.path.relpath(p, root)))
            by_ext[os.path.splitext(f)[1] or f] += g
res.sort(reverse=True)
print("chars by ext:", by_ext.most_common(10))
print("files with text:", len(res), "total chars:", sum(r[0] for r in res))
for r in res[:40]:
    print(r)

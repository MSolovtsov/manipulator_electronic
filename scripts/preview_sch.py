#!/usr/bin/env python3
"""Быстрое превью схемы .kicad_sch в PNG (без KiCad): корпуса, выводы, провода, узлы, тексты.
Запуск: python3 scripts/preview_sch.py boards/MC/MC.kicad_sch [out.png] [x0 y0 x1 y1]"""
import re
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt   # noqa: E402
from matplotlib.patches import Rectangle, Circle, Polygon  # noqa: E402

src = sys.argv[1]
out = sys.argv[2] if len(sys.argv) > 2 else src.replace(".kicad_sch", "_preview.png")
s = open(src, encoding="utf-8").read()
lib = s[s.index("(lib_symbols"):s.index("\n  (symbol (lib_id")]
paper = re.search(r'\(paper "(\w+)"\)', s).group(1)
W, H = {"A3": (420, 297), "A4": (297, 210), "A2": (594, 420)}[paper]

symdefs = {}
for m in re.finditer(r'\n  \(symbol "manipulator:([^"]+)"(.*?)\n  \)(?=\n)', lib, re.S):
    body = m.group(2)
    prims = []
    for r in re.finditer(r'\(rectangle \(start ([-\d.]+) ([-\d.]+)\) \(end ([-\d.]+) ([-\d.]+)\) \(stroke \(width [\d.]+\) \(type (\w+)\)', body):
        prims.append(("rect", tuple(map(float, r.groups()[:4])), r.group(5)))
    for r in re.finditer(r'\(polyline \(pts ((?:\(xy [-\d.]+ [-\d.]+\) ?)+)\)', body):
        pts = [tuple(map(float, q)) for q in re.findall(r'\(xy ([-\d.]+) ([-\d.]+)\)', r.group(1))]
        prims.append(("poly", pts, None))
    for r in re.finditer(r'\(circle \(center ([-\d.]+) ([-\d.]+)\) \(radius ([-\d.]+)\)', body):
        prims.append(("circ", tuple(map(float, r.groups())), None))
    for r in re.finditer(r'\(arc \(start ([-\d.]+) ([-\d.]+)\) \(mid ([-\d.]+) ([-\d.]+)\) \(end ([-\d.]+) ([-\d.]+)\)', body):
        prims.append(("arc", tuple(map(float, r.groups())), None))
    pins = re.findall(r'\(pin \w+ line \(at ([-\d.]+) ([-\d.]+) (\d+)\) \(length ([-\d.]+)\)( \(hide yes\))?', body)
    texts = re.findall(r'\(text "([^"]+)" \(at ([-\d.]+) ([-\d.]+) \d+\)', body)
    symdefs[m.group(1)] = (prims, pins, texts)

fig, ax = plt.subplots(figsize=(W / 20, H / 20))
ax.add_patch(Rectangle((0, 0), W, H, fill=False, lw=1))
ax.add_patch(Rectangle((20, 5), W - 25, H - 10, fill=False, lw=0.6, ec="gray"))
ax.add_patch(Rectangle((W - 5 - 185, H - 5 - 55), 185, 55, fill=False, lw=0.6, ec="gray"))


def T(x, y, px, py, rot):
    return (x + px, y - py) if rot == 0 else (x - px, y + py)


for inst in re.finditer(r'\n  \(symbol \(lib_id "manipulator:([^"]+)"\) \(at ([-\d.]+) ([-\d.]+) (\d+)\)(.*?)\n  \)', s, re.S):
    name, x, y, rot, body = inst.group(1), float(inst.group(2)), float(inst.group(3)), int(inst.group(4)), inst.group(5)
    prims, pins, texts = symdefs[name]
    col = "darkred"
    for kind, data, style in prims:
        if kind == "rect":
            x1, y1, x2, y2 = data
            (ax1, ay1), (ax2, ay2) = T(x, y, x1, y1, rot), T(x, y, x2, y2, rot)
            ax.add_patch(Rectangle((min(ax1, ax2), min(ay1, ay2)), abs(ax2 - ax1), abs(ay2 - ay1), fill=False, lw=0.7, ec=col,
                                   ls="--" if style == "dash" else "-"))
        elif kind == "poly":
            pts = [T(x, y, px, py, rot) for px, py in data]
            ax.plot([p[0] for p in pts], [p[1] for p in pts], color=col, lw=0.7)
        elif kind == "circ":
            cx, cy, r = data; c = T(x, y, cx, cy, rot)
            ax.add_patch(Circle(c, r, fill=False, lw=0.7, ec=col))
        elif kind == "arc":
            pts = [T(x, y, data[i], data[i + 1], rot) for i in (0, 2, 4)]
            ax.plot([p[0] for p in pts], [p[1] for p in pts], color=col, lw=0.7)
    for px, py, ang, ln, hidden in pins:
        if hidden:
            continue
        px, py, ang, ln = float(px), float(py), int(ang), float(ln)
        dx, dy = {0: (1, 0), 180: (-1, 0), 90: (0, 1), 270: (0, -1)}[ang]
        a = T(x, y, px, py, rot); b = T(x, y, px + dx * ln, py + dy * ln, rot)
        ax.plot([a[0], b[0]], [a[1], b[1]], color=col, lw=0.9)
        ax.plot(a[0], a[1], "o", color=col, ms=1.5)
    for t, tx, ty in texts:
        p = T(x, y, float(tx), float(ty), rot); ax.text(p[0], p[1], t, fontsize=4, ha="center", va="center", color=col)
    for prop in re.finditer(r'\(property "(Reference|Value)" "([^"]+)" \(at ([-\d.]+) ([-\d.]+) 0\)(.*?)\(effects \(font[^)]*\) \(size ([\d.]+)', body):
        if "(hide yes)" in prop.group(5):
            continue
        val = prop.group(2)
        just = re.search(r'\(justify (\w+)\)', prop.group(5))
        ha = {"left": "left", "right": "right"}.get(just.group(1) if just else "", "center")
        ax.text(float(prop.group(3)), float(prop.group(4)), val, fontsize=float(prop.group(6)) * 2.6, ha=ha, va="center",
                color="navy" if val.startswith(("+", "GND", "3V3")) or prop.group(1) == "Value" else "darkgreen")
for w in re.finditer(r'\(wire \(pts \(xy ([-\d.]+) ([-\d.]+)\) \(xy ([-\d.]+) ([-\d.]+)\)\)', s):
    x1, y1, x2, y2 = map(float, w.groups()); ax.plot([x1, x2], [y1, y2], color="green", lw=0.9)
for j in re.finditer(r'\(junction \(at ([-\d.]+) ([-\d.]+)\)', s):
    ax.plot(float(j.group(1)), float(j.group(2)), "o", color="green", ms=3)
for n in re.finditer(r'\(no_connect \(at ([-\d.]+) ([-\d.]+)\)', s):
    ax.plot(float(n.group(1)), float(n.group(2)), "x", color="blue", ms=4)
for t in re.finditer(r'\n  \(text "([^"]+)"[^\n]*\(at ([-\d.]+) ([-\d.]+) 0\)[^\n]*\(size ([\d.]+)', s):
    ax.text(float(t.group(2)), float(t.group(3)), t.group(1), fontsize=float(t.group(4)) * 2.6, ha="left", va="center", color="black")
if len(sys.argv) > 6:
    x0, y0, x1, y1 = map(float, sys.argv[3:7]); ax.set_xlim(x0, x1); ax.set_ylim(y1, y0)
else:
    ax.set_xlim(-2, W + 2); ax.set_ylim(H + 2, -2)
ax.set_aspect("equal"); ax.axis("off")
plt.savefig(out, dpi=int(__import__("os").environ.get("DPI","130")), bbox_inches="tight"); print(out)

#!/usr/bin/env python3
"""Проверка платы, собранной gen_PS_pcb.py (до DRC в KiCad): геометрия по данным генератора.

  1. связность: все площадки одной цепи соединены дорожками или зоной своей цепи (на своём слое);
  2. зазоры медь–медь между разными цепями (площадки, дорожки, по слоям) ≥ CLR;
  3. пересечения courtyard'ов; медь до края платы ≥ 0,5 мм; всё внутри контура;
  4. дорожки чужих цепей внутри силовой зоны +24V (режут медь) — предупреждение;
  5. гальванический остров: расстояние от меди острова до любой меди силовой стороны ≥ 2 мм;
  6. нормы Резонита (базовый уровень): отверстия ≥ 0,3 / NPTH ≥ 0,5, поясок ≥ 0,2, медь до NPTH ≥ 0,2,
     отверстие–отверстие ≥ 0,2, шелкография: линия ≥ 0,15, текст ≥ 1,0.

Запуск: python3 scripts/check_pcb.py [КОД]   (по умолчанию PS; читает scripts/gen_<КОД>_pcb.py как модуль)
Дополнительно рисует boards/<КОД>/<КОД>_preview.png (не для репозитория — файл в .gitignore).
Переходные отверстия (via) учитываются как площадки своей цепи на обоих слоях.
"""
import importlib.util
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODE = sys.argv[1] if len(sys.argv) > 1 else "PS"
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("gen", ROOT / "scripts" / f"gen_{CODE}_pcb.py")
g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)

CLR = g.CLR
ISO = 2.0
EDGE = 0.5
problems, warnings = [], []


# ---- сбор меди --------------------------------------------------------------------------------------------
class Pad:
    def __init__(self, ref, num, x, y, r, net, layers, kind):
        self.ref, self.num, self.x, self.y, self.r, self.net, self.layers, self.kind = ref, num, x, y, r, net, layers, kind

    def __repr__(self):
        return f"{self.ref}.{self.num or 'NPTH'}@({self.x},{self.y})"


pads = []
for ref, fpname, value, x0, y0, nets in g.PLACE:
    for num, kind, shape, x, y, sx, sy, drill, ang in g.FPS[fpname].pads:
        r = max(sx, sy) / 2 if shape != "circle" else sx / 2
        if kind == "np_thru_hole" and shape == "oval":
            r = max(sx, sy) / 2                       # паз — грубо кругом по длине
        layers = {"F.Cu"} if kind == "smd" else {"F.Cu", "B.Cu"}
        net = nets.get(num, "") if num else ""
        if net.startswith("unconnected-"):
            net = ""
        pads.append(Pad(ref, num, round(x0 + x, 3), round(y0 + y, 3), r, net, layers, kind))
for i, (hx, hy) in enumerate(g.HOLES):
    pads.append(Pad(f"H{i + 1}", "", hx, hy, 1.6, "", {"F.Cu", "B.Cu"}, "np_thru_hole"))
for i, (net, vx, vy) in enumerate(getattr(g, "vias", [])):
    pads.append(Pad("via", str(i), vx, vy, g.VIA_D / 2, net, {"F.Cu", "B.Cu"}, "via"))

segs = []   # (net, layer, w, (x1,y1), (x2,y2))
for net, layer, w, pts in g.tracks:
    for a, b in zip(pts, pts[1:]):
        segs.append((net, layer, w, a, b))


def seg_pt_dist(a, b, p):
    ax, ay = a; bx, by = b; px, py = p
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0 if L2 == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / L2))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(px - cx, py - cy)


def seg_seg_dist(a, b, c, d):
    def cross(o, p, q):
        return (p[0] - o[0]) * (q[1] - o[1]) - (p[1] - o[1]) * (q[0] - o[0])
    d1, d2 = cross(c, d, a), cross(c, d, b)
    d3, d4 = cross(a, b, c), cross(a, b, d)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)) and d1 and d2 and d3 and d4:
        return 0.0
    return min(seg_pt_dist(a, b, c), seg_pt_dist(a, b, d), seg_pt_dist(c, d, a), seg_pt_dist(c, d, b))


def in_poly(p, poly):
    x, y = p; inside = False
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        if (y1 > y) != (y2 > y):
            xi = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if xi > x:
                inside = not inside
    return inside


def poly_dist(p, poly):
    """Расстояние от точки до полигона (0 внутри)."""
    if in_poly(p, poly):
        return 0.0
    return min(seg_pt_dist(a, b, p) for a, b in zip(poly, poly[1:] + poly[:1]))


ZONES = [(n, net, layer, poly) for n, (net, layer, poly, kind) in g.ZONES.items() if kind == "copper"]
KEEPOUTS = [poly for n, (net, layer, poly, kind) in g.ZONES.items() if kind == "keepout"]
NOPOUR = [poly for n, (net, layer, poly, kind) in g.ZONES.items() if kind in ("keepout", "keepout_pour")]


def in_nopour(p):
    return any(in_poly(p, k) for k in NOPOUR)


def copper_dist(p, poly):
    """Расстояние от точки до меди зоны: полигон минус вырезы (keepout copperpour)."""
    if not in_poly(p, poly):
        return poly_dist(p, poly)
    for k in NOPOUR:
        if in_poly(p, k):
            return min(seg_pt_dist(a, b, p) for a, b in zip(k, k[1:] + k[:1]))
    return 0.0

# ---- 1. связность --------------------------------------------------------------------------------------------
parent = {}


def find(a):
    while parent.setdefault(a, a) != a:
        a = parent[a]
    return a


def union(a, b):
    parent[find(a)] = find(b)


netpads = {}
for p in pads:
    if p.net:
        netpads.setdefault(p.net, []).append(p)
for net, layer, w, a, b in segs:
    key_a, key_b = ("s", layer, a), ("s", layer, b)
    union(key_a, key_b)
    for p in pads:
        if p.net == net and layer in p.layers:
            for end, key in ((a, key_a), (b, key_b)):
                if math.hypot(p.x - end[0], p.y - end[1]) <= p.r + 1e-6:
                    union(("p", p.ref, p.num), key)
            # дорожка проходит через площадку своей цепи (Т-соединение)
            if seg_pt_dist(a, b, (p.x, p.y)) <= p.r - 0.05:
                union(("p", p.ref, p.num), key_a)
# дорожки одной цепи, касающиеся друг друга на одном слое
for i, (n1, l1, w1, a1, b1) in enumerate(segs):
    for n2, l2, w2, a2, b2 in segs[i + 1:]:
        if n1 == n2 and l1 == l2 and seg_seg_dist(a1, b1, a2, b2) <= (w1 + w2) / 2 + 1e-6:
            union(("s", l1, a1), ("s", l2, a2))
# зоны
for zname, znet, zlayer, poly in ZONES:
    for p in pads:
        if p.net == znet and zlayer in p.layers and in_poly((p.x, p.y), poly) and not in_nopour((p.x, p.y)):
            union(("p", p.ref, p.num), ("z", zname))
    for net, layer, w, a, b in segs:
        if net == znet and layer == zlayer and any(in_poly(q, poly) and not in_nopour(q) for q in (a, b)):
            union(("s", layer, a), ("z", zname))
for net, plist in netpads.items():
    roots = {find(("p", p.ref, p.num)) for p in plist}
    if len(roots) > 1:
        groups = {}
        for p in plist:
            groups.setdefault(find(("p", p.ref, p.num)), []).append(repr(p))
        problems.append(f"цепь {net} не связана: " + " | ".join(", ".join(v) for v in groups.values()))

# ---- 2. зазоры --------------------------------------------------------------------------------------------------
for i, p in enumerate(pads):
    for q in pads[i + 1:]:
        if p.net == q.net and p.net:
            continue
        if not (p.layers & q.layers):
            continue
        d = math.hypot(p.x - q.x, p.y - q.y) - p.r - q.r
        if d < CLR - 1e-6:
            problems.append(f"зазор {d:.2f} < {CLR}: {p} — {q}")
for net, layer, w, a, b in segs:
    for p in pads:
        if p.net == net and net or layer not in p.layers:
            continue
        d = seg_pt_dist(a, b, (p.x, p.y)) - w / 2 - p.r
        if d < CLR - 1e-6:
            problems.append(f"зазор {d:.2f} < {CLR}: дорожка {net} {layer} {a}-{b} — {p}")
for i, (n1, l1, w1, a1, b1) in enumerate(segs):
    for n2, l2, w2, a2, b2 in segs[i + 1:]:
        if n1 == n2 or l1 != l2:
            continue
        d = seg_seg_dist(a1, b1, a2, b2) - (w1 + w2) / 2
        if d < CLR - 1e-6:
            problems.append(f"зазор {d:.2f} < {CLR}: {n1} {a1}-{b1} — {n2} {a2}-{b2} ({l1})")

# ---- 3. courtyard, край платы --------------------------------------------------------------------------------------
import re


def courtyards(fp):
    boxes = []
    for s in fp.gr:
        if '"F.CrtYd"' not in s:
            continue
        m = re.search(r"\(fp_rect \(start ([-\d.]+) ([-\d.]+)\) \(end ([-\d.]+) ([-\d.]+)\)", s)
        if m:
            x1, y1, x2, y2 = map(float, m.groups()); boxes.append((min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)))
        m = re.search(r"\(fp_circle \(center ([-\d.]+) ([-\d.]+)\) \(end ([-\d.]+) ([-\d.]+)\)", s)
        if m:
            cx, cy, ex, ey = map(float, m.groups()); r = math.hypot(ex - cx, ey - cy)
            boxes.append((cx - r, cy - r, cx + r, cy + r))
    return boxes


CY = []
for ref, fpname, value, x0, y0, nets in g.PLACE:
    for x1, y1, x2, y2 in courtyards(g.FPS[fpname]):
        CY.append((ref, x0 + x1, y0 + y1, x0 + x2, y0 + y2))
for i, (hx, hy) in enumerate(g.HOLES):
    CY.append((f"H{i + 1}", hx - 3.3, hy - 3.3, hx + 3.3, hy + 3.3))
for i, (r1, ax1, ay1, ax2, ay2) in enumerate(CY):
    for r2, bx1, by1, bx2, by2 in CY[i + 1:]:
        if r1 != r2 and ax1 < bx2 and bx1 < ax2 and ay1 < by2 and by1 < ay2:
            problems.append(f"courtyard пересекаются: {r1} и {r2}")
    if ax1 < 0 or ay1 < 0 or ax2 > g.BOARD_W or ay2 > g.BOARD_H:
        problems.append(f"courtyard {r1} выходит за контур платы")
for p in pads:
    if p.kind == "np_thru_hole":
        continue
    if min(p.x - p.r, p.y - p.r, g.BOARD_W - p.x - p.r, g.BOARD_H - p.y - p.r) < EDGE:
        problems.append(f"медь ближе {EDGE} мм к краю: {p}")
for net, layer, w, a, b in segs:
    for pt in (a, b):
        if min(pt[0], pt[1], g.BOARD_W - pt[0], g.BOARD_H - pt[1]) - w / 2 < EDGE:
            problems.append(f"дорожка {net} у края платы: {pt}")
# keepout под модулем: медь внутри запрещена
for poly in KEEPOUTS:
    for net, layer, w, a, b in segs:
        if in_poly(a, poly) or in_poly(b, poly):
            problems.append(f"дорожка {net} внутри keepout {a}-{b}")
    for p in pads:
        if p.net and in_poly((p.x, p.y), poly):
            problems.append(f"площадка внутри keepout: {p}")

# ---- 4. чужие дорожки внутри зоны +24V (F.Cu) ---------------------------------------------------------------------
POWER_ZONE = getattr(g, "POWER_ZONE", None)
for zname, znet, zlayer, poly in ZONES:
    if znet != POWER_ZONE:
        continue
    for net, layer, w, a, b in segs:
        if layer == zlayer and net != znet and any(in_poly(q, poly) and not in_nopour(q) for q in (a, b)):
            warnings.append(f"дорожка {net} внутри зоны {zname} режет медь: {a}-{b}")

# ---- 5. остров -------------------------------------------------------------------------------------------------------
ISLAND = set(getattr(g, "ISLAND", set()))
isl_pts = [(p.x, p.y, p.r) for p in pads if p.net in ISLAND]
isl_segs = [(a, b, w) for net, layer, w, a, b in segs if net in ISLAND]
for p in pads:
    if p.net in ISLAND or not p.net:
        continue
    for x, y, r in isl_pts:
        d = math.hypot(p.x - x, p.y - y) - p.r - r
        if d < ISO:
            problems.append(f"остров: {d:.2f} < {ISO} между {p} и площадкой острова ({x},{y})")
    for a, b, w in isl_segs:
        d = seg_pt_dist(a, b, (p.x, p.y)) - p.r - w / 2
        if d < ISO:
            problems.append(f"остров: {d:.2f} < {ISO} между {p} и дорожкой острова {a}-{b}")
for net, layer, w, a, b in segs:
    if net in ISLAND:
        continue
    for x, y, r in isl_pts:
        d = seg_pt_dist(a, b, (x, y)) - r - w / 2
        if d < ISO:
            problems.append(f"остров: {d:.2f} < {ISO} между дорожкой {net} {a}-{b} и площадкой острова ({x},{y})")
    for a2, b2, w2 in isl_segs:
        d = seg_seg_dist(a, b, a2, b2) - (w + w2) / 2
        if d < ISO:
            problems.append(f"остров: {d:.2f} < {ISO} между дорожкой {net} {a}-{b} и дорожкой острова {a2}-{b2}")
for zname, znet, zlayer, poly in ZONES:
    for x, y, r in isl_pts:
        d = copper_dist((x, y), poly) - r
        if d < ISO:
            problems.append(f"остров: {d:.2f} < {ISO} между зоной {zname} и площадкой острова ({x},{y})")
    for a, b, w in isl_segs:
        d = min(copper_dist(a, poly), copper_dist(b, poly)) - w / 2
        if d < ISO:
            problems.append(f"остров: {d:.2f} < {ISO} между зоной {zname} и дорожкой острова {a}-{b}")

# ---- 6. технологические нормы Резонита (базовый уровень, фольга 18 мкм; rezonit.ru → «Технологические возможности») ----
REZ = dict(track=0.125, gap=0.125, zone_gap=0.2, pth_min=0.3, annular=0.2, npth_min=0.5, to_npth=0.2,
           hole_to_hole=0.2, to_edge=0.25, silk_line=0.15, silk_text=1.0)
for ref, fpname, value, x0, y0, nets in g.PLACE:
    for num, kind, shape, x, y, sx, sy, drill, ang in g.FPS[fpname].pads:
        if kind == "thru_hole":
            if drill < REZ["pth_min"]:
                problems.append(f"Резонит: отверстие {drill} < {REZ['pth_min']}: {ref}.{num}")
            if (min(sx, sy) - drill) / 2 < REZ["annular"] - 1e-6:
                problems.append(f"Резонит: поясок {(min(sx, sy) - drill) / 2:.2f} < {REZ['annular']}: {ref}.{num}")
        if kind == "np_thru_hole" and min(drill) < REZ["npth_min"]:
            problems.append(f"Резонит: неметаллизированное отверстие {drill} < {REZ['npth_min']}: {ref}")
for net, layer, w, a, b in segs:
    if w < REZ["track"]:
        problems.append(f"Резонит: проводник {w} < {REZ['track']}: {net} {a}-{b}")
# медь (площадки, дорожки) до неметаллизированных отверстий ≥ 0,2; отверстие до отверстия ≥ 0,2
npth = [p for p in pads if p.kind == "np_thru_hole"]
for h in npth:
    for p in pads:
        if p is h or p.kind == "np_thru_hole":
            continue
        d = math.hypot(p.x - h.x, p.y - h.y) - p.r - h.r
        if d < REZ["to_npth"]:
            problems.append(f"Резонит: медь до NPTH {d:.2f} < {REZ['to_npth']}: {p} — {h}")
    for net, layer, w, a, b in segs:
        d = seg_pt_dist(a, b, (h.x, h.y)) - w / 2 - h.r
        if d < REZ["to_npth"]:
            problems.append(f"Резонит: дорожка до NPTH {d:.2f} < {REZ['to_npth']}: {net} {a}-{b} — {h}")
drills = []
for ref, fpname, value, x0, y0, nets in g.PLACE:
    for num, kind, shape, x, y, sx, sy, drill, ang in g.FPS[fpname].pads:
        if kind == "smd":
            continue
        dr = max(drill) / 2 if isinstance(drill, tuple) else drill / 2
        drills.append((f"{ref}.{num or 'NPTH'}", x0 + x, y0 + y, dr))
for i, (hx, hy) in enumerate(g.HOLES):
    drills.append((f"H{i + 1}", hx, hy, 1.6))
for i, (net, vx, vy) in enumerate(getattr(g, "vias", [])):
    drills.append((f"via{i}", vx, vy, g.VIA_DRILL / 2))
for i, (n1, x1, y1, r1) in enumerate(drills):
    for n2, x2, y2, r2 in drills[i + 1:]:
        d = math.hypot(x1 - x2, y1 - y2) - r1 - r2
        if d < REZ["hole_to_hole"]:
            problems.append(f"Резонит: между краями отверстий {d:.2f} < {REZ['hole_to_hole']}: {n1} — {n2}")
# шелкография: линия ≥ 0,15, текст ≥ 1,0
silk_items = []
for ref, fpname, value, x0, y0, nets in g.PLACE:
    silk_items += [(ref, s) for s in g.FPS[fpname].gr if '"F.SilkS"' in s]
for ref, sgr in silk_items:
    m = re.search(r"\(size ([\d.]+) ([\d.]+)\) \(thickness ([\d.]+)\)", sgr)
    if m and (float(m.group(1)) < REZ["silk_text"] or float(m.group(3)) < REZ["silk_line"]):
        problems.append(f"Резонит: шелкография текст {m.group(1)}/{m.group(3)} у {ref}")
    m = re.search(r"\(stroke \(width ([\d.]+)\)", sgr)
    if m and float(m.group(1)) < REZ["silk_line"] - 1e-6 and "fp_text" not in sgr:
        problems.append(f"Резонит: линия шелкографии {m.group(1)} < {REZ['silk_line']} у {ref}")
for sgr in g.gr_items():
    if sgr.lstrip().startswith("(gr_") and '"F.SilkS"' in sgr:
        m = re.search(r"\(size ([\d.]+) ([\d.]+)\) \(thickness ([\d.]+)\)", sgr)
        if m and (float(m.group(1)) < REZ["silk_text"] or float(m.group(3)) < REZ["silk_line"]):
            problems.append(f"Резонит: надпись на плате {m.group(1)}/{m.group(3)}: {sgr[:60]}")
        m = re.search(r"\(stroke \(width ([\d.]+)\)", sgr)
        if m and float(m.group(1)) < REZ["silk_line"] - 1e-6:
            problems.append(f"Резонит: линия шелкографии {m.group(1)}: {sgr[:60]}")
# ссылки Reference на шелкографии — размер 1,0 / 0,15 задан в FP.sexpr

# ---- отчёт и превью ---------------------------------------------------------------------------------------------------
print(f"площадок {len(pads)}, сегментов {len(segs)}, зон {len(ZONES)}")
for w in warnings:
    print("  предупреждение:", w)
for p in problems:
    print("  ПРОБЛЕМА:", p)
print(f"проблем: {len(problems)}, предупреждений: {len(warnings)}")

try:
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle, Circle, Polygon
    fig, ax = plt.subplots(figsize=(15, 11.6))
    ax.add_patch(Rectangle((0, 0), g.BOARD_W, g.BOARD_H, fill=False, lw=1.5, ec="k"))
    for zname, znet, zlayer, poly in ZONES:
        ax.add_patch(Polygon(poly, closed=True, fill=True, alpha=0.12, fc="red" if zlayer == "F.Cu" else "blue", ec="none"))
    for poly in NOPOUR:
        ax.add_patch(Polygon(poly, closed=True, fill=True, fc="white", alpha=0.9, ls="--", ec="purple"))
    for ref, x1, y1, x2, y2 in CY:
        ax.add_patch(Rectangle((x1, y1), x2 - x1, y2 - y1, fill=False, lw=0.4, ec="gray"))
    for net, layer, w, a, b in segs:
        ax.plot([a[0], b[0]], [a[1], b[1]], color="red" if layer == "F.Cu" else "blue", lw=w * 2.2, alpha=0.7, solid_capstyle="round")
    for p in pads:
        ax.add_patch(Circle((p.x, p.y), p.r, fc="none" if p.kind == "np_thru_hole" else "gold", ec="k", lw=0.5))
    for ref, fpname, value, x0, y0, nets in g.PLACE:
        ax.text(x0, y0, ref, ha="center", va="center", fontsize=8, color="darkgreen", weight="bold")
    ax.set_xlim(-2, g.BOARD_W + 2); ax.set_ylim(g.BOARD_H + 2, -2); ax.set_aspect("equal"); ax.set_title(f"{CODE} — F.Cu красный, B.Cu синий, зоны полупрозрачно")
    out = ROOT / "boards" / CODE / f"{CODE}_preview.png"
    plt.savefig(out, dpi=110, bbox_inches="tight"); print("превью:", out)
except Exception as e:  # noqa
    print("превью не построено:", e)

sys.exit(1 if problems else 0)

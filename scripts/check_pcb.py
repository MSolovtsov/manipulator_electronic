#!/usr/bin/env python3
"""Проверка платы, собранной gen_PS_pcb.py (до DRC в KiCad): геометрия по данным генератора.

  1. связность: все площадки одной цепи соединены дорожками или зоной своей цепи (на своём слое);
  2. зазоры медь–медь между разными цепями (площадки, дорожки, по слоям) ≥ CLR;
  3. пересечения courtyard'ов; медь до края платы ≥ 0,5 мм; всё внутри контура;
  4. дорожки чужих цепей внутри силовой зоны +24V (режут медь) — предупреждение;
  5. гальванический остров: расстояние от меди острова до любой меди силовой стороны ≥ 2 мм;
  6. нормы Резонита (базовый уровень): отверстия ≥ 0,3 / NPTH ≥ 0,5, поясок ≥ 0,2, медь до NPTH ≥ 0,2,
     отверстие–отверстие ≥ 0,2, шелкография: линия ≥ 0,15, текст ≥ 1,0.

Технологические проверки сверх DRC (нормы — pcb_common.DFM; САПР их не контролирует):
  7. углы изломов дорожек: острее DFM["min_angle"] — ошибка (кислотная ловушка), круче 45° — предупреждение;
  8. крепёж: вокруг винта не более DFM["hole_nets"] цепи и медь не ближе DFM["hole_to_copper"];
  9. шелкография: наложение надписи на контактную площадку — ошибка (завод срежет надпись),
     зазор меньше DFM["silk_to_pad"] и наложение на переход — предупреждение.
 10. компоновка: конструктивно привязанные компоненты (FIXED) на своих местах, функциональные узлы
     (UNITS) собраны и не перемешаны, каналы трасс (CHANNELS) свободны, таблица длин связей (HPWL);
 11. разводка: переходов на цепь и изломов на дорожку не больше нормы — иначе виновата расстановка;
 12. высота компонентов (MAX_H) и доступ паяльником между низким и высоким корпусом.

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

# ---- 7. геометрия меди: углы изломов (DFM: только 45°; острый угол — кислотная ловушка при травлении) ----
DFM = getattr(g, "DFM", {})
MIN_ANGLE = DFM.get("min_angle", 90.0)
not45 = []
for net, layer, w, pts in g.tracks:
    for a, b, c in zip(pts, pts[1:], pts[2:]):
        v1 = (b[0] - a[0], b[1] - a[1]); v2 = (c[0] - b[0], c[1] - b[1])
        l1 = math.hypot(*v1); l2 = math.hypot(*v2)
        if l1 < 1e-9 or l2 < 1e-9:
            continue
        cosv = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (l1 * l2)))
        inner = 180.0 - math.degrees(math.acos(cosv))          # угол между звеньями дорожки
        if inner < MIN_ANGLE - 0.1:
            problems.append(f"угол {inner:.0f} град < {MIN_ANGLE:.0f} (кислотная ловушка): {net} в точке {b}")
        elif inner < 134.9:
            not45.append((net, b, inner))
if not45:
    ex = "; ".join(f"{n} {b} {a:.0f} град" for n, b, a in not45[:5])
    warnings.append(f"изломов круче 45 град: {len(not45)} — скосить chamfer_tracks() [{ex}]")

# ---- 8. крепёж: вокруг винта не более одной цепи, медь не ближе нормы DFM ----------------------------------
H2C = DFM.get("hole_to_copper", 1.0)
HOLE_NETS = DFM.get("hole_nets", 1)
for i, (hx, hy) in enumerate(g.HOLES):
    near = {}
    for pd in pads:
        if pd.kind == "np_thru_hole" or not pd.net:
            continue
        d = math.hypot(pd.x - hx, pd.y - hy) - pd.r - 1.6
        if d < H2C:
            near.setdefault(pd.net, []).append((str(pd), d))
    for net, layer, w, a, b in segs:
        d = seg_pt_dist(a, b, (hx, hy)) - w / 2 - 1.6
        if d < H2C:
            near.setdefault(net, []).append((f"дорожка {a}-{b}", d))
    for zname, znet, zlayer, poly in ZONES:
        d = copper_dist((hx, hy), poly) - 1.6
        if d < H2C:
            near.setdefault(znet, []).append((f"зона {zname} ({zlayer})", d))
    if not near:
        continue
    det = "; ".join(f"{n}: " + ", ".join(f"{w} {dd:.2f}" for w, dd in sorted(v, key=lambda t: t[1])[:2]) for n, v in sorted(near.items()))
    if len(near) > HOLE_NETS:
        problems.append(f"крепёж H{i + 1} ({hx},{hy}): вокруг винта {len(near)} цепи ({', '.join(sorted(near))}) — "
                        f"металлическая стойка их соединит [{det}]")
    else:
        problems.append(f"крепёж H{i + 1} ({hx},{hy}): медь ближе {H2C} мм [{det}]")

# ---- 9. сборка: шелкография не наезжает на контактные площадки ----------------------------------------------
# Ширина знака штрихового шрифта KiCad — примерно 0,62 высоты; оценка сверху, спорные случаи смотреть в KiCad.
SILK_PAD = DFM.get("silk_to_pad", 0.2)
GLYPH_W, GLYPH_H = 0.62, 0.75
silk_boxes = []                       # (подпись, x, y, полуширина, полувысота)
for t, x, y, sz in g.TEXTS:
    sz = max(sz, 1.0)
    silk_boxes.append((f'надпись "{t}"', x, y, len(t) * sz * GLYPH_W / 2, sz * GLYPH_H))
for ref, fpname, value, x0, y0, nets in g.PLACE:
    fp = g.FPS[fpname]
    silk_boxes.append((f"обозначение {ref}", x0 + fp.ref_at[0], y0 + fp.ref_at[1], len(ref) * 1.0 * GLYPH_W / 2, 1.0 * GLYPH_H))
    for sgr in fp.gr:
        if '"F.SilkS"' not in sgr or "(hide yes)" in sgr:
            continue
        m = re.search(r'fp_text \w+ "([^"]*)" \(at ([-\d.]+) ([-\d.]+)', sgr)
        if not m:
            continue
        hm = re.search(r"\(size ([\d.]+)", sgr)
        h = float(hm.group(1)) if hm else 1.0
        txt = m.group(1)
        silk_boxes.append((f'{ref}: "{txt}"', x0 + float(m.group(2)), y0 + float(m.group(3)),
                           len(txt) * h * GLYPH_W / 2, h * GLYPH_H))
silk_bad, silk_near = [], []
for label, sx, sy, hw, hh in silk_boxes:
    for pd in pads:
        if pd.kind == "np_thru_hole":
            continue
        d = max(abs(sx - pd.x) - (hw + pd.r), abs(sy - pd.y) - (hh + pd.r))
        if d >= SILK_PAD:
            continue
        if pd.kind == "via" or d >= 0:         # переход закрыт маской; зазор меньше нормы — ещё не наложение
            silk_near.append((label, str(pd), d))
        else:
            silk_bad.append((label, str(pd), d))
for label, pdn, d in silk_bad[:20]:
    problems.append(f"шелкография поверх площадки ({-d:.2f} мм перекрытия): {label} — {pdn}; завод срежет надпись")
for label, pdn, d in silk_near[:20]:
    how = f"перекрывает на {-d:.2f} мм" if d < 0 else f"в {d:.2f} мм (норма {SILK_PAD})"
    warnings.append(f"шелкография {how}: {label} — {pdn}")
if len(silk_bad) > 20 or len(silk_near) > 20:
    warnings.append(f"шелкография: всего наложений {len(silk_bad)}, близких {len(silk_near)} (показаны первые 20)")

# ---- 10. компоновка: конструктивная привязка, функциональные узлы, длины связей --------------------------
# Качество платы задаётся расстановкой: узел ставится целиком, узлы — в порядке по числу связей.
infos = []
for ref, (fx, fy, src) in sorted(getattr(g, "FIXED", {}).items()):
    cur = [(x, y) for r, fp, v, x, y, n in g.PLACE if r == ref]
    if not cur:
        problems.append(f"компоновка: {ref} объявлен конструктивно привязанным, но его нет в PLACE")
    elif abs(cur[0][0] - fx) > 1e-6 or abs(cur[0][1] - fy) > 1e-6:
        problems.append(f"компоновка: {ref} сдвинут с конструктивного места ({fx},{fy}) на {cur[0]} — источник: {src}")

UNITS = getattr(g, "UNITS", {})
POS = {r: (x, y) for r, fp, v, x, y, n in g.PLACE}
if not UNITS:
    warnings.append("компоновка: UNITS не заполнены — функциональные узлы не объявлены, группировку проверить нечем")
else:
    def u_refs(v):
        return list(v["refs"]) if isinstance(v, dict) else list(v)

    def u_radius(v):
        return v.get("radius", DFM.get("unit_radius", 25.0)) if isinstance(v, dict) else DFM.get("unit_radius", 25.0)

    covered = {r for v in UNITS.values() for r in u_refs(v)}
    lost = sorted(set(POS) - covered)
    dup = sorted(r for r in covered if sum(r in u_refs(v) for v in UNITS.values()) > 1)
    if lost:
        warnings.append(f"компоновка: вне функциональных узлов {len(lost)} компонентов: {', '.join(lost)}")
    if dup:
        problems.append(f"компоновка: компонент числится в двух узлах: {', '.join(dup)}")
    boxes = {}
    for name, v in UNITS.items():
        refs, rad = u_refs(v), u_radius(v)
        pts = [POS[r] for r in refs if r in POS]
        if not pts:
            continue
        xs = [q[0] for q in pts]; ys = [q[1] for q in pts]
        cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
        boxes[name] = (min(xs), min(ys), max(xs), max(ys))
        far = [(r, math.hypot(POS[r][0] - cx, POS[r][1] - cy)) for r in refs if r in POS]
        far = [(r, d) for r, d in far if d > rad]
        if far:
            det = ", ".join(f"{r} {d:.0f} мм" for r, d in sorted(far, key=lambda t: -t[1])[:3])
            warnings.append(f"компоновка: узел «{name}» растащен по плате — от центра дальше {rad:.0f} мм: {det}")
    names = sorted(boxes)
    for i, n1 in enumerate(names):
        a = boxes[n1]
        for n2 in names[i + 1:]:
            b = boxes[n2]
            if a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]:
                warnings.append(f"компоновка: прямоугольники узлов «{n1}» и «{n2}» перекрываются — узлы перемешаны")

for x1, y1, x2, y2, what in getattr(g, "CHANNELS", []):
    inside = [r for r, (x, y) in POS.items() if x1 <= x <= x2 and y1 <= y <= y2]
    if inside:
        problems.append(f"компоновка: в канале трасс «{what}» стоят компоненты: {', '.join(sorted(inside))}")

netpads = {}
for pd in pads:
    if pd.net:
        netpads.setdefault(pd.net, []).append((pd.x, pd.y))
hp = []
for n, ps in netpads.items():
    if len(ps) < 2:
        continue
    xs = [q[0] for q in ps]; ys = [q[1] for q in ps]
    hp.append(((max(xs) - min(xs)) + (max(ys) - min(ys)), n, len(ps)))
hp.sort(reverse=True)
if hp:
    tot = sum(h for h, n, k in hp)
    infos.append(f"длины связей (HPWL): всего {tot:.0f} мм на {len(hp)} цепей, в среднем {tot / len(hp):.0f} мм; "
                 "длиннее всех — " + ", ".join(f"{n} {h:.0f} мм" for h, n, k in hp[:4]))

# ---- 11. разводка: переходы и изломы как признак неудачной компоновки ------------------------------------
VIA_N = DFM.get("via_per_net", 4)
BENDS_N = DFM.get("bends_max", 3)
pervia = {}
for net, vx, vy in getattr(g, "vias", []):
    pervia[net] = pervia.get(net, 0) + 1
heavy = sorted(((k, n) for n, k in pervia.items() if k > VIA_N), reverse=True)
if heavy:
    warnings.append(f"разводка: цепей с числом переходов больше {VIA_N}: {len(heavy)} — "
                    + ", ".join(f"{n} ({k})" for k, n in heavy[:6]) + "; это признак компоновки, а не трассировки")
def corners(pts):
    """Число поворотов в пересчёте на прямые углы: скос 45° + 45° считается одним поворотом,
    поэтому chamfer_tracks() число поворотов не увеличивает."""
    t = 0.0
    for a, b, c in zip(pts, pts[1:], pts[2:]):
        v1 = (b[0] - a[0], b[1] - a[1]); v2 = (c[0] - b[0], c[1] - b[1])
        l1 = math.hypot(*v1); l2 = math.hypot(*v2)
        if l1 < 1e-9 or l2 < 1e-9:
            continue
        cs = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (l1 * l2)))
        t += math.degrees(math.acos(cs))
    return t / 90.0


long_tracks = [(round(corners(pts), 1), net) for net, layer, w, pts in g.tracks if corners(pts) > BENDS_N]
if long_tracks:
    long_tracks.sort(reverse=True)
    warnings.append(f"разводка: дорожек с числом поворотов больше {BENDS_N}: {len(long_tracks)} — "
                    + ", ".join(f"{n} ({k:g})" for k, n in long_tracks[:6])
                    + "; трасса обходит узлы — переставить компоненты")
total_len = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for net, layer, w, pts in g.tracks for a, b in zip(pts, pts[1:]))
infos.append(f"разводка: меди {total_len:.0f} мм, переходов {len(getattr(g, 'vias', []))}, "
             f"стратегия слоёв «{getattr(g, 'ROUTER_STRATEGY', 'hv')}»")

# ---- 12. высота компонентов и доступ при ручной сборке ---------------------------------------------------
MAX_H = getattr(g, "MAX_H", None)
H = {}
for ref, fpname, value, x0, y0, nets in g.PLACE:
    H[ref] = getattr(g.FPS[fpname], "height", None)
unknown = sorted(r for r, h in H.items() if h is None)
if unknown:
    infos.append(f"высота корпуса не задана у {len(unknown)} компонентов (требует уточнения): "
                 + ", ".join(unknown[:10]) + ("…" if len(unknown) > 10 else ""))
if MAX_H is None:
    infos.append("ограничение по высоте (MAX_H) не задано — требует уточнения по чертежу корпуса")
else:
    for r, h in sorted(H.items()):
        if h is not None and h > MAX_H:
            problems.append(f"высота: {r} — {h} мм над платой при ограничении {MAX_H} мм")
known_h = {r: h for r, h in H.items() if h is not None}
if known_h:
    rmax = max(known_h, key=known_h.get)
    infos.append(f"высота: максимальная над платой {known_h[rmax]} мм ({rmax}) — передать в mechanics"
                 + (f"; у {len(unknown)} компонентов высота не задана" if unknown else ""))
# компоненты под модулем на гнёздах (например, ESP32 на MC): не выше изолятора гнёзд
MODULE = getattr(g, "MODULE", None)
MODULE_REFS = getattr(g, "MODULE_REFS", ("XS1", "XS2"))
if MODULE is not None:
    sock_h = [H.get(r) for r in MODULE_REFS if r in H]
    sock_h = min((h for h in sock_h if h is not None), default=None)
    under = [r for r, (x, y) in POS.items()
             if r not in MODULE_REFS and MODULE[0] < x < MODULE[2] and MODULE[1] < y < MODULE[3]]
    if sock_h is None:
        infos.append("модуль на гнёздах: высота гнёзд не задана — проверка компонентов под модулем пропущена")
    else:
        for r in sorted(under):
            h = H.get(r)
            if h is None:
                warnings.append(f"модуль: {r} стоит под модулем, высота не задана — должна быть ≤ {sock_h} мм (гнёзда)")
            elif h > sock_h:
                problems.append(f"модуль: {r} — {h} мм под модулем выше гнёзд {sock_h} мм")
        infos.append(f"модуль на гнёздах: под контуром {len(under)} компонентов, предел {sock_h} мм")
TALL, LOW, ACC = DFM.get("tall", 8.0), DFM.get("low", 3.0), DFM.get("solder_access", 3.0)
for r1, h1 in sorted(H.items()):
    if h1 is None or h1 < TALL:
        continue
    for r2, h2 in sorted(H.items()):
        if h2 is None or h2 > LOW or r1 == r2:
            continue
        d = math.hypot(POS[r1][0] - POS[r2][0], POS[r1][1] - POS[r2][1])
        if d < ACC:
            warnings.append(f"сборка: {r2} ({h2} мм) в {d:.1f} мм от высокого {r1} ({h1} мм) — "
                            f"паяльником не подлезть, феном поплавит соседа")

# ---- отчёт и превью ---------------------------------------------------------------------------------------------------
print(f"площадок {len(pads)}, сегментов {len(segs)}, зон {len(ZONES)}")
for t in infos:
    print("  сведения:", t)
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

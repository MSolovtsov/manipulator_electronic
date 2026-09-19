#!/usr/bin/env python3
"""Общая часть генераторов печатных плат (gen_<КОД>_pcb.py): формат KiCad 9 (20241229), класс FP и библиотека
посадочных мест, дорожки/переходы/зоны, контур, крепёж, надписи, сборка файла.

Генератор задаёт pc.PROJECT, pc.ROOT_UUID, pc.BOARD_W/H, pc.TITLE, pc.REV, вызывает set_nets(), set_place(), рисует
seg()/via(), заполняет ZONES, HOLES, TEXTS, ISO_RECTS и вызывает write(). Проверка — scripts/check_pcb.py <КОД>.
Правила — electronics/CLAUDE.md, «Генерация платы».
"""
import math
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_FP = ROOT / "lib" / "footprints" / "manipulator.pretty"

PCB_VER = "20241229"
PCB_GEN_VER = "9.0"
FP_VER = "20241229"
LIB = "manipulator"
PROJECT = "PS"                                                # переопределяется генератором
ROOT_UUID = "9d3a5f2c-4b1e-4f0a-8c6d-2e7b1a9f0c11"           # uuid корневого листа схемы (gen_<КОД>_sch.py)
SYM_NS = uuid.UUID("6f1c2b3a-0d4e-4f5a-9b6c-7d8e9f0a1b2c")   # то же пространство имён, что в sch_common.py
FP_NS = uuid.UUID("2b7e1d0c-9a8f-4c6e-8d5b-3a4f5e6d7c8b")

BOARD_W, BOARD_H = 120.0, 100.0
OBX, OBY = 50.0, 50.0        # смещение платы на листе KiCad
TITLE, REV, DATE = "", "", "2026-09-17"
COMPANY = "МГТУ им. Н.Э. Баумана, группа СМ7-21М"

# ---- правила -------------------------------------------------------------------------------------
CLR = 0.5                    # зазор медь–медь (мм)
W_SIG, W_5P, W_24 = 0.8, 2.0, 6.0
VIA_D, VIA_DRILL = 1.2, 0.6  # переходное отверстие (Резонит: отверстие ≥ 0,3, поясок ≥ 0,2)
LAYERS_THT = '(layers "*.Cu" "*.Mask")'
F, B = "F.Cu", "B.Cu"


def r3(v):
    return round(v + 0.0, 3)


def U(*key):
    return str(uuid.uuid5(FP_NS, "|".join(str(k) for k in key)))


def sym_uuid(ref):
    return str(uuid.uuid5(SYM_NS, f"{PROJECT}:{ref}"))


# ---- цепи ------------------------------------------------------------------------------------------
NETS, NET = [], {}


def set_nets(names):
    """Список цепей платы; имена безымянных — как их даёт KiCad 10 (Net-(REF-имя вывода))."""
    NETS.clear(); NETS.extend(names); NET.clear(); NET.update({n: i for i, n in enumerate(NETS)})


# ---- примитивы footprint (локальные координаты, мм; y вниз) -----------------------------------------
def rot(px, py, ang):
    """Поворот локальной точки на ang градусов (визуально против часовой стрелки при y вниз)."""
    a = math.radians(ang)
    return (px * math.cos(a) + py * math.sin(a), -px * math.sin(a) + py * math.cos(a))


class FP:
    def __init__(self, name, descr, tags="", smd=False):
        self.name, self.descr, self.tags, self.is_smd = name, descr, tags, smd
        self.pads = []      # (num, kind, shape, x, y, sx, sy, drill, rotdeg)
        self.gr = []        # s-выражения графики
        self.ref_at = (0, -4.0)
        self.val_at = (0, 4.0)

    # --- контактные площадки
    def tht(self, num, x, y, drill, size, shape="circle"):
        self.pads.append((num, "thru_hole", shape, x, y, size, size, drill, 0))

    def tht_oval(self, num, x, y, drill, sx, sy):
        self.pads.append((num, "thru_hole", "oval", x, y, sx, sy, drill, 0))

    def smd(self, num, x, y, sx, sy):
        self.pads.append((num, "smd", "roundrect", x, y, sx, sy, None, 0))

    def npth_slot(self, x, y, w, l, ang):
        self.pads.append(("", "np_thru_hole", "oval", x, y, w, l, (w, l), ang))

    # --- графика
    def line(self, layer, x1, y1, x2, y2, w=0.12):
        self.gr.append(f'(fp_line (start {r3(x1)} {r3(y1)}) (end {r3(x2)} {r3(y2)}) (stroke (width {w}) (type default)) (layer "{layer}") (uuid "{U(self.name, layer, "l", x1, y1, x2, y2)}"))')

    def rect(self, layer, x1, y1, x2, y2, w=0.12):
        self.gr.append(f'(fp_rect (start {r3(x1)} {r3(y1)}) (end {r3(x2)} {r3(y2)}) (stroke (width {w}) (type default)) (fill no) (layer "{layer}") (uuid "{U(self.name, layer, "r", x1, y1, x2, y2)}"))')

    def circle(self, layer, cx, cy, r, w=0.12):
        self.gr.append(f'(fp_circle (center {r3(cx)} {r3(cy)}) (end {r3(cx + r)} {r3(cy)}) (stroke (width {w}) (type default)) (fill no) (layer "{layer}") (uuid "{U(self.name, layer, "c", cx, cy, r)}"))')

    def text(self, layer, t, x, y, size=0.8, ang=0):
        if layer == "F.SilkS":                 # Резонит: высота шрифта маркировки ≥ 1,0 мм, линия ≥ 0,15 мм
            size = max(size, 1.0)
        th = 0.15 if layer == "F.SilkS" else 0.1
        self.gr.append(f'(fp_text user "{t}" (at {r3(x)} {r3(y)} {ang}) (layer "{layer}") (uuid "{U(self.name, layer, "t", t, x, y)}") (effects (font (size {size} {size}) (thickness {th}))))')

    def outline(self, x1, y1, x2, y2, cy_margin=0.5):
        """Контур корпуса: F.Fab (тонко), F.SilkS (снаружи), F.CrtYd (с запасом)."""
        self.rect("F.Fab", x1, y1, x2, y2, 0.1)
        self.rect("F.SilkS", x1 - 0.2, y1 - 0.2, x2 + 0.2, y2 + 0.2, 0.15)   # линия шелкографии ≥ 0,15 (Резонит)
        self.rect("F.CrtYd", x1 - cy_margin, y1 - cy_margin, x2 + cy_margin, y2 + cy_margin, 0.05)

    def bbox(self):
        xs, ys = [], []
        for p in self.pads:
            xs += [p[3] - p[5] / 2, p[3] + p[5] / 2]; ys += [p[4] - p[6] / 2, p[4] + p[6] / 2]
        return min(xs), min(ys), max(xs), max(ys)

    # --- вывод
    def pad_sexpr(self, ref, nets, indent="    "):
        out = []
        for num, kind, shape, x, y, sx, sy, drill, ang in self.pads:
            if kind == "smd":
                layers = '(layers "F.Cu" "F.Paste" "F.Mask")'
                d = ""
            elif kind == "np_thru_hole":
                layers = '(layers "*.Cu" "*.Mask")'
                d = f" (drill {r3(drill[0])})" if shape == "circle" else f" (drill oval {r3(drill[0])} {r3(drill[1])})"
            else:
                layers = LAYERS_THT
                d = f" (drill {r3(drill)})"
            net = ""
            if num and nets and num in nets:
                net = f' (net {NET[nets[num]]} "{nets[num]}")'
            rr = " (roundrect_rratio 0.2)" if shape == "roundrect" else ""
            out.append(f'{indent}(pad "{num}" {kind} {shape} (at {r3(x)} {r3(y)} {ang}) (size {r3(sx)} {r3(sy)}){d} {layers}{rr}'
                       f'{net} (uuid "{U(self.name, ref, "pad", num, x, y)}"))')
        return "\n".join(out)

    def sexpr(self, ref, value, x, y, nets=None, sheet=True):
        """Footprint на плате (ref заполнен) или в библиотеке (ref='REF**')."""
        attr = "smd" if self.is_smd else "through_hole"
        props = [
            f'    (property "Reference" "{ref}" (at {r3(self.ref_at[0])} {r3(self.ref_at[1])} 0) (layer "F.SilkS") (uuid "{U(self.name, ref, "Reference")}") (effects (font (size 1 1) (thickness 0.15))))',
            f'    (property "Value" "{value}" (at {r3(self.val_at[0])} {r3(self.val_at[1])} 0) (layer "F.Fab") (uuid "{U(self.name, ref, "Value")}") (effects (font (size 1 1) (thickness 0.15))))',
            f'    (property "Footprint" "{LIB}:{self.name}" (at 0 0 0) (layer "F.Fab") (hide yes) (uuid "{U(self.name, ref, "Footprint")}") (effects (font (size 1.27 1.27) (thickness 0.15))))',
            f'    (property "Datasheet" "" (at 0 0 0) (layer "F.Fab") (hide yes) (uuid "{U(self.name, ref, "Datasheet")}") (effects (font (size 1.27 1.27) (thickness 0.15))))',
            f'    (property "Description" "{self.descr}" (at 0 0 0) (layer "F.Fab") (hide yes) (uuid "{U(self.name, ref, "Description")}") (effects (font (size 1.27 1.27) (thickness 0.15))))',
        ]
        # путь символа корневого листа в KiCad 10 — только uuid символа, без uuid листа
        path = f'    (path "/{sym_uuid(ref)}")\n    (sheetname "/")\n    (sheetfile "{PROJECT}.kicad_sch")\n' if sheet else ""
        at = f" (at {r3(x + OBX)} {r3(y + OBY)})" if sheet else ""
        gr = "\n".join("    " + g for g in self.gr)
        return (f'  (footprint "{LIB}:{self.name}" (layer "F.Cu") (uuid "{U(self.name, ref, "fp")}"){at}\n'
                f'    (descr "{self.descr}")\n    (tags "{self.tags}")\n' + "\n".join(props) + "\n" + path +
                f'    (attr {attr})\n{gr}\n{self.pad_sexpr(ref, nets)}\n    (embedded_fonts no)\n  )')

    def lib_file(self):
        gr = "\n".join("  " + g for g in self.gr)
        attr = "smd" if self.is_smd else "through_hole"
        return (f'(footprint "{self.name}" (version {FP_VER}) (generator "pcbnew") (generator_version "{PCB_GEN_VER}") (layer "F.Cu")\n'
                f'  (descr "{self.descr}")\n  (tags "{self.tags}")\n'
                f'  (property "Reference" "REF**" (at {r3(self.ref_at[0])} {r3(self.ref_at[1])} 0) (layer "F.SilkS") (uuid "{U(self.name, "lib", "Reference")}") (effects (font (size 1 1) (thickness 0.15))))\n'
                f'  (property "Value" "{self.name}" (at {r3(self.val_at[0])} {r3(self.val_at[1])} 0) (layer "F.Fab") (uuid "{U(self.name, "lib", "Value")}") (effects (font (size 1 1) (thickness 0.15))))\n'
                f'  (property "Footprint" "" (at 0 0 0) (layer "F.Fab") (hide yes) (uuid "{U(self.name, "lib", "Footprint")}") (effects (font (size 1.27 1.27) (thickness 0.15))))\n'
                f'  (property "Datasheet" "" (at 0 0 0) (layer "F.Fab") (hide yes) (uuid "{U(self.name, "lib", "Datasheet")}") (effects (font (size 1.27 1.27) (thickness 0.15))))\n'
                f'  (property "Description" "{self.descr}" (at 0 0 0) (layer "F.Fab") (hide yes) (uuid "{U(self.name, "lib", "Description")}") (effects (font (size 1.27 1.27) (thickness 0.15))))\n'
                f'  (attr {attr})\n{gr}\n' + self.pad_sexpr("lib", None, "  ") + f'\n  (embedded_fonts no)\n)\n')


# ---- библиотека посадочных мест ----------------------------------------------------------------------
FPS = {}


def tb_dg301(vertical=False):
    """Degson DG301-5.0 2P: шаг 5,0, вывод ⌀1,0 → отверстие 1,3; корпус 10,0 × 7,6 (+0,6 выступ), ряд выводов
    в 4,5 мм от стороны ввода провода. vertical — выводы вдоль y, ввод провода в +x (правый край платы)."""
    name = "TB_DG301-5.0_2P" + ("_V" if vertical else "")
    f = FP(name, "Клеммник винтовой Degson DG301-5.0-02P-12, шаг 5,0 мм, 15 А (чертёж 200102539)", "terminal block degson")
    pts = [(-2.5, 0.0, "1"), (2.5, 0.0, "2")]
    body = (-5.0, -4.5, 5.0, 3.1)
    if vertical:
        # поворот на -90°: (x, y) -> (-y, x): ввод (−y) → +x, вывод 1 сверху
        pts = [(-y, x, n) for x, y, n in pts]
        body = (-body[3], body[0], -body[1], body[2])
    for x, y, n in pts:
        f.tht(n, x, y, 1.3, 2.4)
    f.outline(*body, cy_margin=0.25)        # клеммники стыкуются в ряд, шаг ряда 10,5 мм
    if vertical:
        f.text("F.SilkS", "+", body[0] - 1.2, pts[0][1], 1.0)
        f.ref_at = (0, body[1] - 1.5); f.val_at = (0, body[3] + 1.5)
    else:
        f.text("F.SilkS", "+", pts[0][0], body[3] + 1.2, 1.0)
        f.ref_at = (body[2] + 3.0, 0); f.val_at = (0, body[3] + 1.5)
    FPS[name] = f


def _orient(pts, body, orient):
    """Поворот ряда выводов и корпуса: "" — выводы вдоль x, замок/ввод к +y; "R" — выводы вдоль y, ввод к +x
    (правый край платы); "L" — выводы вдоль y, ввод к −x (левый край). Вывод 1 — сверху при R/L."""
    if orient == "R":
        pts = [(-y, x, n) for x, y, n in pts]; body = (-body[3], body[0], -body[1], body[2])
    elif orient == "L":
        pts = [(y, x, n) for x, y, n in pts]; body = (body[1], body[0], body[3], body[2])
    return pts, body


def jst_xh(n, orient=""):
    """JST XH B{n}B-XH-A: шаг 2,5; отверстие 1,0; корпус (n−1)·2,5 + 4,9 × 5,75; ряд выводов в 2,35 мм от задней стенки.
    Размеры — по библиотеке KiCad; сверить с чертежом JST eXH перед заказом."""
    name = f"JST_XH_B{n}B-XH-A" + (f"_{orient}" if orient else "")
    f = FP(name, f"Вилка JST B{n}B-XH-A, {n} конт., шаг 2,5 мм, 3 А (размеры KiCad — проверить по JST)", "connector jst xh")
    x0 = -(n - 1) * 2.5 / 2
    pts = [(x0 + i * 2.5, 0.0, str(i + 1)) for i in range(n)]
    body = (x0 - 2.45, -2.35, x0 + (n - 1) * 2.5 + 2.45, 3.4)
    pts, body = _orient(pts, body, orient)
    for i, (x, y, num) in enumerate(pts):
        f.tht(num, x, y, 1.0, 1.8, "circle" if i else "rect")
    f.outline(*body)
    if orient:
        f.text("F.SilkS", "1", pts[0][0], pts[0][1] - 2.4, 0.8)
        f.ref_at = (0, body[1] - 1.5); f.val_at = (0, body[3] + 1.5)
    else:
        f.text("F.SilkS", "1", x0, 4.6, 0.8)
        f.ref_at = (0, -3.6); f.val_at = (0, 4.6)
    FPS[name] = f


def jst_vh(n, vertical=False, orient=None):
    """JST VH B{n}P-VH: шаг 3,96; отверстие 1,7; корпус (n−1)·3,96 + 6,0 × 7,0 (по KiCad; сверить с чертежом JST eVH).
    vertical=True — то же, что orient="R" (имя _V, плата PS)."""
    if orient is None:
        orient = "R" if vertical else ""
    name = f"JST_VH_B{n}P-VH" + ("_V" if vertical else (f"_{orient}" if orient else ""))
    f = FP(name, f"Вилка JST B{n}P-VH, {n} конт., шаг 3,96 мм, 10 А (размеры KiCad — проверить по JST)", "connector jst vh")
    x0 = -(n - 1) * 3.96 / 2
    pts = [(x0 + i * 3.96, 0.0, str(i + 1)) for i in range(n)]
    body = (x0 - 3.0, -3.0, x0 + (n - 1) * 3.96 + 3.0, 4.0)
    pts, body = _orient(pts, body, orient)
    vertical = bool(orient)
    for i, (x, y, num) in enumerate(pts):
        f.tht(num, x, y, 1.7, 2.8, "rect" if i == 0 else "circle")
    f.outline(*body)
    if vertical:
        f.text("F.SilkS", "1", body[0] - 1.2, pts[0][1], 0.8)
        f.ref_at = (0, body[1] - 1.5); f.val_at = (0, body[3] + 1.5)
    else:
        f.text("F.SilkS", "1", pts[0][0], body[3] + 1.2, 0.8)
        f.ref_at = (0, body[1] - 1.5); f.val_at = (0, body[3] + 1.5)
    FPS[name] = f


def relay_nrp15():
    """NCR NRP-15 1C (6 отверстий — подходит и 5-выводному варианту). Вид сверху получен зеркалированием
    «PCB layout» datasheet (вид снизу). Номера площадок = выводы символа: 1 A1, 2 A2, 3 COM (две), 4 NO, 5 NC."""
    f = FP("Relay_NRP-15_1C", "Реле NCR NRP-15-C (1C, SPDT 20 А/28 В DC), корпус 27,5 × 32 × 20; вид снизу datasheet зеркалирован", "relay ncr nrp15")
    f.tht("5", 8.65, -13.5, 2.1, 3.5)      # NC
    f.tht("4", 8.65, -5.9, 2.1, 3.5)       # NO
    f.tht("3", -9.15, -3.36, 2.1, 3.5)     # COM
    f.tht("3", 0.0, 11.88, 2.1, 3.5)       # COM (второй вывод 6-выводного варианта)
    f.tht("1", -4.85, 9.34, 1.3, 2.3)      # катушка A1
    f.tht("2", 5.35, 9.34, 1.3, 2.3)       # катушка A2
    f.outline(-13.75, -16.0, 13.75, 16.0)
    for t, x, y in (("NC", 8.65, -16.9), ("NO", 11.5, -5.9), ("COM", -12.0, -0.8), ("A1", -7.6, 9.34), ("A2", 8.2, 9.34)):
        f.text("F.SilkS", t, x, y, 0.8)
    f.ref_at = (0, -17.8); f.val_at = (0, 17.8)
    FPS[f.name] = f


def mornsun_ymd():
    """Mornsun VRA(B)_YMD-10WR3: 25,4 × 25,4 × 11,7, вывод ⌀1,0, сетка 2,54; вид сверху (PCB layout datasheet):
    1 Ctrl, 2 GND, 3 Vin — левый ряд; 6 0V (верх), 5 нет, 4 +Vo (низ) — правый ряд. Отверстие 1,4 (datasheet 1,5)."""
    f = FP("DCDC_Mornsun_YMD_25.4x25.4", "Mornsun VRB2405YMD-10WR3, DIP 25,4 × 25,4, выводы по datasheet 2026.03", "dcdc mornsun ymd")
    f.tht("1", -10.16, -10.16, 1.4, 2.4, "rect")
    f.tht("2", -10.16, -2.54, 1.4, 2.4)
    f.tht("3", -10.16, 2.54, 1.4, 2.4)
    f.tht("4", 10.16, 10.16, 1.4, 2.4)
    f.tht("6", 10.16, -10.16, 1.4, 2.4)
    f.outline(-12.7, -12.7, 12.7, 12.7)
    f.line("F.SilkS", 0, -12.9, 0, 12.9, 0.15)          # граница развязки
    for t, x, y in (("Ctrl", -7.2, -10.16), ("GND", -7.2, -2.54), ("Vin", -7.2, 2.54), ("+Vo", 7.0, 10.16), ("0V", 7.0, -10.16)):
        f.text("F.Fab", t, x, y, 0.8)
    f.ref_at = (0, -14.2); f.val_at = (0, 14.2)
    FPS[f.name] = f


def d_smc():
    """SMC (DO-214AB): площадки 2,9 × 3,0 в ±3,55; вывод 1 — катод (полоса)."""
    f = FP("D_SMC", "Диод SMC (DO-214AB), катод — вывод 1 (полоса)", "diode smc tvs", smd=True)
    f.smd("1", -3.55, 0, 2.9, 3.0)
    f.smd("2", 3.55, 0, 2.9, 3.0)
    f.rect("F.Fab", -3.45, -2.95, 3.45, 2.95, 0.1)
    f.line("F.SilkS", -5.3, -3.2, -5.3, 3.2, 0.3)      # полоса катода
    f.line("F.SilkS", -5.3, -3.2, 5.3, -3.2, 0.15); f.line("F.SilkS", -5.3, 3.2, 5.3, 3.2, 0.15)
    f.rect("F.CrtYd", -5.5, -3.5, 5.5, 3.5, 0.05)
    f.ref_at = (0, -4.5); f.val_at = (0, 4.5)
    FPS[f.name] = f


def d_do41():
    f = FP("D_DO-41_P10.16mm", "Диод DO-41, шаг 10,16; вывод 1 — катод (полоса)", "diode do-41")
    f.tht("1", -5.08, 0, 1.1, 2.2, "rect"); f.tht("2", 5.08, 0, 1.1, 2.2)
    f.rect("F.Fab", -2.6, -1.35, 2.6, 1.35, 0.1)
    f.rect("F.SilkS", -2.8, -1.55, 2.8, 1.55, 0.15)
    f.line("F.SilkS", -2.0, -1.55, -2.0, 1.55, 0.3)
    f.line("F.SilkS", -3.7, 0, -2.8, 0, 0.15); f.line("F.SilkS", 2.8, 0, 3.7, 0, 0.15)
    f.rect("F.CrtYd", -6.4, -1.8, 6.4, 1.8, 0.05)
    f.ref_at = (0, -2.8); f.val_at = (0, 2.8)
    FPS[f.name] = f


def r_axial(vertical=False):
    name = "R_Axial_P10.16mm" + ("_V" if vertical else "")
    f = FP(name, "Резистор 0,25 Вт, выводной, шаг 10,16", "resistor axial")
    pts = [(-5.08, 0, "1"), (5.08, 0, "2")]
    body = (-3.2, -1.2, 3.2, 1.2)
    if vertical:
        pts = [(y, -x, n) for x, y, n in pts]          # +90°: вывод 1 снизу, вывод 2 сверху
        body = (body[1], -body[2], body[3], -body[0])
    for x, y, n in pts:
        f.tht(n, x, y, 0.9, 1.8)
    f.rect("F.Fab", *body, 0.1); f.rect("F.SilkS", body[0] - 0.2, body[1] - 0.2, body[2] + 0.2, body[3] + 0.2, 0.15)
    f.rect("F.CrtYd", min(p[0] for p in pts) - 1.2, min(p[1] for p in pts) - 1.2, max(p[0] for p in pts) + 1.2, max(p[1] for p in pts) + 1.2, 0.05)
    f.ref_at = (2.6, 0) if vertical else (0, -2.5); f.val_at = (-2.6, 0) if vertical else (0, 2.5)
    FPS[name] = f


def cp_radial():
    f = FP("CP_Radial_D8.0mm_P3.50mm", "Конденсатор электролитический ⌀8, шаг 3,5; вывод 1 — «+»", "capacitor electrolytic")
    f.tht("1", -1.75, 0, 1.0, 1.8, "rect"); f.tht("2", 1.75, 0, 1.0, 1.8)
    f.circle("F.Fab", 0, 0, 4.0, 0.1); f.circle("F.SilkS", 0, 0, 4.2, 0.15)
    f.text("F.SilkS", "+", -3.2, -3.4, 1.0)
    f.circle("F.CrtYd", 0, 0, 4.5, 0.05)
    f.ref_at = (0, -5.5); f.val_at = (0, 5.5)
    FPS[f.name] = f


def c_disc():
    f = FP("C_Disc_P5.00mm", "Конденсатор керамический выводной, шаг 5,0", "capacitor ceramic")
    f.tht("1", -2.5, 0, 0.9, 1.8); f.tht("2", 2.5, 0, 0.9, 1.8)
    f.rect("F.Fab", -3.0, -1.25, 3.0, 1.25, 0.1); f.rect("F.SilkS", -3.2, -1.45, 3.2, 1.45, 0.15)
    f.rect("F.CrtYd", -3.7, -1.7, 3.7, 1.7, 0.05)
    f.ref_at = (0, -2.7); f.val_at = (0, 2.7)
    FPS[f.name] = f


def l_toroid():
    f = FP("L_Toroid_D20_P10.16mm", "Дроссель тороидальный Talema DPO-3.0 (⌀14–20, h 8), выводы 0,5 мм, шаг 10,16 (гибкие)", "inductor toroid talema")
    f.tht("1", -5.08, 0, 1.1, 2.2); f.tht("2", 5.08, 0, 1.1, 2.2)
    f.circle("F.Fab", 0, 0, 10.0, 0.1); f.circle("F.SilkS", 0, 0, 10.2, 0.15)
    f.circle("F.CrtYd", 0, 0, 10.5, 0.05)
    f.ref_at = (0, -11.5); f.val_at = (0, 11.5)
    FPS[f.name] = f


def module_zone():
    """Посадочная зона модуля XL4015E: 60 × 32 мм, четыре паза 3,2 × 10 под 45° (винты М3 в любом положении
    в пределах ±3,5 мм от типового шага 44 × 20), четыре проводных пятака IN+/IN−/OUT+/OUT− справа."""
    f = FP("Module_XL4015E_zone", "Зона под модуль XL4015E (60 × 32, пазы М3 ×4) с пятаками для проводов; сам модуль — E-007", "module zone xl4015e")
    for x, y, a in ((-22, -10, 45), (22, -10, 135), (-22, 10, 135), (22, 10, 45)):
        f.npth_slot(x, y, 3.2, 10.0, a)
    for num, y, t in (("1", -9.0, "IN+"), ("2", -3.0, "IN-"), ("3", 3.0, "OUT+"), ("4", 9.0, "OUT-")):
        f.tht(num, 36.0, y, 1.5, 3.0, "rect" if num == "1" else "circle")
        f.text("F.SilkS", t, 39.5, y, 0.8)
    f.rect("F.SilkS", -30, -16, 30, 16, 0.2)
    f.rect("F.Fab", -30, -16, 30, 16, 0.1)
    f.rect("F.CrtYd", -30.5, -16.5, 38.0, 16.5, 0.05)
    f.text("F.SilkS", "XL4015E  24 -> 5,0 V  (провода к пятакам)", 0, -13.5, 1.0)
    f.ref_at = (0, -17.5); f.val_at = (0, 17.5)
    FPS[f.name] = f




def pin_socket_1x22():
    """Гнездовая линейка 1 × 22, шаг 2,54 (PBS-22): отверстие 1,0, площадка 1,7; корпус 2,54 × 55,88; вывод 1 — сверху.
    Под модуль YD-ESP32-S3: ряды J1/J3 на расстоянии 25,4 мм (чертёж Espressif ESP32-S3-DevKitC-1: 25.40)."""
    f = FP("PinSocket_1x22_P2.54mm_Vertical", "Гнездовая линейка PBS-22 (1 × 22, 2,54 мм) под ряд модуля YD-ESP32-S3", "socket header pbs")
    for i in range(22):
        f.tht(str(i + 1), 0.0, i * 2.54, 1.0, 1.7, "rect" if i == 0 else "circle")
    f.outline(-1.27, -1.27, 1.27, 21 * 2.54 + 1.27, cy_margin=0.25)
    f.text("F.SilkS", "1", -2.8, 0.0, 0.8)
    f.ref_at = (0, -2.8); f.val_at = (0, 21 * 2.54 + 2.8)
    FPS[f.name] = f


def module_cjmcu9548():
    """Модуль CJMCU-9548 (TCA9548A): плата 31 × 21, два ряда по 12 штырей, шаг 2,54, расстояние между рядами 17,78
    (protosupplies.com: «DIP row spacing 17.8 mm»); ряды вдоль длинной стороны. Левый ряд сверху вниз: VIN, GND, SDA,
    SCL, RST, A0, A1, A2, SD0, SC0, SD1, SC1; правый ряд сверху вниз: SC7, SD7, SC6, SD6, SC5, SD5, SC4, SD4, SC3, SD3,
    SC2, SD2. Номера площадок = номера выводов символа Module_TCA9548 (1 VIN, 2 SDA, 3 SCL, 4 RST, 5 A0, 6 A1,
    7 A2, 8 GND, 9 SD0, 10 SC0, … 24 SC7). Модуль вставляется в гнёзда PBS-12 или паяется штырями."""
    f = FP("Module_CJMCU-9548", "Модуль CJMCU-9548 (TCA9548A), 31 × 21, 2 × 12 штырей 2,54, ряды 17,78 (protosupplies.com)", "module tca9548a i2c mux")
    left = ["1", "8", "2", "3", "4", "5", "6", "7", "9", "10", "11", "12"]
    right = ["24", "23", "22", "21", "20", "19", "18", "17", "16", "15", "14", "13"]
    for i, num in enumerate(left):
        f.tht(num, -8.89, -13.97 + i * 2.54, 1.0, 1.7, "rect" if num == "1" else "circle")
    for i, num in enumerate(right):
        f.tht(num, 8.89, -13.97 + i * 2.54, 1.0, 1.7)
    f.outline(-10.5, -15.5, 10.5, 15.5)
    for t, x, y in (("VIN", -6.2, -13.97), ("GND", -6.2, -11.43), ("SDA", -6.2, -8.89), ("SCL", -6.2, -6.35),
                    ("RST", -6.2, -3.81), ("A0", -6.2, -1.27), ("A1", -6.2, 1.27), ("A2", -6.2, 3.81),
                    ("SD0", -6.2, 6.35), ("SC0", -6.2, 8.89), ("SD1", -6.2, 11.43), ("SC1", -6.2, 13.97),
                    ("SC3", 6.2, 6.35), ("SD3", 6.2, 8.89), ("SC2", 6.2, 11.43), ("SD2", 6.2, 13.97)):
        f.text("F.Fab", t, x, y, 0.8)
    f.text("F.SilkS", "CJMCU-9548", 0, -12.0, 1.0)
    f.ref_at = (0, -17.0); f.val_at = (0, 17.0)
    FPS[f.name] = f


def dip6(horizontal=False):
    """DIP-6, ряды 7,62, шаг 2,54: отверстие 0,8, площадка 1,6. Выводы 1–3 — левый ряд сверху вниз, 4–6 — правый снизу
    вверх. horizontal — корпус повёрнут: выводы 1–3 — нижний ряд слева направо, 4–6 — верхний справа налево."""
    name = "DIP-6_W7.62mm" + ("_H" if horizontal else "")
    f = FP(name, "Корпус DIP-6 (КР293КП2Б), ряды 7,62 мм; ключ у вывода 1", "dip-6 optorelay")
    pts = [(-3.81, -2.54, "1"), (-3.81, 0.0, "2"), (-3.81, 2.54, "3"), (3.81, 2.54, "4"), (3.81, 0.0, "5"), (3.81, -2.54, "6")]
    body = (-3.3, -4.0, 3.3, 4.0)
    if horizontal:                                     # выводы 1–3 — нижний ряд слева направо, 4–6 — верхний справа налево
        pts = [(-2.54, 3.81, "1"), (0.0, 3.81, "2"), (2.54, 3.81, "3"), (2.54, -3.81, "4"), (0.0, -3.81, "5"), (-2.54, -3.81, "6")]
        body = (-4.0, -3.3, 4.0, 3.3)
    for x, y, n in pts:
        f.tht(n, x, y, 0.8, 1.6, "rect" if n == "1" else "circle")
    f.outline(*body)
    f.text("F.SilkS", "1", pts[0][0] - (0 if horizontal else 2.2), pts[0][1] + (2.2 if horizontal else 0), 0.8)
    f.ref_at = (0, body[1] - 1.5); f.val_at = (0, body[3] + 1.5)
    FPS[name] = f


def idc_2x06():
    """Вилка IDC BH-12 (2 × 6, шаг 2,54) с кожухом: отверстие 1,0, площадка 1,7; кожух 20,32 × 8,9 (стандарт).
    Нумерация IDC: нечётные — верхний ряд слева направо (1, 3, … 11), чётные — нижний (2, 4, … 12); ключ (паз) — сверху."""
    f = FP("IDC-Header_2x06_P2.54mm_Vertical", "Вилка IDC BH-12 (2 × 6, 2,54 мм) с кожухом 20,32 × 8,9; ключ сверху", "connector idc bh-12")
    for c in range(6):
        x = -6.35 + c * 2.54
        f.tht(str(2 * c + 1), x, -1.27, 1.0, 1.7, "rect" if c == 0 else "circle")
        f.tht(str(2 * c + 2), x, 1.27, 1.0, 1.7)
    f.outline(-10.16, -4.45, 10.16, 4.45)
    f.line("F.SilkS", -2.5, -4.65, -2.5, -3.6, 0.15); f.line("F.SilkS", 2.5, -4.65, 2.5, -3.6, 0.15)   # ключ
    f.text("F.SilkS", "1", -8.9, -3.0, 0.8)
    f.ref_at = (0, -6.0); f.val_at = (0, 6.0)
    FPS[f.name] = f


def fuse_ptc_radial():
    """Предохранитель самовосстанавливающийся радиальный (серия MF-R/RUEF ~1 А): шаг 5,08, отверстие 1,0; корпус
    ≈ 8 × 3,5 — модель не выбрана (E-083, «кандидат»), размеры уточнить по datasheet выбранной модели."""
    f = FP("Fuse_PTC_Radial_P5.08mm", "Предохранитель PTC радиальный, шаг 5,08 (модель E-083 уточняется)", "fuse ptc polyfuse")
    f.tht("1", -2.54, 0, 1.0, 1.8); f.tht("2", 2.54, 0, 1.0, 1.8)
    f.rect("F.Fab", -4.0, -1.75, 4.0, 1.75, 0.1); f.rect("F.SilkS", -4.2, -1.95, 4.2, 1.95, 0.15)
    f.rect("F.CrtYd", -4.5, -2.2, 4.5, 2.2, 0.05)
    f.ref_at = (0, -3.0); f.val_at = (0, 3.0)
    FPS[f.name] = f


# ---- расстановка ------------------------------------------------------------------------------------
PLACE, FOOT, POS, PADNET = [], {}, {}, {}


def set_place(rows):
    """rows — [(ref, footprint, value, x, y, {pad: net}), …]."""
    PLACE.clear(); PLACE.extend(rows)
    FOOT.clear(); FOOT.update({ref: fp for ref, fp, *_ in PLACE})
    POS.clear(); POS.update({ref: (x, y) for ref, _, _, x, y, _ in PLACE})
    PADNET.clear(); PADNET.update({ref: nets for ref, *_, nets in PLACE})


def pad(ref, num):
    """Абсолютные координаты площадки (первое вхождение номера)."""
    x0, y0 = POS[ref]
    for p in FPS[FOOT[ref]].pads:
        if p[0] == num:
            return (r3(x0 + p[3]), r3(y0 + p[4]))
    raise KeyError((ref, num))


# ---- дорожки, переходы и зоны ---------------------------------------------------------------------------
items = []
tracks = []   # (net, layer, width, [(x, y), ...]) — для check_pcb.py
vias = []     # (net, x, y) — для check_pcb.py


def seg(net, layer, w, *pts):
    tracks.append((net, layer, w, pts))
    for a, b in zip(pts, pts[1:]):
        items.append(f'  (segment (start {r3(a[0] + OBX)} {r3(a[1] + OBY)}) (end {r3(b[0] + OBX)} {r3(b[1] + OBY)}) '
                     f'(width {w}) (layer "{layer}") (net {NET[net]}) (uuid "{U("seg", net, layer, a, b)}"))')


def via(net, x, y):
    vias.append((net, x, y))
    items.append(f'  (via (at {r3(x + OBX)} {r3(y + OBY)}) (size {VIA_D}) (drill {VIA_DRILL}) (layers "F.Cu" "B.Cu") '
                 f'(net {NET[net]}) (uuid "{U("via", net, x, y)}"))')


def route(net, w, *pts, start_layer=F):
    """Манхэттенская трасса: горизонтальные отрезки — на F.Cu, вертикальные — на B.Cu, в углах — переходы.
    Начало/конец — площадки (сквозные, оба слоя). Диагонали не допускаются."""
    layer = start_layer
    for i, (a, b) in enumerate(zip(pts, pts[1:])):
        if abs(a[0] - b[0]) < 1e-9 and abs(a[1] - b[1]) < 1e-9:
            continue
        want = F if abs(a[1] - b[1]) < 1e-9 else B
        if i and want != layer:
            via(net, *a)
        layer = want
        seg(net, layer, w, a, b)




# ---- трассировщик (сетка, два слоя; F.Cu — преимущественно горизонтали, B.Cu — вертикали) ---------------------------
import heapq

GRID = 0.635


class Router:
    """Лабиринтный трассировщик по сетке GRID на двух слоях. Препятствия — площадки чужих цепей (с зазором),
    уже проложенные дорожки и переходы, край платы, запретные зоны. Стоимость шага: «свой» слой/направление 1,
    «чужое» направление 4, переход 8. Результат — сегменты и переходы через seg()/via()."""

    def __init__(self, w_default=0.8, keepouts=()):
        self.nx = int(BOARD_W / GRID) + 1
        self.ny = int(BOARD_H / GRID) + 1
        self.occ = [{}, {}]                     # слой → {(i, j): net}
        self.w_default = w_default
        self.keepouts = list(keepouts)
        self.fail = []
        self.novia = set()                      # клетки, где нельзя ставить переход (рядом с площадками/отверстиями)
        for ref, fpname, value, x0, y0, nets in PLACE:
            for num, kind, shape, x, y, sx, sy, drill, ang in FPS[fpname].pads:
                r = max(sx, sy) / 2
                net = nets.get(num, "") if num else ""
                if net.startswith("unconnected-"):
                    net = ""
                layers = (0,) if kind == "smd" else (0, 1)
                self.block(x0 + x, y0 + y, r + CLR + w_default / 2, net or "#pad", layers)
                self.novia.update(self.cells_near(x0 + x, y0 + y, r + CLR + VIA_D / 2 + 0.3))
        for hx, hy in HOLES:
            self.block(hx, hy, 1.6 + 0.2 + w_default / 2, "#hole", (0, 1))
            self.novia.update(self.cells_near(hx, hy, 1.6 + 0.2 + VIA_D / 2 + 0.3))
        for poly in self.keepouts:
            xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
            for i in range(int(min(xs) / GRID), int(max(xs) / GRID) + 2):
                for j in range(int(min(ys) / GRID), int(max(ys) / GRID) + 2):
                    if self._in_poly((i * GRID, j * GRID), poly):
                        self.occ[0][(i, j)] = "#keep"; self.occ[1][(i, j)] = "#keep"

    @staticmethod
    def _in_poly(p, poly):
        x, y = p; inside = False
        for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
            if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
                inside = not inside
        return inside

    def block(self, x, y, r, net, layers):
        """Занять клетки в радиусе r от (x, y) цепью net (чужие цепи туда не пройдут)."""
        n = int(r / GRID) + 1
        ci, cj = round(x / GRID), round(y / GRID)
        for i in range(ci - n, ci + n + 1):
            for j in range(cj - n, cj + n + 1):
                if math.hypot(i * GRID - x, j * GRID - y) <= r:
                    for L in layers:
                        cur = self.occ[L].get((i, j))
                        if cur is None or cur == net:
                            self.occ[L][(i, j)] = net
                        elif not cur.startswith("#") and net != cur:
                            self.occ[L][(i, j)] = "#conflict"   # две чужие цепи рядом — клетка закрыта для всех

    def free(self, L, i, j, net, w):
        if i < 1 or j < 1 or i >= self.nx - 1 or j >= self.ny - 1:
            return False
        if i * GRID - w / 2 < EDGE_MIN or j * GRID - w / 2 < EDGE_MIN or BOARD_W - i * GRID - w / 2 < EDGE_MIN or BOARD_H - j * GRID - w / 2 < EDGE_MIN:
            return False
        cur = self.occ[L].get((i, j))
        return cur is None or cur == net

    def cells_near(self, x, y, r):
        n = int(r / GRID) + 1
        ci, cj = round(x / GRID), round(y / GRID)
        return [(i, j) for i in range(ci - n, ci + n + 1) for j in range(cj - n, cj + n + 1) if math.hypot(i * GRID - x, j * GRID - y) <= r]

    def route(self, net, pads_xy, w=None, pad_r=0.85):
        """Соединить площадки цепи (список (x, y)) деревом: каждая следующая — к ближайшей уже проложенной меди."""
        w = w or self.w_default
        done = set()                                          # клетки (L, i, j), принадлежащие цепи
        starts = pads_xy[0]
        for L in (0, 1):
            for c in self.cells_near(*starts, pad_r):
                done.add((L,) + c)
        for tx, ty in pads_xy[1:]:
            targets = set()
            for L in (0, 1):
                for c in self.cells_near(tx, ty, pad_r):
                    targets.add((L,) + c)
            path = self._search(net, done, targets, w)
            if path is None:
                self.fail.append((net, (tx, ty)))
                continue
            self._emit(net, path, w, (tx, ty), pads_xy[0])
            for k, st in enumerate(path):
                done.add(st)
                self.block(st[1] * GRID, st[2] * GRID, w / 2 + CLR + self.w_default / 2, net, (st[0],))
                if k and path[k - 1][0] != st[0]:                                  # переход: оба слоя, радиус via
                    self.block(st[1] * GRID, st[2] * GRID, VIA_D / 2 + CLR + self.w_default / 2, net, (0, 1))
                    self.novia.update(self.cells_near(st[1] * GRID, st[2] * GRID, VIA_D + CLR))
        return not self.fail

    def _search(self, net, sources, targets, w):
        dist, prev = {}, {}
        pq = []
        for st in sources:
            L, i, j = st
            if self.free(L, i, j, net, w):
                dist[st] = 0; heapq.heappush(pq, (0, st))
        while pq:
            d, st = heapq.heappop(pq)
            if d > dist.get(st, 1e18):
                continue
            if st in targets:
                path = [st]
                while st in prev:
                    st = prev[st]; path.append(st)
                return path[::-1]
            L, i, j = st
            for di, dj, dL in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1)):
                nL = L ^ dL
                ni, nj = i + di, j + dj
                if not self.free(nL, ni, nj, net, w):
                    continue
                if dL:
                    if not self.free(L ^ 1, i, j, net, w) or (i, j) in self.novia:
                        continue
                    if min(i * GRID, j * GRID, BOARD_W - i * GRID, BOARD_H - j * GRID) < EDGE_MIN + VIA_D / 2:
                        continue
                    cost = 8
                else:
                    horiz = di != 0
                    cost = 1 if (horiz == (L == 0)) else 4
                nd = d + cost
                ns = (nL, ni, nj)
                if nd < dist.get(ns, 1e18):
                    dist[ns] = nd; prev[ns] = st; heapq.heappush(pq, (nd, ns))
        return None

    def _emit(self, net, path, w, tgt, src):
        """Сжать путь в отрезки, поставить переходы; концы подтянуть к центрам площадок."""
        pts = [(L, i, j) for L, i, j in path]
        runs = []                                         # (layer, [(i, j), ...]) — отрезки одного слоя
        cur_layer, cur = pts[0][0], [(pts[0][1], pts[0][2])]
        for L, i, j in pts[1:]:
            if L != cur_layer:
                runs.append((cur_layer, cur)); via(net, r3(i * GRID), r3(j * GRID))
                cur_layer, cur = L, [(i, j)]
            else:
                cur.append((i, j))
        runs.append((cur_layer, cur))
        for L, seq in runs:
            layer = F if L == 0 else B
            simp = [seq[0]]                               # оставляем только точки смены направления
            for k in range(1, len(seq) - 1):
                (i0, j0), (i1, j1), (i2, j2) = seq[k - 1], seq[k], seq[k + 1]
                if (i1 - i0, j1 - j0) != (i2 - i1, j2 - j1):
                    simp.append(seq[k])
            if len(seq) > 1:
                simp.append(seq[-1])
            simp = [(r3(i * GRID), r3(j * GRID)) for i, j in simp]
            if len(simp) > 1:
                seg(net, layer, w, *simp)
        pts = [(L, i * GRID, j * GRID) for L, i, j in path]
        # подводка к центрам площадок (та же цепь; короткие отрезки под любым углом)
        first_layer = F if pts[0][0] == 0 else B
        last_layer = F if pts[-1][0] == 0 else B
        a = (r3(pts[0][1]), r3(pts[0][2]))
        if math.hypot(a[0] - src[0], a[1] - src[1]) > 1e-6:
            pass  # начало лежит на уже проложенной меди или в площадке — подводка не нужна
        b = (r3(pts[-1][1]), r3(pts[-1][2]))
        if math.hypot(b[0] - tgt[0], b[1] - tgt[1]) > 1e-6:
            seg(net, last_layer, w, b, (r3(tgt[0]), r3(tgt[1])))


EDGE_MIN = 0.5


ZONES = {}   # имя: (цепь, слой, полигон, тип)


def zone_sexpr(name, net, layer, poly, kind):
    pts = " ".join(f"(xy {r3(x + OBX)} {r3(y + OBY)})" for x, y in poly)
    if kind in ("keepout", "keepout_pour"):
        tr = "not_allowed" if kind == "keepout" else "allowed"
        return (f'  (zone (net 0) (net_name "") (layers "F&B.Cu") (uuid "{U("zone", name)}") (name "{name}") (hatch edge 0.5)\n'
                f'    (connect_pads (clearance 0)) (min_thickness 0.25) (filled_areas_thickness no)\n'
                f'    (keepout (tracks {tr}) (vias {tr}) (pads allowed) (copperpour not_allowed) (footprints allowed))\n'
                f'    (fill (thermal_gap 0.5) (thermal_bridge_width 0.5))\n    (polygon (pts {pts}))\n  )')
    return (f'  (zone (net {NET[net]}) (net_name "{net}") (layer "{layer}") (uuid "{U("zone", name)}") (name "{name}") (hatch edge 0.5)\n'
            f'    (priority 1)\n    (connect_pads (clearance {CLR}))\n    (min_thickness 0.5) (filled_areas_thickness no)\n'
            f'    (fill yes (thermal_gap 0.6) (thermal_bridge_width 1.0))\n    (polygon (pts {pts}))\n  )')


# ---- контур, крепёж, надписи ------------------------------------------------------------------------------
HOLES = []        # (x, y) — М3 ⌀3,2
TEXTS = []        # (текст, x, y, размер) на F.SilkS
ISO_RECTS = []    # прямоугольники границы развязки (штрих-пунктир F.SilkS)
GR_RECTS = []     # (слой, x1, y1, x2, y2, ширина) — контуры модулей и т. п.


def gr_items():
    out = [f'  (gr_rect (start {OBX} {OBY}) (end {OBX + BOARD_W} {OBY + BOARD_H}) (stroke (width 0.1) (type default)) (fill no) (layer "Edge.Cuts") (uuid "{U("edge")}"))']
    for i, (x, y) in enumerate(HOLES):
        out.append(f'  (footprint "{LIB}:MountingHole_3.2mm_M3" (layer "F.Cu") (uuid "{U("hole", i)}") (at {r3(x + OBX)} {r3(y + OBY)})\n'
                   f'    (descr "Крепёжное отверстие М3 (⌀3,2), без металлизации")\n    (tags "mounting hole m3")\n'
                   f'    (property "Reference" "H{i + 1}" (at 0 -4.5 0) (layer "F.SilkS") (hide yes) (uuid "{U("hole", i, "ref")}") (effects (font (size 1 1) (thickness 0.15))))\n'
                   f'    (property "Value" "M3" (at 0 4.5 0) (layer "F.Fab") (hide yes) (uuid "{U("hole", i, "val")}") (effects (font (size 1 1) (thickness 0.15))))\n'
                   f'    (property "Footprint" "{LIB}:MountingHole_3.2mm_M3" (at 0 0 0) (layer "F.Fab") (hide yes) (uuid "{U("hole", i, "fp")}") (effects (font (size 1.27 1.27) (thickness 0.15))))\n'
                   f'    (property "Datasheet" "" (at 0 0 0) (layer "F.Fab") (hide yes) (uuid "{U("hole", i, "ds")}") (effects (font (size 1.27 1.27) (thickness 0.15))))\n'
                   f'    (property "Description" "" (at 0 0 0) (layer "F.Fab") (hide yes) (uuid "{U("hole", i, "de")}") (effects (font (size 1.27 1.27) (thickness 0.15))))\n'
                   f'    (attr exclude_from_pos_files exclude_from_bom)\n'
                   f'    (fp_circle (center 0 0) (end 3.3 0) (stroke (width 0.05) (type default)) (fill no) (layer "F.CrtYd") (uuid "{U("hole", i, "cy")}"))\n'
                   f'    (pad "" np_thru_hole circle (at 0 0) (size 3.2 3.2) (drill 3.2) (layers "*.Cu" "*.Mask") (uuid "{U("hole", i, "pad")}"))\n'
                   f'    (embedded_fonts no)\n  )')
    for t, x, y, s in TEXTS:
        s = max(s, 1.0)                                    # Резонит: высота шрифта маркировки ≥ 1,0 мм
        out.append(f'  (gr_text "{t}" (at {r3(x + OBX)} {r3(y + OBY)} 0) (layer "F.SilkS") (uuid "{U("text", t)}") (effects (font (size {s} {s}) (thickness 0.15))))')
    for layer, x1, y1, x2, y2, w in GR_RECTS:
        out.append(f'  (gr_rect (start {r3(x1 + OBX)} {r3(y1 + OBY)}) (end {r3(x2 + OBX)} {r3(y2 + OBY)}) (stroke (width {w}) (type default)) (fill no) (layer "{layer}") (uuid "{U("grrect", layer, x1, y1, x2, y2)}"))')
    for r in ISO_RECTS:                                    # штрих-пунктир границы острова на F.SilkS
        for a, b in zip(r, r[1:] + r[:1]):
            out.append(f'  (gr_line (start {r3(a[0] + OBX)} {r3(a[1] + OBY)}) (end {r3(b[0] + OBX)} {r3(b[1] + OBY)}) (stroke (width 0.2) (type dash_dot)) (layer "F.SilkS") (uuid "{U("iso", a, b)}"))')
    return out


# ---- сборка -----------------------------------------------------------------------------------------------
def header():
    return f'''(kicad_pcb (version {PCB_VER}) (generator "pcbnew") (generator_version "{PCB_GEN_VER}")
  (general (thickness 1.6) (legacy_teardrops no))
  (paper "A3")
  (title_block
    (title "{TITLE}")
    (date "{DATE}")
    (rev "{REV}")
    (company "{COMPANY}")
  )
  (layers
    (0 "F.Cu" signal) (2 "B.Cu" signal)
    (9 "F.Adhes" user "F.Adhesive") (11 "B.Adhes" user "B.Adhesive")
    (13 "F.Paste" user) (15 "B.Paste" user)
    (5 "F.SilkS" user "F.Silkscreen") (7 "B.SilkS" user "B.Silkscreen")
    (1 "F.Mask" user) (3 "B.Mask" user)
    (17 "Dwgs.User" user "User.Drawings") (19 "Cmts.User" user "User.Comments")
    (21 "Eco1.User" user "User.Eco1") (23 "Eco2.User" user "User.Eco2")
    (25 "Edge.Cuts" user) (27 "Margin" user)
    (31 "F.CrtYd" user "F.Courtyard") (29 "B.CrtYd" user "B.Courtyard")
    (35 "F.Fab" user) (33 "B.Fab" user)
  )
  (setup
    (stackup
      (layer "F.SilkS" (type "Top Silk Screen"))
      (layer "F.Paste" (type "Top Solder Paste"))
      (layer "F.Mask" (type "Top Solder Mask") (thickness 0.01))
      (layer "F.Cu" (type "copper") (thickness 0.0175))
      (layer "dielectric 1" (type "core") (thickness 1.545) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02))
      (layer "B.Cu" (type "copper") (thickness 0.0175))
      (layer "B.Mask" (type "Bottom Solder Mask") (thickness 0.01))
      (layer "B.Paste" (type "Bottom Solder Paste"))
      (layer "B.SilkS" (type "Bottom Silk Screen"))
      (copper_finish "HAL lead-free")
      (dielectric_constraints no)
    )
    (pad_to_mask_clearance 0.05)
    (allow_soldermask_bridges_in_footprints no)
    (grid_origin {OBX} {OBY})
    (pcbplotparams (layerselection 0x00000000_00000000_55555555_5755f5ff) (plot_on_all_layers_selection 0x00000000_00000000_00000000_00000000)
      (disableapertmacros no) (usegerberextensions no) (usegerberattributes yes) (usegerberadvancedattributes yes) (creategerberjobfile yes)
      (dashed_line_dash_ratio 12) (dashed_line_gap_ratio 3) (svgprecision 4) (plotframeref no) (mode 1) (useauxorigin no)
      (hpglpennumber 1) (hpglpenspeed 20) (hpglpendiameter 15) (pdf_front_fp_property_popups yes) (pdf_back_fp_property_popups yes)
      (pdf_metadata yes) (pdf_single_document no) (dxfpolygonmode yes) (dxfimperialunits yes) (dxfusepcbnewfont yes) (psnegative no)
      (psa4output no) (plot_black_and_white yes) (sketchpadsonfab no) (plotpadnumbers no) (hidednponfab no) (sketchdnponfab yes)
      (crossoutdnponfab yes) (subtractmaskfromsilk no) (outputformat 1) (mirror no) (drillshape 1) (scaleselection 1) (outputdirectory ""))
  )
'''


def build():
    nets_s = "\n".join(f'  (net {i} "{n}")' for i, n in enumerate(NETS))
    fps = [FPS[fpname].sexpr(ref, value, x, y, nets) for ref, fpname, value, x, y, nets in PLACE]
    zones = [zone_sexpr(n, *v) for n, v in ZONES.items()]
    body = "\n".join([nets_s] + fps + gr_items() + items + zones)
    return header() + body + "\n  (embedded_fonts no)\n)\n"


def pro_rules(classes):
    """Правила и классы цепей для <КОД>.kicad_pro (объединяются с существующим файлом проекта):
    classes — [(имя, ширина, зазор, [шаблоны цепей]), …]; первый — Default."""
    import json
    path = ROOT / "boards" / PROJECT / f"{PROJECT}.kicad_pro"
    d = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"meta": {"filename": path.name, "version": 3}}
    d.setdefault("board", {}).setdefault("design_settings", {})["rules"] = {
        "min_clearance": 0.3, "min_connection": 0.3, "min_copper_edge_clearance": 0.5, "min_hole_clearance": 0.3,
        "min_hole_to_hole": 0.5, "min_through_hole_diameter": 0.3, "min_track_width": 0.3, "min_via_annular_width": 0.2,
        "min_via_diameter": 1.0, "min_text_height": 1.0, "min_text_thickness": 0.15, "solder_mask_to_copper_clearance": 0.0}
    cls, pats = [], []
    for name, w, clr, nets in classes:
        cls.append({"name": name, "clearance": clr, "track_width": w, "via_diameter": VIA_D, "via_drill": VIA_DRILL,
                    "bus_width": 12, "wire_width": 6, "line_style": 0, "diff_pair_gap": 0.25, "diff_pair_via_gap": 0.25,
                    "diff_pair_width": 0.2, "microvia_diameter": 0.3, "microvia_drill": 0.1,
                    "pcb_color": "rgba(0, 0, 0, 0.000)", "schematic_color": "rgba(0, 0, 0, 0.000)",
                    "priority": 2147483647 if name == "Default" else len(cls)})
        pats += [{"netclass": name, "pattern": n} for n in nets]
    d["net_settings"] = {"classes": cls, "meta": {"version": 5}, "net_colors": None, "netclass_assignments": None,
                         "netclass_patterns": pats}
    path.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write():
    out_pcb = ROOT / "boards" / PROJECT / f"{PROJECT}.kicad_pcb"
    OUT_FP.mkdir(parents=True, exist_ok=True)
    out_pcb.write_text(build(), encoding="utf-8")
    for name, f in FPS.items():
        (OUT_FP / f"{name}.kicad_mod").write_text(f.lib_file(), encoding="utf-8")
    hole = FP("MountingHole_3.2mm_M3", "Крепёжное отверстие М3 (⌀3,2), без металлизации", "mounting hole")
    hole.pads.append(("", "np_thru_hole", "circle", 0, 0, 3.2, 3.2, (3.2, 3.2), 0))
    hole.circle("F.CrtYd", 0, 0, 3.3, 0.05)
    (OUT_FP / "MountingHole_3.2mm_M3.kicad_mod").write_text(hole.lib_file(), encoding="utf-8")
    gk = OUT_FP / ".gitkeep"
    if gk.exists():
        gk.unlink()
    print(f"{PROJECT}.kicad_pcb: {len(PLACE)} компонентов, {len(items)} сегментов/переходов, {len(ZONES)} зон; footprint'ов: {len(FPS) + 1}")

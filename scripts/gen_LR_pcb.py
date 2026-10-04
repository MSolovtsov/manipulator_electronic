#!/usr/bin/env python3
"""Генератор печатной платы LR (панель лабораторных работ) учебного манипулятора — формат KiCad 9/10.

Пишет boards/LR/LR.kicad_pcb и недостающие посадочные места в lib/footprints/manipulator.pretty/.
Схема — boards/LR/LR.kicad_sch (scripts/gen_LR_sch.py), общая часть — scripts/pcb_common.py,
проверки — scripts/check_pcb.py LR и scripts/check_sch_pcb.py LR.

Состав (схема LR): четыре одинаковые группы M1…M4 (клеммы E-051, защита 100 Ом + BAT54S + 1N4148,
разъём к плате CH, двухцветный светодиод с двумя резисторами 150 Ом) и узел расширителя портов
(PCF8574 + разъём к плате MC).

ОГРАНИЧЕНИЯ ЭТОЙ ВЕРСИИ — плату нельзя заказывать, пока не сняты оба пункта:
  1. Клемма E-051 («комбинированные приборные клеммы: винт + гнездо банан 4 мм») — конкретная модель
     не выбрана (база компонентов, примечание E-051: «Варианты … отложены»). Посадочное место
     TermGroup_5x_Banana4 сделано ПАРАМЕТРИЧЕСКИМ: шаг, диаметр отверстия и площадки — константы
     TERM_* ниже; принятые значения типовые, не из datasheet. От шага клеммы прямо зависит размер платы.
  2. Чертежа корпуса нет: размер платы, положение клемм и светодиодов на передней стенке и ограничение
     по высоте компонентов (MAX_H) не заданы. Поэтому FIXED пустой — конструктивной привязки нет.

Раскладка клемм в группе — 3 × 2 по утверждённому примечанию базы к E-051: верхний ряд SCL, SDA, GND_L,
нижний ряд IN1, IN2, свободная позиция. Свободная позиция занята светодиодом группы HL1…HL4 — он смотрит
на ту же переднюю стенку, что и клеммы.

Запуск: python3 scripts/gen_LR_pcb.py
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pcb_common as pc                    # noqa: E402
from pcb_common import *                   # noqa: E402,F401,F403

# ---- клемма E-051: ПРЕДВАРИТЕЛЬНЫЕ размеры, модель не выбрана --------------------------------------
TERM_PITCH = 19.05      # шаг клемм в группе, мм — типовой для приборных зажимов 4 мм; СВЕРИТЬ
TERM_DRILL = 6.5        # отверстие под резьбовой корпус клеммы, мм; СВЕРИТЬ
TERM_PAD = 8.5          # металлизированная площадка вокруг отверстия (поясок 1,0 мм); СВЕРИТЬ
TERM_BODY = 12.0        # габарит корпуса клеммы над платой, мм; СВЕРИТЬ

pc.PROJECT = PROJECT = "LR"
pc.ROOT_UUID = ROOT_UUID = "7b2e4d19-6c85-4a37-b0e2-1f6a8c35d947"      # тот же, что в gen_LR_sch.py
pc.BOARD_W, pc.BOARD_H = BOARD_W, BOARD_H = 150.0, 155.0               # следует из TERM_PITCH; см. docstring
pc.TITLE, pc.REV = "Манипулятор учебный. Панель лабораторных работ LR", "LR-A1"

CLR = pc.CLR

# ---- цепи ------------------------------------------------------------------------------------------
GRP = [1, 2, 3, 4]
P_PINS = {4: "P0", 5: "P1", 6: "P2", 7: "P3", 9: "P4", 10: "P5", 11: "P6", 12: "P7"}
UNNAMED = []
for k in GRP:
    T, C = f"X{4 + k}", f"X{k}"
    UNNAMED += [f"Net-({T}-IN1)", f"Net-({T}-IN2)", f"Net-({T}-SDA)", f"Net-({T}-SCL)",
                f"Net-({C}-SDA)", f"Net-({C}-SCL)", f"Net-(HL{k}-K1)", f"Net-(HL{k}-K2)"]
UNNAMED += [f"Net-(DD1-{n})" for n in P_PINS.values()]
NC = ["unconnected-(DD1-INT)"]
set_nets(["", "3V3", "GND_L", "SDA", "SCL"] + UNNAMED + NC)

# ---- посадочные места ------------------------------------------------------------------------------
jst_xh(5, "L"); jst_xh(4, "R"); r_axial(); dip16(); d_do35(); sot23(); led_bicolor_5mm()

_f = FP("TermGroup_5x_Banana4",
        "Группа из 5 комбинированных приборных клемм E-051 (винт + гнездо 4 мм), раскладка 3 × 2: "
        "ПРЕДВАРИТЕЛЬНОЕ место, модель клеммы не выбрана — сверить шаг и отверстие",
        "terminal banana 4mm", height=TERM_BODY)
# позиции сетки 3 × 2 относительно центра группы; номера — выводы символа X5…X8 схемы
_GRID = {"4": (-TERM_PITCH, -TERM_PITCH / 2),      # SCL
         "3": (0.0, -TERM_PITCH / 2),              # SDA
         "5": (TERM_PITCH, -TERM_PITCH / 2),       # GND_L
         "1": (-TERM_PITCH, TERM_PITCH / 2),       # IN1
         "2": (0.0, TERM_PITCH / 2)}               # IN2  (позиция (+P, +P/2) свободна — там светодиод)
for _n, (_x, _y) in _GRID.items():
    _f.tht(_n, _x, _y, TERM_DRILL, TERM_PAD, "rect" if _n == "1" else "circle")
    _f.circle("F.SilkS", _x, _y, TERM_BODY / 2, 0.15)
    # courtyard — по каждой клемме отдельно: свободная позиция сетки 3 × 2 остаётся свободной (там светодиод)
    _f.circle("F.CrtYd", _x, _y, TERM_BODY / 2 + 0.5, 0.05)
_f.ref_at = (0, -TERM_PITCH / 2 - TERM_BODY / 2 - 1.8)
_f.val_at = (0, TERM_PITCH / 2 + TERM_BODY / 2 + 1.8)
FPS["TermGroup_5x_Banana4"] = _f

# ---- компоновка: функциональные узлы ---------------------------------------------------------------
TC = {1: (38.0, 24.0), 2: (112.0, 24.0), 3: (38.0, 84.0), 4: (112.0, 84.0)}   # центры групп клемм
YA, YB, YC = 22.0, 29.0, 40.0        # три ряда полосы группы: разъём+100 Ом+диод / ограничители / 150 Ом
BAND_A = {k: TC[k][1] + YA for k in GRP}
BAND_B = {k: TC[k][1] + YB for k in GRP}     # ряд ограничителей SOT-23 (от него идут отводы вниз)
BAND_C = {k: TC[k][1] + YC for k in GRP}
STRIP_Y = 142.0                              # полоса расширителя портов внизу платы

PLACE_ROWS = []
for k in GRP:
    cx, cy = TC[k]
    T, C = f"X{4 + k}", f"X{k}"
    d1, d2 = f"VD{4 * k - 3}", f"VD{4 * k - 2}"       # 1N4148 в линиях IN1, IN2
    z1, z2 = f"VD{4 * k - 1}", f"VD{4 * k}"           # BAT54S на линиях SDA, SCL
    rs, rc = f"R{2 * k - 1}", f"R{2 * k}"             # 100 Ом в линиях SDA, SCL
    rl1, rl2 = f"R{8 + 2 * k - 1}", f"R{8 + 2 * k}"   # 150 Ом в катодах светодиода
    hl = f"HL{k}"
    p_hi, p_lo = sorted(P_PINS)[2 * (k - 1) + 1], sorted(P_PINS)[2 * (k - 1)]   # R нечётный — старший вывод (см. схему)
    PLACE_ROWS += [
        (T, "TermGroup_5x_Banana4", "E-051 x5", cx, cy,
         {"1": f"Net-({T}-IN1)", "2": f"Net-({T}-IN2)", "3": f"Net-({T}-SDA)",
          "4": f"Net-({T}-SCL)", "5": "GND_L"}),
        (hl, "LED_Bicolor_5mm", "зел/красн", cx + TERM_PITCH, cy + TERM_PITCH / 2,
         {"1": "3V3", "2": f"Net-(HL{k}-K1)", "3": f"Net-(HL{k}-K2)"}),
        (C, "JST_XH_B5B-XH-A_L", "B5B-XH-A", cx - 26.0, BAND_A[k] + 3.0,
         {"1": f"Net-({T}-IN1)", "2": f"Net-({T}-IN2)", "3": f"Net-({C}-SDA)",
          "4": f"Net-({C}-SCL)", "5": "GND_L"}),
        (rs, "R_Axial_P10.16mm", "100 Ом", cx - 12.0, BAND_A[k],
         {"1": f"Net-({T}-SDA)", "2": f"Net-({C}-SDA)"}),
        (rc, "R_Axial_P10.16mm", "100 Ом", cx + 2.0, BAND_A[k],
         {"1": f"Net-({T}-SCL)", "2": f"Net-({C}-SCL)"}),
        (d1, "D_DO-35_P7.62mm", "1N4148", cx + 16.0, BAND_A[k],
         {"1": f"Net-({T}-IN1)", "2": "GND_L"}),
        (d2, "D_DO-35_P7.62mm", "1N4148", cx + 16.0, BAND_B[k],
         {"1": f"Net-({T}-IN2)", "2": "GND_L"}),
        (z1, "SOT-23", "BAT54S", cx - 9.0, BAND_B[k], {"1": "GND_L", "2": "3V3", "3": f"Net-({C}-SDA)"}),
        (z2, "SOT-23", "BAT54S", cx - 2.0, BAND_B[k], {"1": "GND_L", "2": "3V3", "3": f"Net-({C}-SCL)"}),
        (rl1, "R_Axial_P10.16mm", "150 Ом", cx - 12.0, BAND_C[k],
         {"1": f"Net-(HL{k}-K1)", "2": f"Net-(DD1-{P_PINS[p_hi]})"}),
        (rl2, "R_Axial_P10.16mm", "150 Ом", cx + 2.0, BAND_C[k],
         {"1": f"Net-(HL{k}-K2)", "2": f"Net-(DD1-{P_PINS[p_lo]})"}),
    ]

DD1_NETS = {"1": "GND_L", "2": "GND_L", "3": "GND_L", "8": "GND_L", "16": "3V3",
            "13": "unconnected-(DD1-INT)", "14": "SCL", "15": "SDA"}
DD1_NETS.update({str(n): f"Net-(DD1-{v})" for n, v in P_PINS.items()})
PLACE_ROWS += [
    ("DD1", "DIP-16_W7.62mm", "PCF8574", 70.0, 78.0, DD1_NETS),
    ("X9", "JST_XH_B4B-XH-A_R", "B4B-XH-A", 118.0, STRIP_Y,
     {"1": "3V3", "2": "SCL", "3": "SDA", "4": "GND_L"}),
]
set_place(PLACE_ROWS)

UNITS = {}
for k in GRP:
    UNITS[f"группа M{k}"] = [f"X{4 + k}", f"HL{k}", f"X{k}",
                             f"VD{4 * k - 3}", f"VD{4 * k - 2}", f"VD{4 * k - 1}", f"VD{4 * k}",
                             f"R{2 * k - 1}", f"R{2 * k}", f"R{8 + 2 * k - 1}", f"R{8 + 2 * k}"]
UNITS["расширитель портов"] = ["DD1"]
UNITS["разъём к MC"] = ["X9"]          # краевой разъём, ставится по корпусу, а не по узлу
FIXED = {}          # чертежа передней стенки нет — конструктивной привязки нет (требует уточнения)
CHANNELS = [(62.0, 40.0, 78.0, 62.0, "P0…P7 от DD1 к светодиодам, 3V3 и GND_L между группами")]
MAX_H = None        # ограничение по высоте — требует уточнения по чертежу корпуса

# ---- крепёж (до трассировки: трассировщик обходит отверстия только если они уже объявлены) ----------
HOLES.extend([(6, 6), (BOARD_W - 6, 6), (6, BOARD_H - 6), (BOARD_W - 6, BOARD_H - 6), (6, 76), (BOARD_W - 6, 76)])

# ---- трассировка -----------------------------------------------------------------------------------
ROUTER_STRATEGY = "plane"    # сигналы по F.Cu, B.Cu отдан земле GND_L: плата разреженная, переходы не нужны
W_TRACK = 0.8                # одна ширина для всех цепей: токи логические, запас по норме проекта

rt = Router(w_default=W_TRACK, strategy=ROUTER_STRATEGY)

# Выводы 1 (GND_L) и 2 (3V3) ограничителя BAT54S отстоят на 1,9 мм. Зоны запрета вокруг них
# (радиус r + зазор + полширины = 1,5 мм) перекрываются, клетки становятся «ничьими», и лабиринтный
# трассировщик к этим площадкам не проходит в принципе. Поэтому от них рисуем короткие отводы руками
# и сообщаем о них трассировщику (block): GND_L — отвод и переход в зону земли на B.Cu;
# 3V3 — отвод и переход, который дальше служит точкой подключения для трассировщика.
STUB_DX, STUB_DY_G, STUB_DY_P = 2.6, 3.2, 5.4   # переходы GND_L и 3V3 разнесены по вертикали


def block_path(net, pts, layers=(0,)):
    """Пометить занятыми клетки вдоль нарисованной руками дорожки, чтобы трассировщик её видел."""
    r = W_TRACK + CLR
    for q1, q2 in zip(pts, pts[1:]):
        n = max(1, int(math.hypot(q2[0] - q1[0], q2[1] - q1[1]) / 0.3))
        for i in range(n + 1):
            t = i / n
            rt.block(q1[0] + (q2[0] - q1[0]) * t, q1[1] + (q2[1] - q1[1]) * t, r, net, layers)


SMD_SKIP, SMD_VIA = set(), {}
for k in GRP:
    for z in (f"VD{4 * k - 1}", f"VD{4 * k}"):
        p1, p2 = pad(z, "1"), pad(z, "2")
        sx, sy = r3((p1[0] + p2[0]) / 2), BAND_B[k]
        g = (r3(sx - STUB_DX), r3(sy + STUB_DY_G))        # переход GND_L в зону на B.Cu
        v = (r3(sx + STUB_DX), r3(sy + STUB_DY_P))        # переход 3V3 — точка подключения трассировщика
        seg("GND_L", F, W_TRACK, p1, g); via("GND_L", *g)
        seg("3V3", F, W_TRACK, p2, v); via("3V3", *v)
        block_path("#keep", [p1, g]); rt.block(g[0], g[1], VIA_D / 2 + CLR + W_TRACK / 2 + DFM["chamfer"], "#keep", (0, 1))
        block_path("3V3", [p2, v]);    rt.block(v[0], v[1], VIA_D / 2 + CLR + W_TRACK / 2 + DFM["chamfer"], "3V3", (0, 1))
        SMD_SKIP |= {(z, "1"), (z, "2")}
        SMD_VIA.setdefault(k, []).append(v)
for k in GRP:                       # перемычка 3V3 между переходами двух ограничителей группы
    v1, v2 = SMD_VIA[k]
    seg("3V3", F, W_TRACK, v1, v2); block_path("3V3", [v1, v2])

netpads = {}
for ref, fpname, value, x0, y0, nets in PLACE:
    for num, kind, shape, x, y, sx_, sy_, drill, ang in FPS[fpname].pads:
        n = nets.get(num, "")
        if not n or n.startswith("unconnected-") or (ref, num) in SMD_SKIP:
            continue
        netpads.setdefault(n, []).append((r3(x0 + x), r3(y0 + y)) + ((0,) if kind == "smd" else ()))
netpads["GND_L"] = []                       # землю разливает зона на B.Cu
del netpads["3V3"]                          # 3V3 разводим отдельно: сначала по группам, потом магистраль

ORDER = []
for k in GRP:
    T, C = f"X{4 + k}", f"X{k}"
    ORDER += [f"Net-({T}-IN1)", f"Net-({T}-IN2)", f"Net-({T}-SDA)", f"Net-({T}-SCL)",
              f"Net-({C}-SDA)", f"Net-({C}-SCL)", f"Net-(HL{k}-K1)", f"Net-(HL{k}-K2)"]
ORDER += [f"Net-(DD1-{v_})" for v_ in P_PINS.values()] + ["SCL", "SDA"]   # SCL раньше SDA: его площадка на X9 зажата
for net in ORDER:
    pts = netpads.get(net, [])
    if len(pts) > 1:
        rt.route(net, pts, W_TRACK)

# 3V3: сначала местная раздача внутри группы (анод светодиода — переходы ограничителей),
# потом магистраль между группами и расширителем портов. Так каждая ветка короткая и проверяемая.
for k in GRP:
    rt.route("3V3", [pad(f"HL{k}", "1"), SMD_VIA[k][1]], W_TRACK)
rt.route("3V3", [pad("HL1", "1"), pad("HL2", "1"), pad("HL3", "1"), pad("HL4", "1"),
                 pad("DD1", "16"), pad("X9", "1")], W_TRACK)
FAILED = rt.fail

# ---- зоны, крепёж, надписи -------------------------------------------------------------------------
ZONES.update({"GND_L": ("GND_L", B, [(1, 1), (BOARD_W - 1, 1), (BOARD_W - 1, BOARD_H - 1), (1, BOARD_H - 1)], "copper")})
ISLAND = set()            # гальванической развязки на LR нет: вся плата на логической земле
POWER_ZONE = None

_LBL_DY = TERM_PITCH / 2 + TERM_BODY / 2 + 2.6          # подпись столбцов — выше корпусов клемм
TEXTS.extend([("Манипулятор учебный — панель ЛР rev A1", 75.0, 152.0, 1.2),
              ("M1", 16.0, 24.0, 2.0), ("M2", 90.0, 24.0, 2.0),
              ("M3", 16.0, 84.0, 2.0), ("M4", 90.0, 84.0, 2.0)]
             + [("SCL   SDA   GND", TC[k][0], TC[k][1] - _LBL_DY, 1.2) for k in GRP]
             + [("к MC", 118.0, 131.0, 1.2), ("PCF8574", 70.0, 90.0, 1.2),
                ("КЛЕММЫ E-051 — МОДЕЛЬ НЕ ВЫБРАНА, ПЛАТУ НЕ ЗАКАЗЫВАТЬ", 75.0, 148.5, 1.2)])

# ---- технологическая доводка (DFM, см. CLAUDE.md «Генерация платы») ---------------------------------
hole_keepouts()      # вырез заливки вокруг крепежа: винт М3 с шайбой не должен касаться меди
chamfer_tracks()     # прямые углы ортогонального Router — под 45°

if __name__ == "__main__":
    write()
    pro_rules([("Default", 0.8, CLR, []), ("Power3V3", 1.0, CLR, ["3V3", "GND_L"])])
    if FAILED:
        print("НЕ ПРОЛОЖЕНЫ:", FAILED)

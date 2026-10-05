#!/usr/bin/env python3
"""Генератор печатной платы MC (контроллер) учебного манипулятора.

Создаёт boards/MC/MC.kicad_pcb (формат KiCad 9, читается KiCad 10) и footprint'ы в lib/footprints/manipulator.pretty.
Общая часть (класс FP, библиотека посадочных мест, трассировщик, зоны, сборка) — scripts/pcb_common.py.

Исходные данные посадочных мест:
  гнёзда XS1/XS2 — PBS-22, ряды на 25,40 мм (механический чертёж Espressif ESP32-S3-DevKitC-1, DXF 2021-03-12; модуль
  YD-ESP32-S3 — клон, длина платы 62,74; сверить с модулем перед заказом);
  U1 — CJMCU-9548: плата 31 × 21, два ряда по 12 штырей, шаг 2,54, между рядами 17,78 (protosupplies.com);
  U2 — КР293КП2Б в DIP-6 (Протон, promelec.ru: «DIP-6»); нумерация выводов — по символу, сверить по ТУ;
  FU1 — радиальный PTC, шаг 5,08 (модель E-083 не выбрана — размер корпуса уточнить);
  JST XH/VH, IDC BH-12, резисторы/конденсатор — стандартные.

Правила (Резонит, 2 слоя, FR-4 1,6, фольга 18 мкм): зазор 0,5, сигнальные 0,8, питание 1,0, переходы 1,2/0,6.
Слои: F.Cu — преимущественно горизонтальные дорожки и зона GND_P (силовой угол слева внизу), B.Cu — вертикальные
дорожки и зона GND_L (остров — вся плата, кроме силового угла). Граница развязки GND_P/GND_L — штрих-пунктир.

Компоновка (мм, от левого верхнего угла; плата 120 × 102):
  левый край сверху вниз — X1 схват, X5 +5V_L с PS, X4 концевик (остров); X2 +5P с PS, X3 кнопка KH (силовой угол);
  модуль ESP32 в гнёздах XS1/XS2 — слева от центра, антенна к верхнему краю, USB к центру платы;
  U1 (CJMCU-9548) с подтяжками R1…R3 — справа вверху; X10 (LR) — правый край;
  U2 (оптореле) с R4…R6, C1, R7, FU1 — левая колонка; R8/R9 (делитель RX схвата, E-073) — между X1 и гнёздами; X6…X9 (CH1…CH4) — нижний край в ряд, шаг 25,4.

Запуск: python3 scripts/gen_MC_pcb.py; затем scripts/check_pcb.py MC и scripts/check_sch_pcb.py MC
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pcb_common as pc                    # noqa: E402
from pcb_common import *                   # noqa: E402,F401,F403

pc.PROJECT = PROJECT = "MC"
pc.ROOT_UUID = ROOT_UUID = "3c7e9a10-5b2d-4e8f-9a61-0d4c2b7f6e55"
pc.BOARD_W, pc.BOARD_H = BOARD_W, BOARD_H = 120.0, 102.0
pc.TITLE, pc.REV = "Манипулятор учебный. Плата контроллера MC", "MC-A1"

# ---- цепи ------------------------------------------------------------------------------------------
SIG = [f"M{m}_{s}" for m in range(1, 5) for s in ("CURR", "RELE", "IN1", "IN2", "SDA", "SCL")]
NC = [f"unconnected-(XS1-{n}-Pad{p})" for n, p in (("RST", 3), ("IO3", 13), ("IO46", 14))] + \
     [f"unconnected-(XS2-{n}-Pad{p})" for n, p in (("TX", 2), ("RX", 3), ("IO37", 11), ("IO36", 12), ("IO35", 13),
                                                    ("IO0", 14), ("IO45", 15), ("IO20", 19), ("IO19", 20))] + \
     [f"unconnected-(U1-{n}-Pad{p})" for p, n in zip(range(17, 25), ("SD4", "SC4", "SD5", "SC5", "SD6", "SC6", "SD7", "SC7"))] + \
     ["unconnected-(U2-Pad3)", "unconnected-(U2-Pad5)"] + [f"unconnected-(X{k}-Pad12)" for k in range(6, 10)]
set_nets(["", "3V3", "+5V_L", "GND_L", "+5P", "GND_P", "KH", "Net-(U2-OUT)", "SDA", "SCL", "MUX-RST", "MUX-A0", "MUX-A1",
          "Net-(XS2-IO2)", "Net-(XS2-IO1)", "Net-(XS2-IO48)", "Net-(FU1-Pad1)", "Net-(R5-Pad1)",
          "Net-(R8-Pad1)"] + SIG + NC)

# ---- посадочные места этой платы ----------------------------------------------------------------------
jst_xh(4, "L"); jst_xh(2, "L"); jst_xh(4, "R"); jst_vh(2, orient="L")
pin_socket_1x22(); module_cjmcu9548(); dip6(horizontal=True); idc_2x06(); fuse_ptc_radial()
r_axial(); r_axial(vertical=True); c_disc()

# ---- расстановка ------------------------------------------------------------------------------------
XS1_X, XS2_X, XS_Y = 34.0, 59.4, 8.0          # гнёзда: вывод 1 сверху (край антенны), ряды на 25,4
CH_X = [30.5, 55.9, 81.3, 106.7]              # центры X6…X9, шаг 25,4; ряды выводов y = 90,5 (нечётные) / 93,04 (чётные)
CH_Y = 91.77

# ряд J1 (XS1) / J3 (XS2): номер контакта → цепь
J1 = {"1": "3V3", "2": "3V3", "3": NC[0], "4": "M1_CURR", "5": "M2_CURR", "6": "M3_CURR", "7": "M4_CURR",
      "8": "M3_IN2", "9": "M4_IN1", "10": "M4_IN2", "11": "M1_RELE", "12": "SDA", "13": NC[1], "14": NC[2],
      "15": "SCL", "16": "M1_IN1", "17": "M1_IN2", "18": "M2_IN1", "19": "M2_IN2", "20": "M3_IN1", "21": "+5V_L", "22": "GND_L"}
J3 = {"1": "GND_L", "2": NC[3], "3": NC[4], "4": "Net-(XS2-IO1)", "5": "Net-(XS2-IO2)", "6": "MUX-RST",
      "7": "Net-(U2-OUT)", "8": "M4_RELE", "9": "M3_RELE", "10": "MUX-A1", "11": NC[5], "12": NC[6], "13": NC[7],
      "14": NC[8], "15": NC[9], "16": "Net-(XS2-IO48)", "17": "MUX-A0", "18": "M2_RELE", "19": NC[10], "20": NC[11],
      "21": "GND_L", "22": "GND_L"}
U1N = {"1": "3V3", "2": "SDA", "3": "SCL", "4": "MUX-RST", "5": "MUX-A0", "6": "MUX-A1", "7": "GND_L", "8": "GND_L",
       "9": "M1_SDA", "10": "M1_SCL", "11": "M2_SDA", "12": "M2_SCL", "13": "M3_SDA", "14": "M3_SCL", "15": "M4_SDA", "16": "M4_SCL"}
U1N.update({str(17 + i): NC[12 + i] for i in range(8)})


def ch_nets(m):
    """Контакты вилки CH: нечётные — сигналы (верхний ряд), чётные — питание/земли/KH (нижний ряд)."""
    return {"1": f"M{m}_CURR", "2": "GND_L", "3": f"M{m}_RELE", "4": "+5V_L", "5": f"M{m}_IN1", "6": "+5P",
            "7": f"M{m}_IN2", "8": "KH", "9": f"M{m}_SDA", "10": "GND_P", "11": f"M{m}_SCL", "12": NC[22 + m - 1]}


set_place([
    # левый край — остров
    ("X1", "JST_XH_B4B-XH-A_L", "B4B-XH-A", 6.0, 16.0, {"1": "Net-(FU1-Pad1)", "2": "Net-(XS2-IO2)", "3": "Net-(R8-Pad1)", "4": "GND_L"}),
    ("FU1", "Fuse_PTC_Radial_P5.08mm", "polyfuse 1 А", 16.0, 8.0, {"1": "Net-(FU1-Pad1)", "2": "+5V_L"}),
    ("R8", "R_Axial_P10.16mm_V", "10 кОм", 28.0, 24.0, {"1": "Net-(R8-Pad1)", "2": "Net-(XS2-IO1)"}),
    ("R9", "R_Axial_P10.16mm_V", "20 кОм", 28.0, 39.0, {"1": "Net-(XS2-IO1)", "2": "GND_L"}),
    ("X5", "JST_VH_B2P-VH_L", "B2P-VH", 6.0, 30.0, {"1": "+5V_L", "2": "GND_L"}),
    ("C1", "C_Disc_P5.00mm", "100 нФ", 14.5, 33.0, {"1": "Net-(XS2-IO48)", "2": "GND_L"}),
    ("X4", "JST_XH_B2B-XH-A_L", "B2B-XH-A", 6.0, 41.0, {"1": "Net-(XS2-IO48)", "2": "GND_L"}),
    ("R7", "R_Axial_P10.16mm_V", "10 кОм", 17.0, 44.0, {"1": "3V3", "2": "Net-(XS2-IO48)"}),
    ("R6", "R_Axial_P10.16mm_V", "10 кОм", 11.0, 52.0, {"1": "3V3", "2": "Net-(U2-OUT)"}),
    # левый край — силовой угол (+5P / GND_P / KH)
    ("U2", "DIP-6_W7.62mm_H", "КР293КП2Б", 14.0, 64.0, {"1": "Net-(R5-Pad1)", "2": "GND_P", "3": NC[20], "4": "Net-(U2-OUT)", "5": NC[21], "6": "GND_L"}),
    ("R5", "R_Axial_P10.16mm_V", "470 Ом", 13.5, 76.0, {"1": "Net-(R5-Pad1)", "2": "KH"}),
    ("X2", "JST_VH_B2P-VH_L", "B2P-VH", 6.0, 76.0, {"1": "+5P", "2": "GND_P"}),
    ("R4", "R_Axial_P10.16mm_V", "1 кОм", 18.0, 82.0, {"1": "KH", "2": "GND_P"}),
    ("X3", "JST_XH_B4B-XH-A_L", "B4B-XH-A", 6.0, 88.0, {"1": "+5P", "2": "KH", "3": "KH", "4": "GND_P"}),
    # модуль ESP32
    ("XS1", "PinSocket_1x22_P2.54mm_Vertical", "PBS-22", XS1_X, XS_Y, J1),
    ("XS2", "PinSocket_1x22_P2.54mm_Vertical", "PBS-22", XS2_X, XS_Y, J3),
    # мультиплексор и подтяжки, LR
    ("U1", "Module_CJMCU-9548", "CJMCU-9548", 85.0, 22.0, U1N),
    ("R1", "R_Axial_P10.16mm", "4,7 кОм", 85.0, 44.0, {"1": "3V3", "2": "SDA"}),
    ("R2", "R_Axial_P10.16mm", "4,7 кОм", 85.0, 48.0, {"1": "3V3", "2": "SCL"}),
    ("R3", "R_Axial_P10.16mm", "10 кОм", 85.0, 52.0, {"1": "3V3", "2": "MUX-RST"}),
    ("X10", "JST_XH_B4B-XH-A_R", "B4B-XH-A", 114.0, 52.0, {"1": "3V3", "2": "SCL", "3": "SDA", "4": "GND_L"}),
    # разъёмы CH1…CH4
    ("X6", "IDC-Header_2x06_P2.54mm_Vertical", "BH-12", CH_X[0], CH_Y, ch_nets(1)),
    ("X7", "IDC-Header_2x06_P2.54mm_Vertical", "BH-12", CH_X[1], CH_Y, ch_nets(2)),
    ("X8", "IDC-Header_2x06_P2.54mm_Vertical", "BH-12", CH_X[2], CH_Y, ch_nets(3)),
    ("X9", "IDC-Header_2x06_P2.54mm_Vertical", "BH-12", CH_X[3], CH_Y, ch_nets(4)),
])

HOLES.extend([(4, 4), (116, 4), (4, 56), (116, 78)])
MODULE = (32.7, 3.3, 60.7, 66.0)              # контур модуля YD-ESP32-S3 (62,74 × 28) над гнёздами
P_CORNER = [(1, 62.0), (20.5, 62.0), (20.5, 101), (1, 101)]   # силовой угол GND_P

# ---- трассировка -----------------------------------------------------------------------------------------
# GND_L — зона B.Cu (все площадки GND_L — в зоне), GND_P — зона F.Cu в силовом углу + дорожка вдоль нижнего края.
ROUTER_STRATEGY = "hv"        # "hv" — F.Cu горизонтали / B.Cu вертикали; "plane" — сигналы по F.Cu, B.Cu под землю
rt = Router(w_default=1.0, strategy=ROUTER_STRATEGY)


def pads_of(net):
    out = []
    for ref, fpname, value, x0, y0, nets in PLACE:
        for num, n in nets.items():
            if n == net:
                out.append(pad(ref, num))
    return out


ORDER = [   # (цепь, ширина, порядок площадок — первая уже «есть», остальные подключаются по очереди)
    ("Net-(FU1-Pad1)", 0.8, None), ("Net-(XS2-IO2)", 0.8, None), ("Net-(XS2-IO1)", 0.8, None),
    ("Net-(R5-Pad1)", 0.8, None), ("Net-(U2-OUT)", 0.8, None), ("Net-(XS2-IO48)", 0.8, None),
    ("M1_CURR", 0.8, None), ("M1_RELE", 0.8, None), ("M1_IN1", 0.8, None), ("M1_IN2", 0.8, None),
    ("M2_CURR", 0.8, None), ("M2_RELE", 0.8, None), ("M2_IN1", 0.8, None), ("M2_IN2", 0.8, None),
    ("M3_CURR", 0.8, None), ("M3_RELE", 0.8, None), ("M3_IN1", 0.8, None), ("M3_IN2", 0.8, None),
    ("M4_CURR", 0.8, None), ("M4_RELE", 0.8, None), ("M4_IN1", 0.8, None), ("M4_IN2", 0.8, None),
    ("M1_SDA", 0.8, None), ("M1_SCL", 0.8, None), ("M2_SDA", 0.8, None), ("M2_SCL", 0.8, None),
    ("M3_SDA", 0.8, None), ("M3_SCL", 0.8, None), ("M4_SDA", 0.8, None), ("M4_SCL", 0.8, None),
    ("MUX-RST", 0.8, None), ("MUX-A0", 0.8, None), ("MUX-A1", 0.8, None),
    ("SDA", 0.8, None), ("SCL", 0.8, None),
    ("Net-(R8-Pad1)", 0.8, None), ("KH", 0.8, None), ("+5P", 1.0, None), ("GND_P", 1.0, None), ("+5V_L", 1.0, None), ("3V3", 0.8, None),
]
for net, w, order in ORDER:
    pts = order or pads_of(net)
    # порядок: начинаем с самой верхней-левой площадки, дальше — ближайшая к уже соединённым
    pts = sorted(pts, key=lambda p: (p[1], p[0]))
    chain = [pts[0]]; rest = pts[1:]
    while rest:
        nxt = min(rest, key=lambda p: min(math.hypot(p[0] - q[0], p[1] - q[1]) for q in chain))
        chain.append(nxt); rest.remove(nxt)
    rt.route(net, chain, w)
FAILED = rt.fail

ZONES.update({
    "GND_L": ("GND_L", B, [(1, 1), (119, 1), (119, 101), (21.5, 101), (21.5, 61.0), (1, 61.0)], "copper"),
    "GND_P": ("GND_P", F, P_CORNER, "copper"),
})
ISLAND = set()
POWER_ZONE = None

# ---- контур, надписи --------------------------------------------------------------------------------------
GR_RECTS.extend([("F.Fab", *MODULE, 0.1), ("F.SilkS", MODULE[0] - 0.2, MODULE[1] - 0.2, MODULE[2] + 0.2, MODULE[3] + 0.2, 0.15)])
ISO_RECTS.append(P_CORNER)
TEXTS.extend([("Манипулятор учебный — плата MC rev A1", 70, 70.5, 1.2),
              ("A1: YD-ESP32-S3, антенна ↑, USB ↓", 46.7, 1.6, 1.0),
              ("схват", 11.5, 23.5, 1.0), ("+5V_L PS", 12.5, 36.0, 1.0), ("концевик", 11.5, 47.0, 1.0),
              ("+5P PS", 12.5, 82.5, 1.0), ("кнопка KH", 12.5, 94.5, 1.0),
              ("CH1", CH_X[0], 98.5, 1.0), ("CH2", CH_X[1], 98.5, 1.0), ("CH3", CH_X[2], 98.5, 1.0), ("CH4", CH_X[3], 98.5, 1.0),
              ("LR", 108.5, 58.5, 1.0),
              ("ГРАНИЦА РАЗВЯЗКИ: GND_P (угол) / GND_L", 44, 60.0, 1.0)])

# ---- компоновка: функциональные узлы и конструктивная привязка (CLAUDE.md «Компоновка») ------------------
UNITS = {
    "питание логики":        ["X5", "FU1"],
    "вход X1 и делитель":    ["X1", "R8", "R9"],
    "вход IO48":             ["X4", "C1", "R7"],
    "развязка KH":           ["U2", "R5", "R6", "R4", "X2", "X3"],
    "контроллер ESP32":      ["XS1", "XS2"],
    "мультиплексор I2C":     ["U1", "R1", "R2", "R3"],
    "разъём LR":             ["X10"],
    "разъёмы каналов (ряд)": {"refs": ["X6", "X7", "X8", "X9"], "radius": 45.0,
                              "note": "нижний край, одинаковый шаг"},
}
FIXED = {}        # чертёж корпуса/панели не выпущен — требует уточнения
CHANNELS = []     # каналы межузловых трасс — задать при перекомпоновке
MAX_H = None      # ограничение по высоте — требует уточнения по чертежу корпуса

# ---- технологическая доводка (DFM, см. CLAUDE.md «Генерация платы») -------------------------------------
hole_keepouts()      # вырез заливки вокруг крепежа: винт М3 с шайбой не должен касаться меди
chamfer_tracks()     # прямые углы ортогонального Router — под 45°

if __name__ == "__main__":
    write()
    pro_rules([("Default", 0.8, CLR, []), ("Power5", 1.0, CLR, ["+5V_L", "+5P", "GND_P"])])
    if FAILED:
        print("НЕ ПРОЛОЖЕНЫ:", FAILED)

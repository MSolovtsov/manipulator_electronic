#!/usr/bin/env python3
"""Общая часть генераторов схем плат (KiCad 10): помощники s-выражений, библиотека символов по ГОСТ,
размещение символов, провода/узлы/порты, сборка файлов проекта.

Используется gen_<КОД>_sch.py: генератор импортирует модуль, задаёт sc.PROJECT, sc.FOOTPRINTS,
рисует лист функциями place/wire/pwr/…, затем вызывает write_project(...).
Правила — electronics/CLAUDE.md, «Генерация файлов KiCad».
"""
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_LIB = ROOT / "lib" / "symbols" / "manipulator.kicad_sym"
OUT_WKS = ROOT / "lib" / "worksheets" / "gost_portrait.kicad_wks"
WKS_SRC = Path(__file__).resolve().parent / "gost_portrait.kicad_wks"  # рядом со скриптом, если библиотека ещё пуста

SCH_VER = "20260306"
SCH_GEN_VER = "10.0"
LIB_VER = "20251024"     # формат библиотек KiCad 10.0 (снят с файла, сохранённого KiCad 10, 2026-10-03)
LIB_GEN_VER = "10.0"
LIB = "manipulator"
PROJECT = "PS"        # переопределяется генератором
ROOT_UUID = "9d3a5f2c-4b1e-4f0a-8c6d-2e7b1a9f0c11"   # переопределяется генератором (uuid листа)
DATE = "2026-09-17"
OX, OY = 22.86, 0.0   # сдвиг всей схемы: слева рамка ГОСТ с графами занимает 20 мм


def U():
    return str(uuid.uuid4())


FACE = "GOST 2.304"   # ГОСТ 2.304 тип Б (lib/fonts/); курсив — свойство italic
# Высота шрифта по ряду ГОСТ 2.304: основной текст листа 2,5 мм, позиционные обозначения 3,5 мм.
TXT = 2.5   # подписи выводов, номиналы, содержимое и заголовки таблиц, примечания
REF = 3.5   # позиционные обозначения (R1, C1, A1, K1, X1 …)


def font(size=TXT, justify=None):
    j = f" (justify {justify})" if justify else ""
    return f'(effects (font (face "{FACE}") (size {size} {size}) (italic yes)){j})'



def prop(name, value, x, y, rot=0, hide=False, justify=None, size=TXT):
    h = " (hide yes)" if hide else ""
    return f'(property "{name}" "{value}" (at {x} {y} {rot}) (show_name no) (do_not_autoplace no){h} {font(size, justify)})'


# ----------------------------------------------------------------------------
# Библиотека символов (формат KiCad 10 — и внутри схемы, и в .kicad_sym)
# ----------------------------------------------------------------------------
def pin(kind, x, y, ang, num, name="", length=2.54, hide=False):
    h = " (hide yes)" if hide else ""
    # шрифт имени/номера вывода — без face/italic: KiCad 10 их у выводов не хранит и при сохранении отбрасывает
    pf = "(effects (font (size 2.5 2.5)))"
    return (f'(pin {kind} line (at {x} {y} {ang}) (length {length}){h} '
            f'(name "{name}" {pf}) (number "{num}" {pf}))')


def rect(x1, y1, x2, y2, fill="none", w=0.254):
    return f'(rectangle (start {x1} {y1}) (end {x2} {y2}) (stroke (width {w}) (type default)) (fill (type {fill})))'


def poly(pts, fill="none", w=0.254):
    p = " ".join(f"(xy {x} {y})" for x, y in pts)
    return f'(polyline (pts {p}) (stroke (width {w}) (type default)) (fill (type {fill})))'


def arc(sx, sy, mx, my, ex, ey):
    return f'(arc (start {sx} {sy}) (mid {mx} {my}) (end {ex} {ey}) (stroke (width 0.254) (type default)) (fill (type none)))'


def text(t, x, y, ang=0, size=TXT):
    return f'(text "{t}" (at {x} {y} {ang}) {font(size)})'


def lib_symbol(name, ref, value, graphics, pins, desc, power=False, hide_pin_numbers=False,
               hide_pin_names=False, ref_at=(0, 3.81), val_at=(0, -3.81), val_justify=None, offset=0.508):
    pw = " (power global)" if power else ""
    pn = " (pin_numbers (hide yes))" if hide_pin_numbers else ""
    off = "" if abs(offset - 0.508) < 1e-9 else f" (offset {offset})"   # 0,508 — значение по умолчанию, KiCad его не пишет
    pnames = f'(pin_names{off}{" (hide yes)" if hide_pin_names else ""})' if (off or hide_pin_names) else ""
    body = "\n".join(f"      {g}" for g in graphics)
    pins_s = "\n".join(f"      {p}" for p in pins)
    return f'''  (symbol "{LIB}:{name}"{pw}{pn}{(" " + pnames) if pnames else ""} (exclude_from_sim no) (in_bom yes) (on_board yes) (in_pos_files yes) (duplicate_pin_numbers_are_jumpers no)
    {prop("Reference", ref, ref_at[0], ref_at[1], hide=power)}
    {prop("Value", value, val_at[0], val_at[1], justify=val_justify)}
    {prop("Footprint", "", 0, 0, hide=True)}
    {prop("Datasheet", "", 0, 0, hide=True)}
    {prop("Description", desc, 0, 0, hide=True)}
    (symbol "{name}_0_1"
{body}
    )
    (symbol "{name}_1_1"
{pins_s}
    )
    (embedded_fonts no)
  )'''


def power_rail(name):
    """Шина питания: планка-стрелка вверх (графика power:+24V), скрытый вывод power_in."""
    g = [poly([(-0.762, 1.27), (0, 2.54)], w=0), poly([(0, 2.54), (0.762, 1.27)], w=0), poly([(0, 0), (0, 2.54)], w=0)]
    p = [pin("power_in", 0, 0, 90, "1", name, 0, hide=True)]
    return lib_symbol(name, "#PWR", name, g, p, f"Символ питания: глобальная цепь {name}", power=True,
                      hide_pin_numbers=True, hide_pin_names=True, ref_at=(0, -3.81), val_at=(0, 3.556), offset=0)


def gnd_arrow(name):
    """Земля: стрелка вниз (графика «0В» курсового проекта), скрытый вывод power_in."""
    g = [poly([(-0.635, -1.27), (0, -2.54), (0.635, -1.27)]), poly([(0, 0), (0, -2.54)])]
    p = [pin("power_in", 0, 0, 0, "1", name, 0, hide=True)]
    return lib_symbol(name, "#PWR", name, g, p, f"Символ земли: глобальная цепь {name}", power=True,
                      hide_pin_numbers=True, hide_pin_names=True, ref_at=(0, 3.81), val_at=(0, -3.81), offset=0)


def sig_arrow(name, right=True):
    """Стрелка-порт сигнала (ГОСТ): вывод в начале, остриё в направлении сигнала, имя рядом."""
    d = 1 if right else -1
    g = [poly([(0, 0), (2.54 * d, 0)]), poly([(1.27 * d, 0.635), (2.54 * d, 0), (1.27 * d, -0.635)])]
    p = [pin("power_in", 0, 0, 0 if right else 180, "1", name, 0, hide=True)]
    return lib_symbol(name, "#PWR", name, g, p, f"Порт сигнала: глобальная цепь {name}", power=True,
                      hide_pin_numbers=True, hide_pin_names=True, ref_at=(0, 3.81),
                      val_at=(3.175 * d, 0), val_justify="left" if right else "right", offset=0)


SYMBOLS = {}

def circ(cx, cy, r, w=0.3048):
    return f'(circle (center {cx} {cy}) (radius {r}) (stroke (width {w}) (type default)) (fill (type none)))'

def dashed_rect(x1, y1, x2, y2):
    return f'(rectangle (start {x1} {y1}) (end {x2} {y2}) (stroke (width 0.1524) (type dash)) (fill (type none)))'

W = 0.3048  # толщина линий УГО (ГОСТ 2.303: линии связи 0,3–0,4; УГО — та же или до 2×)

# ГОСТ 2.728: резистор — прямоугольник 10 × 4 мм
SYMBOLS["R"] = lib_symbol("R", "R", "R", [rect(-2.032, -5.08, 2.032, 5.08, w=W)],
    [pin("passive", 0, 7.62, 270, "1", "", 2.54), pin("passive", 0, -7.62, 90, "2", "", 2.54)],
    "Резистор (ГОСТ 2.728, 10 × 4 мм)", hide_pin_numbers=True, ref_at=(3.175, 1.27), val_at=(3.175, -1.27), val_justify="left", offset=0)

# ГОСТ 2.728: конденсатор — обкладки 8 мм, зазор 1,5 мм
SYMBOLS["C"] = lib_symbol("C", "C", "C",
    [poly([(-4.064, -0.762), (4.064, -0.762)], w=0.508), poly([(-4.064, 0.762), (4.064, 0.762)], w=0.508)],
    [pin("passive", 0, 3.81, 270, "1", "", 3.048), pin("passive", 0, -3.81, 90, "2", "", 3.048)],
    "Конденсатор (ГОСТ 2.728)", hide_pin_numbers=True, ref_at=(5.08, 1.27), val_at=(5.08, -1.27), val_justify="left", offset=0.254)

SYMBOLS["C_Polarized"] = lib_symbol("C_Polarized", "C", "C_Polarized",
    [poly([(-4.064, -0.762), (4.064, -0.762)], w=0.508), poly([(-4.064, 0.762), (4.064, 0.762)], w=0.508),
     poly([(-6.35, 2.286), (-5.08, 2.286)], w=W), poly([(-5.715, 1.651), (-5.715, 2.921)], w=W)],
    [pin("passive", 0, 3.81, 270, "1", "", 3.048), pin("passive", 0, -3.81, 90, "2", "", 3.048)],
    "Конденсатор поляризованный (ГОСТ 2.728), «+» у вывода 1", hide_pin_numbers=True,
    ref_at=(5.08, 1.27), val_at=(5.08, -1.27), val_justify="left", offset=0.254)

# ГОСТ 2.723: катушка индуктивности — полуокружности
SYMBOLS["L"] = lib_symbol("L", "L", "L",
    [arc(-5.08, 0, -3.81, 1.27, -2.54, 0), arc(-2.54, 0, -1.27, 1.27, 0, 0), arc(0, 0, 1.27, 1.27, 2.54, 0), arc(2.54, 0, 3.81, 1.27, 5.08, 0)],
    [pin("passive", -7.62, 0, 0, "1", "", 2.54), pin("passive", 7.62, 0, 180, "2", "", 2.54)],
    "Дроссель (ГОСТ 2.723)", hide_pin_numbers=True, ref_at=(0, 3.81), val_at=(0, -2.54))

# ГОСТ 2.730: диод — треугольник (анод) и черта (катод); вывод 1 — катод, 2 — анод
SYMBOLS["D"] = lib_symbol("D", "VD", "D",
    [poly([(-2.54, 2.032), (-2.54, -2.032)], w=W), poly([(2.54, 2.032), (2.54, -2.032), (-2.54, 0), (2.54, 2.032)], w=W), poly([(-2.54, 0), (2.54, 0)], w=W)],
    [pin("passive", -5.08, 0, 0, "1", "K", 2.54), pin("passive", 5.08, 0, 180, "2", "A", 2.54)],
    "Диод (ГОСТ 2.730): 1 — катод, 2 — анод", hide_pin_numbers=True, hide_pin_names=True, ref_at=(0, 3.81), val_at=(0, -3.81))

# ГОСТ 2.730: диод лавинный / ограничитель напряжения — катодная черта с отогнутыми концами
SYMBOLS["D_TVS"] = lib_symbol("D_TVS", "VD", "D_TVS",
    [poly([(-1.778, 2.032), (-2.54, 2.032), (-2.54, -2.032), (-3.302, -2.032)], w=W),
     poly([(2.54, 2.032), (2.54, -2.032), (-2.54, 0), (2.54, 2.032)], w=W), poly([(-2.54, 0), (2.54, 0)], w=W)],
    [pin("passive", -5.08, 0, 0, "1", "K", 2.54), pin("passive", 5.08, 0, 180, "2", "A", 2.54)],
    "Диод защитный TVS (ГОСТ 2.730): 1 — катод к шине, 2 — анод к земле", hide_pin_numbers=True, hide_pin_names=True, ref_at=(0, 3.81), val_at=(0, -3.81))

# ГОСТ 2.755 / 2.721: XT — соединение разборное (клемма) — кружок; вертикально: 1 — верх (+), 2 — низ (−)
SYMBOLS["Conn_XT2"] = lib_symbol("Conn_XT2", "XT", "Conn_XT2",
    [circ(0, 1.27, 1.016), circ(0, -1.27, 1.016), dashed_rect(-1.651, -2.794, 1.651, 2.794)],
    [pin("passive", 0, 5.08, 270, "1", "1", 2.794), pin("passive", 0, -5.08, 90, "2", "2", 2.794)],
    "Клеммник 2 контакта (ГОСТ 2.755, разборное соединение): 1 — верх, 2 — низ", hide_pin_names=True,
    ref_at=(2.54, 0), val_at=(2.54, -2.54), val_justify="left", offset=1.016)

# ГОСТ 2.755: XP — вилка (штырь) — линия с остриём; вертикально
SYMBOLS["Conn_XP2"] = lib_symbol("Conn_XP2", "XP", "Conn_XP2",
    [poly([(-0.762, 2.286), (0, 0.508), (0.762, 2.286)], w=W), poly([(-0.762, -0.508), (0, -2.286), (0.762, -0.508)], w=W),
     dashed_rect(-1.651, -2.794, 1.651, 2.794)],
    [pin("passive", 0, 5.08, 270, "1", "1", 2.794), pin("passive", 0, -5.08, 90, "2", "2", 2.794)],
    "Вилка на плату, 2 контакта (ГОСТ 2.755, штырь): 1 — верх, 2 — низ", hide_pin_names=True,
    ref_at=(2.54, 0), val_at=(2.54, -2.54), val_justify="left", offset=1.016)

# ГОСТ 2.755: XP — вилка 4 контакта; выводы выходят влево, вывод 1 — верхний
SYMBOLS["Conn_XP4"] = lib_symbol("Conn_XP4", "XP", "Conn_XP4",
    [poly([(-2.032, y + 0.762), (-0.254, y), (-2.032, y - 0.762)], w=W) for y in (7.62, 2.54, -2.54, -7.62)]
    + [dashed_rect(-2.54, -10.16, 2.54, 10.16)],
    [pin("passive", -5.08, 7.62, 0, "1", "1", 2.54), pin("passive", -5.08, 2.54, 0, "2", "2", 2.54),
     pin("passive", -5.08, -2.54, 0, "3", "3", 2.54), pin("passive", -5.08, -7.62, 0, "4", "4", 2.54)],
    "Вилка на плату, 4 контакта (ГОСТ 2.755, штырь): выводы слева, 1 — верхний", hide_pin_names=True,
    ref_at=(3.81, 0), val_at=(3.81, -2.54), val_justify="left", offset=1.016)

# ГОСТ 2.756 (катушка 12 × 6) + 2.755 (переключающий контакт), совмещённый способ; связь — штриховая
SYMBOLS["Relay_SPDT"] = lib_symbol("Relay_SPDT", "K", "Relay_SPDT",
    [rect(-6.35, -3.175, 6.35, 3.175, w=W),
     poly([(-6.35, 8.89), (-2.54, 8.89)], w=W),                       # COM
     poly([(-2.54, 8.89), (3.81, 11.43)], w=W),                        # подвижный контакт (обесточен — на NC)
     poly([(5.08, 11.43), (6.35, 11.43)], w=W), poly([(5.08, 11.43), (5.08, 10.16)], w=W),   # NC
     poly([(5.08, 6.35), (6.35, 6.35)], w=W), poly([(5.08, 6.35), (5.08, 7.62)], w=W),       # NO
     '(polyline (pts (xy 0 3.175) (xy 0 9.525)) (stroke (width 0.1524) (type dash)) (fill (type none)))',
     text("A1", -5.08, -4.445), text("A2", 5.08, -4.445)],
    [pin("passive", -8.89, 0, 0, "1", "A1", 2.54), pin("passive", 8.89, 0, 180, "2", "A2", 2.54),
     pin("passive", -8.89, 8.89, 0, "3", "COM", 2.54), pin("passive", 8.89, 6.35, 180, "4", "NO", 2.54),
     pin("passive", 8.89, 11.43, 180, "5", "NC", 2.54)],
    "Реле, один переключающий контакт (ГОСТ 2.755, 2.756)", hide_pin_names=True, ref_at=(0, -6.35), val_at=(0, -8.89))

# ГОСТ 2.702: покупной модуль — «устройство» прямоугольником с обозначениями выводов
SYMBOLS["DCDC_Module"] = lib_symbol("DCDC_Module", "U", "DCDC_Module",
    [rect(-10.16, -6.35, 10.16, 6.35, w=W), text("DC/DC", 0, 0)],
    [pin("power_in", -12.7, 2.54, 0, "1", "IN+", 2.54), pin("power_in", -12.7, -2.54, 0, "2", "IN-", 2.54),
     pin("power_out", 12.7, 2.54, 180, "3", "OUT+", 2.54), pin("power_out", 12.7, -2.54, 180, "4", "OUT-", 2.54)],
    "Модуль DC-DC понижающего преобразователя (устройство, ГОСТ 2.702)", ref_at=(0, 8.89), val_at=(0, -8.89))

# Mornsun VRB_YMD-10WR3 (DIP 25,4 × 25,4): номера выводов по datasheet 2026.03 — 3 Vin, 2 GND, 4 +Vo, 6 0V, 1 Ctrl (свободен), 5 нет вывода
SYMBOLS["DCDC_VRB_YMD"] = lib_symbol("DCDC_VRB_YMD", "U", "DCDC_VRB_YMD",
    [rect(-10.16, -6.35, 10.16, 6.35, w=W), text("DC/DC", 0, 2.54), text("изолир.", 0, -2.54),
     '(polyline (pts (xy 0 -6.35) (xy 0 6.35)) (stroke (width 0.1524) (type dash)) (fill (type none)))'],
    [pin("power_in", -12.7, 2.54, 0, "3", "Vin", 2.54), pin("power_in", -12.7, -2.54, 0, "2", "GND", 2.54),
     pin("power_out", 12.7, 2.54, 180, "4", "+Vo", 2.54), pin("power_out", 12.7, -2.54, 180, "6", "0V", 2.54),
     pin("input", -5.08, -8.89, 90, "1", "Ctrl", 2.54)],
    "Изолированный DC-DC Mornsun VRB_YMD-10WR3 (устройство, ГОСТ 2.702); выводы по datasheet: 3 Vin, 2 GND, 4 +Vo, 6 0V, 1 Ctrl",
    ref_at=(0, 8.89), val_at=(0, -8.89))

for n in ("+24V_IN", "+24V", "+5P", "+5V_L"):
    SYMBOLS[n] = power_rail(n)
for n in ("GND_P", "GND_L"):
    SYMBOLS[n] = gnd_arrow(n)

# ----------------------------------------------------------------------------
# Схема
# ----------------------------------------------------------------------------
PINS = {
    "R": {"1": (0, 7.62), "2": (0, -7.62)},
    "C": {"1": (0, 3.81), "2": (0, -3.81)},
    "C_Polarized": {"1": (0, 3.81), "2": (0, -3.81)},
    "L": {"1": (-7.62, 0), "2": (7.62, 0)},
    "D": {"1": (-5.08, 0), "2": (5.08, 0)},
    "D_TVS": {"1": (-5.08, 0), "2": (5.08, 0)},
    "Conn_XT2": {"1": (0, 5.08), "2": (0, -5.08)},
    "Conn_XP2": {"1": (0, 5.08), "2": (0, -5.08)},
    "Conn_XP4": {"1": (-5.08, 7.62), "2": (-5.08, 2.54), "3": (-5.08, -2.54), "4": (-5.08, -7.62)},
    "Relay_SPDT": {"1": (-8.89, 0), "2": (8.89, 0), "3": (-8.89, 8.89), "4": (8.89, 6.35), "5": (8.89, 11.43)},
    "DCDC_Module": {"1": (-12.7, 2.54), "2": (-12.7, -2.54), "3": (12.7, 2.54), "4": (12.7, -2.54)},
    "DCDC_VRB_YMD": {"3": (-12.7, 2.54), "2": (-12.7, -2.54), "4": (12.7, 2.54), "6": (12.7, -2.54), "1": (-5.08, -8.89)},
}

items = []
used = set()
pwr_counter = [0]


def r2(v):
    return round(v, 3)


# Footprint каждого компонента (библиотека lib/footprints/manipulator.pretty, генератор gen_PS_pcb.py)
FOOTPRINTS = {
    "XT1": "manipulator:TB_DG301-5.0_2P", "XT2": "manipulator:TB_DG301-5.0_2P_V", "XT3": "manipulator:TB_DG301-5.0_2P_V",
    "XT4": "manipulator:TB_DG301-5.0_2P_V", "XT5": "manipulator:TB_DG301-5.0_2P_V", "XT6": "manipulator:TB_DG301-5.0_2P_V",
    "XP1": "manipulator:JST_XH_B4B-XH-A", "XP4": "manipulator:JST_XH_B2B-XH-A", "XP5": "manipulator:JST_XH_B2B-XH-A",
    "XP2": "manipulator:JST_VH_B2P-VH_V", "XP3": "manipulator:JST_VH_B2P-VH_V",
    "K1": "manipulator:Relay_NRP-15_1C", "VD1": "manipulator:D_SMC", "VD2": "manipulator:D_DO-41_P10.16mm",
    "U1": "manipulator:Module_XL4015E_zone", "U2": "manipulator:DCDC_Mornsun_YMD_25.4x25.4",
    "L1": "manipulator:L_Toroid_D20_P10.16mm", "C1": "manipulator:CP_Radial_D8.0mm_P3.50mm",
    "C2": "manipulator:C_Disc_P5.00mm", "R2": "manipulator:R_Axial_P10.16mm_V",
}
SYM_NS = uuid.UUID("6f1c2b3a-0d4e-4f5a-9b6c-7d8e9f0a1b2c")   # пространство имён uuid символов (стабильны между запусками)


def sym_uuid(ref):
    return str(uuid.uuid5(SYM_NS, f"{PROJECT}:{ref}"))


def place(lib, ref, value, x, y, rot=0, fields=None, ref_off=(2.54, -3.81), val_off=(2.54, 1.27),
          hide_ref=False, hide_val=False, justify="left"):
    """Ставит символ, возвращает {номер вывода: (x, y)} на листе."""
    used.add(lib)
    fields = fields or {}
    pins = PINS.get(lib, {"1": (0, 0)})
    if ref.startswith("#"):
        pwr_counter[0] += 1
        ref = f"{ref}0{pwr_counter[0]:02d}"
    props = [prop("Reference", ref, r2(x + ref_off[0]), r2(y + ref_off[1]), hide=hide_ref, justify=justify, size=REF),
             prop("Value", value, r2(x + val_off[0]), r2(y + val_off[1]), hide=hide_val, justify=justify),
             prop("Footprint", FOOTPRINTS.get(ref, ""), x, y, hide=True), prop("Datasheet", "", x, y, hide=True),
             prop("Description", "", x, y, hide=True)]
    props += [prop(k, v, x, y, hide=True) for k, v in fields.items()]
    pin_s = "\n".join(f'    (pin "{p}" (uuid "{U()}"))' for p in pins)
    ex, ey = r2(x + OX), r2(y + OY)
    props = [p.replace(f"(at {r2(x + ref_off[0])} {r2(y + ref_off[1])} 0)", f"(at {r2(x + ref_off[0] + OX)} {r2(y + ref_off[1] + OY)} 0)", 1)
                 .replace(f"(at {r2(x + val_off[0])} {r2(y + val_off[1])} 0)", f"(at {r2(x + val_off[0] + OX)} {r2(y + val_off[1] + OY)} 0)", 1)
                 .replace(f"(at {x} {y} 0)", f"(at {ex} {ey} 0)", 1) for p in props]
    props_s = "\n".join(f"    {p}" for p in props)
    items.append(
        f'  (symbol (lib_id "{LIB}:{lib}") (at {ex} {ey} {rot}) (unit 1) (body_style 1) (exclude_from_sim no) '
        f'(in_bom yes) (on_board yes) (in_pos_files yes) (dnp no) (uuid "{sym_uuid(ref)}")\n{props_s}\n{pin_s}\n'
        f'    (instances (project "{PROJECT}" (path "/{ROOT_UUID}" (reference "{ref}") (unit 1))))\n  )')
    out = {}
    for n, (px, py) in pins.items():
        if rot == 0:
            out[n] = (r2(x + px), r2(y - py))
        elif rot == 180:
            out[n] = (r2(x - px), r2(y + py))
        else:
            raise ValueError("используются только повороты 0 и 180")
    return out


def pwr(net, x, y, down=False):
    """Символ шины (стрелка вверх) или земли (стрелка вниз) выводом в точке (x, y)."""
    if down:
        place(net, "#PWR", net, x, y, 0, val_off=(0, 3.81), hide_ref=True, justify=None)
    else:
        place(net, "#PWR", net, x, y, 0, val_off=(0, -3.556), hide_ref=True, justify=None)


def wire(a, b):
    items.append(f'  (wire (pts (xy {r2(a[0] + OX)} {r2(a[1] + OY)}) (xy {r2(b[0] + OX)} {r2(b[1] + OY)})) (stroke (width 0.3048) (type default)) (uuid "{U()}"))')


def path(*pts):
    for a, b in zip(pts, pts[1:]):
        wire(a, b)


def note(t, x, y, size=TXT):
    items.append(f'  (text "{t}" (exclude_from_sim no) (at {r2(x + OX)} {r2(y + OY)} 0) (effects (font (face "{FACE}") (size {size} {size}) (italic yes)) (justify left bottom)) (uuid "{U()}"))')


def junction(x, y):
    items.append(f'  (junction (at {r2(x + OX)} {r2(y + OY)}) (diameter 0) (color 0 0 0 0) (uuid "{U()}"))')


def nc(x, y):
    items.append(f'  (no_connect (at {r2(x + OX)} {r2(y + OY)}) (uuid "{U()}"))')


def to_pwr(pin_xy, net, dx=0, dy=0, down=False):
    """Провод от вывода к символу питания в (x+dx, y+dy); сначала по X, потом по Y."""
    px, py = pin_xy
    tx, ty = r2(px + dx), r2(py + dy)
    if dx and dy:
        path((px, py), (tx, py), (tx, ty))
    elif dx or dy:
        wire((px, py), (tx, ty))
    pwr(net, tx, ty, down)
    return (tx, ty)


# ---- символы платы MC: гнёзда модуля ESP32, вилки в столбик, модуль TCA9548, оптореле, предохранитель, порты ------
SYMBOLS["3V3"] = power_rail("3V3")

J1 = ["3V3", "3V3", "RST", "IO4", "IO5", "IO6", "IO7", "IO15", "IO16", "IO17", "IO18",
      "IO8", "IO3", "IO46", "IO9", "IO10", "IO11", "IO12", "IO13", "IO14", "5V", "G"]
J3 = ["G", "TX", "RX", "IO1", "IO2", "IO42", "IO41", "IO40", "IO39", "IO38", "IO37",
      "IO36", "IO35", "IO0", "IO45", "IO48", "IO47", "IO21", "IO20", "IO19", "G", "G"]


def socket_rows(name, rows, left, desc):
    """Гнездовая линейка 2,54 мм (ГОСТ 2.755: гнездо — полукруг) с выводами, сгруппированными по назначению.
    rows — список (ряд, имя вывода, номер контакта); ряд 0 — верхний, шаг 2,54; пустые ряды — зазоры между группами.
    Выводы влево (left) или вправо; номера контактов показаны у выводов, имена (подписи модуля) — внутри корпуса."""
    d = -1 if left else 1
    n_rows = max(r for r, _, _ in rows) + 1
    top = 0.0
    g = [dashed_rect(-6.35, -(n_rows - 1) * 2.54 - 2.54, 6.35, 2.54)]
    pins, pos = [], {}
    for r, lab, num in rows:
        y = round(top - r * 2.54, 2)
        g.append(arc(5.715 * d, y + 0.889, 4.826 * d, y, 5.715 * d, y - 0.889))            # гнездо
        g.append(poly([(5.715 * d, y + 0.889), (5.715 * d, y - 0.889)], w=W))
        pins.append(pin("passive", 8.89 * d, y, 0 if left else 180, str(num), lab, 2.54))
        pos[str(num)] = (8.89 * d, y)
    SYMBOLS[name] = lib_symbol(name, "XS", name, g, pins, desc, ref_at=(0, 5.08), val_at=(0, -(n_rows + 1) * 2.54),
                               offset=2.54)
    PINS[name] = pos


def xp_col(name, n, side="left", ref="XP", pitch=2.54):
    """Вилка n контактов в столбик, вывод 1 сверху; выводы влево (side="left") или вправо."""
    d = -1 if side == "left" else 1
    h = (n - 1) * pitch / 2
    g = [dashed_rect(-2.54, -(h + 2.54), 2.54, h + 2.54)]
    pins, pos = [], {}
    for i in range(n):
        y = round(h - i * pitch, 2)
        g.append(poly([(2.032 * d, y + 0.762), (0.254 * d, y), (2.032 * d, y - 0.762)], w=W))
        pins.append(pin("passive", 5.08 * d, y, 0 if d < 0 else 180, str(i + 1), str(i + 1), 2.54))
        pos[str(i + 1)] = (5.08 * d, y)
    SYMBOLS[name] = lib_symbol(name, ref, name, g, pins,
                               f"Вилка на плату, {n} контактов (ГОСТ 2.755, штырь): выводы {'слева' if d < 0 else 'справа'}, 1 — верхний",
                               hide_pin_names=True, ref_at=(-3.81 * d, 0), val_at=(-3.81 * d, -2.54),
                               val_justify="left" if d > 0 else "right", offset=1.016)
    PINS[name] = pos


xp_col("Conn_XP4_L", 4, "left")
xp_col("Conn_XP2_L", 2, "left")
xp_col("Conn_XP2_R", 2, "right")
xp_col("Conn_XP4_R", 4, "right")

# вилка 2 × 6 (IDC BH-12): нечётные контакты слева, чётные справа, ряд 0 — верхний (нумерация IDC: 1-2, 3-4, …)
_g = [dashed_rect(-3.81, -8.89, 3.81, 8.89)]
_p, _pos = [], {}
for j in range(6):
    y = round(6.35 - j * 2.54, 2)
    for d, num in ((-1, 2 * j + 1), (1, 2 * j + 2)):
        _g.append(poly([(3.556 * d, y + 0.762), (1.778 * d, y), (3.556 * d, y - 0.762)], w=W))
        _p.append(pin("passive", 7.62 * d, y, 0 if d < 0 else 180, str(num), str(num), 2.54)); _pos[str(num)] = (7.62 * d, y)
SYMBOLS["Conn_XP12_2S"] = lib_symbol("Conn_XP12_2S", "XP", "Conn_XP12_2S", _g, _p,
                                       "Вилка 2 × 6 (IDC, 2,54 мм; ГОСТ 2.755, штырь): нечётные контакты слева, чётные справа, 1-2 — верхний ряд",
                                       hide_pin_names=True, ref_at=(0, 11.43), val_at=(0, -11.43), offset=1.016)
PINS["Conn_XP12_2S"] = _pos

# модуль CJMCU-9548 (TCA9548A): слева 8 каналов, справа питание/управление. Порядок и номера выводов — условные,
# по шелкографии модуля сверить (Аккуратно!)
_right = [("1", "VIN"), ("3", "SCL"), ("2", "SDA"), ("4", "RST"), ("5", "A0"), ("6", "A1"), ("7", "A2"), ("8", "GND")]
_left = [(str(9 + i), n) for i, n in enumerate(sum(([f"SD{k}", f"SC{k}"] for k in range(8)), []))]
_g = [rect(-12.7, -22.86, 12.7, 22.86, w=W), text("TCA9548A", 0, 0), text("I2C MUX", 0, -2.54)]
_p, _pos = [], {}
for i, (num, nm) in enumerate(_right):
    y = 17.78 - i * 5.08
    _p.append(pin("power_in" if nm in ("VIN", "GND") else "passive", 15.24, y, 180, num, nm, 2.54)); _pos[num] = (15.24, y)
for i, (num, nm) in enumerate(_left):
    y = round(19.05 - i * 2.54, 2)
    _p.append(pin("passive", -15.24, y, 0, num, nm, 2.54)); _pos[num] = (-15.24, y)
SYMBOLS["Module_TCA9548"] = lib_symbol("Module_TCA9548", "DD", "Module_TCA9548", _g, _p,
                                          "Модуль мультиплексора I2C CJMCU-9548 (TCA9548A/PCA9548A), устройство по ГОСТ 2.702; нумерация выводов условная",
                                          ref_at=(0, 25.4), val_at=(0, -25.4))
PINS["Module_TCA9548"] = _pos

# оптореле КР293КП2Б — по образцу кафедры «оптрон» ГОСТ 2.730 (капсула 30 × 12, выводы вверх/вниз, светодиод слева,
# два указателя излучения, приёмник справа); приёмник — замыкающий контакт ГОСТ 2.755 (у КР293 выход — MOSFET-ключ,
# в ГОСТ 2.730 такого типа оптрона нет). Размеры 30,48 × 12,7 — образец, приведённый к сетке 1,27.
# Выводы: 1 — анод (вверху слева), 2 — катод (внизу слева), 4 и 6 — ключ (справа); номера — по ТУ сверить.
_g = [poly([(-8.89, 6.35), (8.89, 6.35)], w=W), poly([(-8.89, -6.35), (8.89, -6.35)], w=W),                       # капсула
      arc(-8.89, 6.35, -15.24, 0, -8.89, -6.35), arc(8.89, -6.35, 15.24, 0, 8.89, 6.35),
      poly([(-8.89, 6.35), (-8.89, 1.524)], w=W), poly([(-8.89, -1.524), (-8.89, -6.35)], w=W),                   # выводы светодиода
      poly([(-10.414, 1.524), (-7.366, 1.524), (-8.89, -1.524), (-10.414, 1.524)], w=W),                          # треугольник, анод сверху
      poly([(-10.414, -1.524), (-7.366, -1.524)], w=W),                                                          # черта катода
      poly([(-5.08, 1.524), (2.54, 1.524)], w=W), poly([(1.27, 2.159), (2.54, 1.524), (1.27, 0.889)], w=W),      # указатели излучения
      poly([(-5.08, -1.524), (2.54, -1.524)], w=W), poly([(1.27, -0.889), (2.54, -1.524), (1.27, -2.159)], w=W),
      poly([(8.89, 6.35), (8.89, 1.905)], w=W), poly([(8.89, -6.35), (8.89, -1.905), (7.239, 2.413)], w=W)]      # контакт ГОСТ 2.755
_p = [pin("passive", -8.89, 8.89, 270, "1", "A", 2.54), pin("passive", -8.89, -8.89, 90, "2", "K", 2.54),
      pin("passive", 8.89, 8.89, 270, "4", "OUT", 2.54), pin("passive", 8.89, -8.89, 90, "6", "OUT", 2.54)]
SYMBOLS["OptoRelay_KR293"] = lib_symbol("OptoRelay_KR293", "U", "OptoRelay_KR293", _g, _p,
                                           "Оптореле КР293КП2Б: оптрон ГОСТ 2.730 (капсула) с замыкающим контактом ГОСТ 2.755; вход — светодиод 1 (анод), 2 (катод); выход — ключ 4–6; номера выводов сверить по ТУ",
                                           hide_pin_names=True, ref_at=(0, 11.43), val_at=(0, -11.43))
PINS["OptoRelay_KR293"] = {"1": (-8.89, 8.89), "2": (-8.89, -8.89), "4": (8.89, 8.89), "6": (8.89, -8.89)}

# предохранитель (ГОСТ 2.727): прямоугольник 10 × 4 с линией по оси; горизонтально, 1 — слева
SYMBOLS["Fuse"] = lib_symbol("Fuse", "FU", "Fuse", [rect(-5.08, -2.032, 5.08, 2.032, w=W), poly([(-7.62, 0), (7.62, 0)], w=W)],
                                [pin("passive", -7.62, 0, 0, "1", "", 2.54), pin("passive", 7.62, 0, 180, "2", "", 2.54)],
                                "Предохранитель самовосстанавливающийся (ГОСТ 2.727)", hide_pin_numbers=True, ref_at=(0, 3.81), val_at=(0, -3.81))
PINS["Fuse"] = {"1": (-7.62, 0), "2": (7.62, 0)}


# ---- символы платы CH: оптопара 6N137, реле с одним замыкающим контактом, модули DRV8871 и ACS712 ---------------

# 6N137 (DIP-8, нумерация по datasheet Broadcom/Lite-On): 2 — анод, 3 — катод, 5 — GND, 6 — VO, 7 — VE, 8 — VCC;
# выводы 1 и 4 у микросхемы свободны и на схеме не показаны.
# УГО — оптрон по образцу кафедры (ГОСТ 2.730, капсула, светодиод слева, два указателя излучения), приёмник —
# усилитель с логическим выходом (ГОСТ 2.759, треугольник) с выводами питания VCC/GND вверх/вниз и VE справа;
# капсула 40,64 × 15,24 — шире образца, чтобы развести шесть выводов.
_g = [poly([(-12.7, 7.62), (12.7, 7.62)], w=W), poly([(-12.7, -7.62), (12.7, -7.62)], w=W),                       # капсула
      arc(-12.7, 7.62, -20.32, 0, -12.7, -7.62), arc(12.7, -7.62, 20.32, 0, 12.7, 7.62),
      poly([(-12.7, 7.62), (-12.7, 1.524)], w=W), poly([(-12.7, -1.524), (-12.7, -7.62)], w=W),                   # выводы светодиода
      poly([(-14.224, 1.524), (-11.176, 1.524), (-12.7, -1.524), (-14.224, 1.524)], w=W),                          # треугольник, анод сверху
      poly([(-14.224, -1.524), (-11.176, -1.524)], w=W),                                                          # черта катода
      poly([(-8.89, 1.524), (-1.27, 1.524)], w=W), poly([(-2.54, 2.159), (-1.27, 1.524), (-2.54, 0.889)], w=W),   # указатели излучения
      poly([(-8.89, -1.524), (-1.27, -1.524)], w=W), poly([(-2.54, -0.889), (-1.27, -1.524), (-2.54, -2.159)], w=W),
      poly([(2.54, 3.81), (2.54, -3.81), (10.16, 0), (2.54, 3.81)], w=W),                                         # усилитель (ГОСТ 2.759)
      poly([(10.16, 0), (20.32, 0)], w=W),                                                                       # выход VO (6)
      poly([(3.81, 7.62), (3.81, 3.175)], w=W), poly([(3.81, -7.62), (3.81, -3.175)], w=W),                       # VCC (8) сверху, GND (5) снизу
      poly([(20.32, 3.81), (7.62, 3.81), (7.62, 1.27)], w=W)]                                                     # VE (7) справа
_p = [pin("passive", -12.7, 10.16, 270, "2", "A", 2.54), pin("passive", -12.7, -10.16, 90, "3", "K", 2.54),
      pin("power_in", 3.81, 10.16, 270, "8", "VCC", 2.54), pin("power_in", 3.81, -10.16, 90, "5", "GND", 2.54),
      pin("output", 22.86, 0, 180, "6", "VO", 2.54), pin("input", 22.86, 3.81, 180, "7", "VE", 2.54)]
SYMBOLS["Opto_6N137"] = lib_symbol("Opto_6N137", "U", "Opto_6N137", _g, _p,
    "Оптопара 6N137 (DIP-8): оптрон ГОСТ 2.730 с усилителем на выходе; 2 — анод, 3 — катод, 5 — GND, 6 — выход (открытый коллектор), 7 — VE, 8 — VCC; выводы 1, 4 свободны",
    hide_pin_names=True, ref_at=(0, 12.7), val_at=(0, -12.7))
PINS["Opto_6N137"] = {"2": (-12.7, 10.16), "3": (-12.7, -10.16), "8": (3.81, 10.16), "5": (3.81, -10.16),
                      "6": (22.86, 0), "7": (22.86, 3.81)}

# ГОСТ 2.756 + 2.755, совмещённый способ: реле с одним замыкающим контактом (обесточенное положение — разомкнуто)
SYMBOLS["Relay_SPST_NO"] = lib_symbol("Relay_SPST_NO", "K", "Relay_SPST_NO",
    [rect(-6.35, -3.175, 6.35, 3.175, w=W),
     poly([(-6.35, 8.89), (-2.54, 8.89)], w=W),                                            # COM
     poly([(-2.54, 8.89), (3.81, 11.43)], w=W),                                            # подвижный контакт (разомкнут)
     poly([(5.08, 8.89), (6.35, 8.89)], w=W), poly([(5.08, 8.89), (5.08, 10.16)], w=W),    # NO
     '(polyline (pts (xy 0 3.175) (xy 0 9.525)) (stroke (width 0.1524) (type dash)) (fill (type none)))',
     text("A1", -5.08, -4.445), text("A2", 5.08, -4.445)],
    [pin("passive", -8.89, 0, 0, "1", "A1", 2.54), pin("passive", 8.89, 0, 180, "2", "A2", 2.54),
     pin("passive", -8.89, 8.89, 0, "3", "COM", 2.54), pin("passive", 8.89, 8.89, 180, "4", "NO", 2.54)],
    "Реле с одним замыкающим контактом (ГОСТ 2.755, 2.756); нумерация выводов условная, сверить по datasheet",
    hide_pin_names=True, ref_at=(0, -6.35), val_at=(0, -8.89))
PINS["Relay_SPST_NO"] = {"1": (-8.89, 0), "2": (8.89, 0), "3": (-8.89, 8.89), "4": (8.89, 8.89)}

# модуль драйвера ДПТ DRV8871 (устройство по ГОСТ 2.702); нумерация выводов условная — сверить по шелкографии
_g = [rect(-11.43, -10.16, 11.43, 10.16, w=W), text("DRV8871", 0, 2.54), text("драйвер ДПТ", 0, -1.27)]
_p = [pin("input", -13.97, 5.08, 0, "3", "IN1", 2.54), pin("input", -13.97, 0, 0, "4", "IN2", 2.54),
      pin("power_in", 0, 12.7, 270, "1", "VM", 2.54), pin("power_in", 0, -12.7, 90, "2", "GND", 2.54),
      pin("output", 13.97, 5.08, 180, "5", "OUT1", 2.54), pin("output", 13.97, 0, 180, "6", "OUT2", 2.54)]
SYMBOLS["Module_DRV8871"] = lib_symbol("Module_DRV8871", "DA", "Module_DRV8871", _g, _p,
    "Модуль драйвера ДПТ DRV8871 (устройство, ГОСТ 2.702): 1 VM, 2 GND, 3 IN1, 4 IN2, 5 OUT1, 6 OUT2; нумерация условная",
    ref_at=(0, 12.7), val_at=(0, -15.24), offset=0.762)
PINS["Module_DRV8871"] = {"3": (-13.97, 5.08), "4": (-13.97, 0), "1": (0, 12.7), "2": (0, -12.7),
                          "5": (13.97, 5.08), "6": (13.97, 0)}

# модуль датчика тока ACS712-20A: силовая цепь IP+ — IP- проходит насквозь (слева направо), сигнальные выводы снизу;
# штриховая линия — гальваническая развязка внутри микросхемы (2,1 кВ по datasheet Allegro)
_g = [rect(-12.7, -7.62, 12.7, 7.62, w=W), text("ACS712", 0, 3.81), text("20 А", 0, 1.27),
      '(polyline (pts (xy -12.7 -1.27) (xy 12.7 -1.27)) (stroke (width 0.1524) (type dash)) (fill (type none)))',
      poly([(-12.7, 3.81), (12.7, 3.81)], w=W)]
_p = [pin("passive", -15.24, 3.81, 0, "4", "IP+", 2.54), pin("passive", 15.24, 3.81, 180, "5", "IP-", 2.54),
      pin("power_in", -7.62, -10.16, 90, "1", "VCC", 2.54), pin("output", 0, -10.16, 90, "2", "OUT", 2.54),
      pin("power_in", 7.62, -10.16, 90, "3", "GND", 2.54)]
SYMBOLS["Module_ACS712"] = lib_symbol("Module_ACS712", "DA", "Module_ACS712", _g, _p,
    "Модуль датчика тока ACS712-20A (устройство, ГОСТ 2.702): 4 IP+, 5 IP- — измеряемая цепь; 1 VCC, 2 OUT, 3 GND — сигнальная часть; нумерация условная",
    ref_at=(0, 10.16), val_at=(0, -13.97), offset=0.762)
PINS["Module_ACS712"] = {"4": (-15.24, 3.81), "5": (15.24, 3.81), "1": (-7.62, -10.16), "2": (0, -10.16),
                         "3": (7.62, -10.16)}


# то же реле, но зеркально: контакты слева (источники), COM справа (потребитель) — чтобы не поворачивать символ
SYMBOLS["Relay_SPDT_R"] = lib_symbol("Relay_SPDT_R", "K", "Relay_SPDT_R",
    [rect(-6.35, -3.175, 6.35, 3.175, w=W),
     poly([(6.35, 8.89), (2.54, 8.89)], w=W),                                              # COM
     poly([(2.54, 8.89), (-3.81, 11.43)], w=W),                                            # подвижный контакт (на NC)
     poly([(-5.08, 11.43), (-6.35, 11.43)], w=W), poly([(-5.08, 11.43), (-5.08, 10.16)], w=W),   # NC
     poly([(-5.08, 6.35), (-6.35, 6.35)], w=W), poly([(-5.08, 6.35), (-5.08, 7.62)], w=W),       # NO
     '(polyline (pts (xy 0 3.175) (xy 0 9.525)) (stroke (width 0.1524) (type dash)) (fill (type none)))',
     text("A2", -5.08, -4.445), text("A1", 5.08, -4.445)],
    [pin("passive", 8.89, 0, 180, "1", "A1", 2.54), pin("passive", -8.89, 0, 0, "2", "A2", 2.54),
     pin("passive", 8.89, 8.89, 180, "3", "COM", 2.54), pin("passive", -8.89, 6.35, 0, "4", "NO", 2.54),
     pin("passive", -8.89, 11.43, 0, "5", "NC", 2.54)],
    "Реле, один переключающий контакт, зеркальное исполнение (ГОСТ 2.755, 2.756): контакты NC, NO слева, COM справа",
    hide_pin_names=True, ref_at=(0, -6.35), val_at=(0, -8.89))
PINS["Relay_SPDT_R"] = {"1": (8.89, 0), "2": (-8.89, 0), "3": (8.89, 8.89), "4": (-8.89, 6.35), "5": (-8.89, 11.43)}


# ---- символы платы LR: расширитель портов PCF8574, ограничитель BAT54S, двухцветный светодиод ------------------

# PCF8574 в DIP-16 (нумерация по datasheet NXP/TI): 1 A0, 2 A1, 3 A2, 4…7 P0…P3, 8 VSS, 9…12 P4…P7,
# 13 INT, 14 SCL, 15 SDA, 16 VDD
_left = [("4", "P0"), ("5", "P1"), ("6", "P2"), ("7", "P3"), ("9", "P4"), ("10", "P5"), ("11", "P6"), ("12", "P7")]
_right = [("16", "VDD"), ("14", "SCL"), ("15", "SDA"), ("13", "INT"), ("1", "A0"), ("2", "A1"), ("3", "A2"), ("8", "VSS")]
_g = [rect(-10.16, -20.32, 10.16, 20.32, w=W), text("PCF8574", 0, 2.54), text("8 бит I2C", 0, -2.54)]
_p, _pos = [], {}
for _i, (_num, _nm) in enumerate(_left):
    _y = 17.78 - _i * 5.08
    _p.append(pin("passive", -12.7, _y, 0, _num, _nm, 2.54)); _pos[_num] = (-12.7, _y)
for _i, (_num, _nm) in enumerate(_right):
    _y = 17.78 - _i * 5.08
    _k = "power_in" if _nm in ("VDD", "VSS") else "passive"
    _p.append(pin(_k, 12.7, _y, 180, _num, _nm, 2.54)); _pos[_num] = (12.7, _y)
SYMBOLS["IC_PCF8574"] = lib_symbol("IC_PCF8574", "DD", "IC_PCF8574", _g, _p,
    "Расширитель портов PCF8574 (DIP-16, ГОСТ 2.702): 1–3 A0…A2, 4–7 и 9–12 — выходы P0…P7, 8 VSS, 13 INT, 14 SCL, 15 SDA, 16 VDD",
    ref_at=(0, 22.86), val_at=(0, -22.86), offset=0.762)
PINS["IC_PCF8574"] = _pos

# BAT54S (SOT-23, сборка из двух диодов Шоттки последовательно): 3 — общая точка (сигнал), 2 — катод верхнего
# диода (к 3,3 В), 1 — анод нижнего (к земле). Нумерация по datasheet — сверить перед платой
_g = [poly([(-7.62, 0), (-2.54, 0)], w=W), poly([(-2.54, -3.81), (-2.54, 3.81)], w=W),
      poly([(-1.27, 2.54), (-1.27, 5.08), (1.27, 3.81), (-1.27, 2.54)], w=W), poly([(1.27, 2.54), (1.27, 5.08)], w=W),
      poly([(1.27, 3.81), (7.62, 3.81)], w=W), poly([(-2.54, 3.81), (-1.27, 3.81)], w=W),
      poly([(1.27, -2.54), (1.27, -5.08), (-1.27, -3.81), (1.27, -2.54)], w=W), poly([(-1.27, -2.54), (-1.27, -5.08)], w=W),
      poly([(1.27, -3.81), (7.62, -3.81)], w=W), poly([(-2.54, -3.81), (-1.27, -3.81)], w=W)]
_p = [pin("passive", -10.16, 0, 0, "3", "IN", 2.54), pin("passive", 10.16, 3.81, 180, "2", "K", 2.54),
      pin("passive", 10.16, -3.81, 180, "1", "A", 2.54)]
SYMBOLS["D_BAT54S"] = lib_symbol("D_BAT54S", "VD", "D_BAT54S", _g, _p,
    "Сборка BAT54S (ГОСТ 2.730): ограничитель сигнала на шины; 3 — сигнал, 2 — к 3,3 В, 1 — к земле; нумерация по datasheet, сверить",
    hide_pin_names=True, ref_at=(0, 7.62), val_at=(0, -7.62))
PINS["D_BAT54S"] = {"3": (-10.16, 0), "2": (10.16, 3.81), "1": (10.16, -3.81)}

# Светодиод двухцветный с общим анодом (3 вывода): 1 — анод (сверху), 2 и 3 — катоды (снизу)
_g = [poly([(0, 7.62), (0, 3.81)], w=W),
      poly([(-2.54, 3.81), (2.54, 3.81)], w=W),
      poly([(-4.445, 0.0), (-0.635, 0.0), (-2.54, -2.54), (-4.445, 0.0)], w=W), poly([(-4.445, -2.54), (-0.635, -2.54)], w=W),
      poly([(-2.54, 3.81), (-2.54, 0.0)], w=W), poly([(-2.54, -2.54), (-2.54, -7.62)], w=W),
      poly([(0.635, 0.0), (4.445, 0.0), (2.54, -2.54), (0.635, 0.0)], w=W), poly([(0.635, -2.54), (4.445, -2.54)], w=W),
      poly([(2.54, 3.81), (2.54, 0.0)], w=W), poly([(2.54, -2.54), (2.54, -7.62)], w=W),
      poly([(-5.715, 2.54), (-4.445, 3.81)], w=W), poly([(-4.445, 3.81), (-5.08, 3.175)], w=W),
      poly([(4.445, 2.54), (5.715, 3.81)], w=W), poly([(5.715, 3.81), (5.08, 3.175)], w=W)]
_p = [pin("passive", 0, 10.16, 270, "1", "A", 2.54), pin("passive", -2.54, -10.16, 90, "2", "K1", 2.54),
      pin("passive", 2.54, -10.16, 90, "3", "K2", 2.54)]
SYMBOLS["LED_Bicolor_CA"] = lib_symbol("LED_Bicolor_CA", "HL", "LED_Bicolor_CA", _g, _p,
    "Светодиод двухцветный с общим анодом (ГОСТ 2.730): 1 — анод, 2 — катод зелёного, 3 — катод красного; цоколёвку сверить",
    hide_pin_names=True, ref_at=(6.35, 5.08), val_at=(6.35, 2.54), val_justify="left")
PINS["LED_Bicolor_CA"] = {"1": (0, 10.16), "2": (-2.54, -10.16), "3": (2.54, -10.16)}


def port(net, x, y, wire_dir, incoming):
    """Стрелка-порт цепи net выводом в (x, y). wire_dir — с какой стороны от порта идёт провод (+1 — справа,
    −1 — слева); графика и имя — с противоположной стороны. incoming — сигнал приходит в узел: остриё у вывода,
    смотрит в сторону провода; иначе остриё на дальнем конце (сигнал уходит от узла)."""
    g_dir = -wire_dir
    key = f"SIG_{net}_{'R' if g_dir > 0 else 'L'}_{'in' if incoming else 'out'}"
    if key not in SYMBOLS:
        far = 2.54 * g_dir
        if incoming:                     # остриё в (0, 0), хвост в far
            g = [poly([(far, 0), (0, 0)]), poly([(far / 2, 0.635), (0, 0), (far / 2, -0.635)])]
        else:                            # хвост в (0, 0), остриё в far
            g = [poly([(0, 0), (far, 0)]), poly([(far / 2, 0.635), (far, 0), (far / 2, -0.635)])]
        just = "left" if g_dir > 0 else "right"
        p = [pin("power_in", 0, 0, 0, "1", net, 0, hide=True)]
        SYMBOLS[key] = lib_symbol(key, "#PWR", net, g, p, f"Порт сигнала: глобальная цепь {net}", power=True,
                                     hide_pin_numbers=True, hide_pin_names=True, ref_at=(0, 3.81), val_at=(3.175 * g_dir, 0),
                                     val_justify=just, offset=0)
        PINS[key] = {"1": (0, 0)}
    place(key, "#PWR", net, x, y, 0, val_off=(3.175 * g_dir, 0), hide_ref=True, justify="left" if g_dir > 0 else "right")


def rail_up(net, x, y):
    pwr(net, x, y)


def gnd_dn(net, x, y):
    pwr(net, x, y, down=True)



# ---- разъём таблицей (ГОСТ 2.702, стиль курсового проекта кафедры): колонки «Контакт» и «Цепь», строка на контакт,
# обозначение X под таблицей слева; выводы — со стороны, обращённой к схеме ----------------------------------------
COL_N, COL_NET, ROW = 17.78, 20.32, 5.08     # ширина колонок и шаг строк (кегль 2,5 мм: «Контакт» ~16,6 мм)
TBL_W = COL_N + COL_NET


def conn_table(name, nets, side="left"):
    """Символ разъёма-таблицы с выводами слева (side="left") или справа. nets — тексты колонки «Цепь» по строкам
    (номера контактов 1…n; "" — контакт не используется). Вывод i — на строке i; строка 1 — вверху (y = 0),
    шапка — над ней. Колонка «Контакт» — со стороны выводов."""
    d = -1 if side == "left" else 1                       # сторона выводов
    n = len(nets)
    x0 = 0.0                                              # край таблицы со стороны выводов
    x1 = -d * TBL_W                                       # дальний край
    xc = -d * COL_N                                       # граница колонок
    y_top = ROW + ROW / 2                                 # верх шапки
    y_bot = -(n - 1) * ROW - ROW / 2
    w = 0.1524
    g = [poly([(x0, y_top), (x1, y_top), (x1, y_bot), (x0, y_bot), (x0, y_top)], w=w),
         poly([(xc, y_top), (xc, y_bot)], w=w)]
    for i in range(n + 1):
        y = ROW / 2 - i * ROW
        g.append(poly([(x0, y), (x1, y)], w=w))
    xn, xnet = -d * COL_N / 2, -d * (COL_N + COL_NET / 2)
    g += [text("Контакт", xn, ROW), text("Цепь", xnet, ROW)]
    pins, pos = [], {}
    for i, net in enumerate(nets, 1):
        y = round(-(i - 1) * ROW, 2)
        g.append(text(str(i), xn, y))
        if net:
            g.append(text(net, xnet, y))
        pins.append(pin("passive", d * 2.54, y, 0 if d < 0 else 180, str(i), net or "-", 2.54))
        pos[str(i)] = (d * 2.54, y)
    SYMBOLS[name] = lib_symbol(name, "X", name, g, pins,
                               f"Разъём, {n} контактов, таблицей (ГОСТ 2.702): колонки «Контакт», «Цепь»; выводы {'слева' if d < 0 else 'справа'}",
                               hide_pin_numbers=True, hide_pin_names=True, ref_at=(x1 if d > 0 else x0, y_bot - 2.0),
                               val_at=(0, y_bot - 4.5), offset=0)
    PINS[name] = pos


def xtable(ref, nets, x, y, side, base, purpose, value, status="Утверждено"):
    """Ставит разъём-таблицу ref (X…) с выводом 1 в точке (x, y); nets — колонка «Цепь». Возвращает {контакт: (x, y)}.
    Обозначение — под таблицей у левого края; Value (тип) скрыт — тип виден в перечне элементов."""
    name = f"Tbl_{ref}_{PROJECT}"
    conn_table(name, nets, side)
    d = -1 if side == "left" else 1
    n = len(nets)
    y_bot = -(n - 1) * ROW - ROW / 2
    x_left = (0 if d < 0 else -TBL_W) - d * 2.54            # левый край таблицы относительно вывода 1
    return place(name, ref, value, x - d * 2.54, y, 0, {"BaseID": base, "Status": status, "Назначение": purpose},
                 ref_off=(x_left + 0.5, -y_bot + 1.9), val_off=(x_left, -y_bot + 4.5), hide_val=True, justify="left")


def table(ref, nets, x, y, side, base, purpose, value, status="Предложение"):
    """xtable + запоминает сторону выводов (для tport)."""
    P = xtable(ref, nets, x, y, side, base, purpose, value, status); P["side"] = side
    return P


def tport(P, n, net, incoming):
    """Стрелка-порт цепи net на контакте n таблицы P: провод 5,08 мм от вывода, остриё — по направлению сигнала
    (incoming — в разъём). Порт стоит со стороны выводов таблицы."""
    x, y = P[n]
    d = -1 if P["side"] == "left" else 1
    xp = r2(x + 5.08 * d)
    wire((min(x, xp), y), (max(x, xp), y))
    port(net, xp, y, wire_dir=-d, incoming=incoming)


# ---- общие помощники компоновки ---------------------------------------------------------------
def conn(ref, x, y, base, purpose, value, status="Утверждено", pins=2, sym=None):
    """Вертикальный разъём: XT — клеммник, XP — вилка, XS — гнездо (ГОСТ 2.710). Value скрыт.
    pins=4 — вилка с выводами влево (Conn_XP4); sym — явное имя символа."""
    if sym is None:
        sym = "Conn_XT2" if ref.startswith("XT") else ("Conn_XP4" if pins == 4 else "Conn_XP2")
    ro = 3.81 if pins == 4 else 2.54
    return place(sym, ref, value, x, y, 0,
                 {"BaseID": base, "Status": status, "Назначение": purpose},
                 ref_off=(ro, 0.0), val_off=(ro, 2.54), hide_val=True)


def tap(pin_xy, y_line, taps, via_x=None):
    """Отвод от вывода к горизонтальной линии y_line (при via_x — сначала по X). Регистрирует узел."""
    x = pin_xy[0] if via_x is None else via_x
    if via_x is not None:
        wire(pin_xy, (via_x, pin_xy[1]))
    wire((x, pin_xy[1]), (x, y_line)); taps.append(x)


def hline(y, taps, x_from, x_to):
    """Горизонтальная линия от x_from до x_to, разбитая в точках отводов; junction в каждом отводе."""
    pts = sorted(set([r2(v) for v in taps if x_from - 1e-6 <= v <= x_to + 1e-6] + [r2(x_from), r2(x_to)]))
    for a, b in zip(pts, pts[1:]):
        wire((a, y), (b, y))
    for v in taps:
        if x_from + 1e-6 < v < x_to - 1e-6:
            junction(r2(v), y)


def vline(x, taps_y, y_from, y_to):
    pts = sorted(set([r2(v) for v in taps_y] + [r2(y_from), r2(y_to)]))
    for a, b in zip(pts, pts[1:]):
        wire((x, a), (x, b))
    for v in taps_y:
        if min(y_from, y_to) + 1e-6 < v < max(y_from, y_to) - 1e-6:
            junction(x, r2(v))


def sig(net, x, y, right=True):
    """Стрелка-порт сигнала с именем цепи выводом в точке (x, y); остриё вправо или влево."""
    if net not in SYMBOLS:
        SYMBOLS[net] = sig_arrow(net, right)
    place(net, "#PWR", net, x, y, 0, val_off=(3.175 if right else -3.175, 0), hide_ref=True,
          justify="left" if right else "right")


# ---- сборка файлов проекта ----------------------------------------------------------------------------
import re


def _clean_numbers(text):
    """Числа в s-выражениях — как их пишет KiCad: без хвостов двоичного представления (…000001) и без «.0»."""
    def f(m):
        v = round(float(m.group(0)), 4)
        return str(int(v)) if v == int(v) else repr(v)
    parts = text.split('"')                       # чётные части — вне кавычек; строки не трогаем
    for i in range(0, len(parts), 2):
        parts[i] = re.sub(r'(?<=[ (])-?\d+\.\d+(?=[ )])', f, parts[i])
    return '"'.join(parts)


def to_lib(sym):
    """Символ для файла библиотеки KiCad 10: тот же текст, что в lib_symbols схемы, без префикса библиотеки."""
    return sym.replace(f'"{LIB}:', '"', 1)


def _top_symbols(text):
    """Блоки (symbol "имя" …) верхнего уровня из текста библиотеки любой разметки (генератор или KiCad):
    скобки считаются с учётом кавычек. Возвращает {имя: исходный текст блока}."""
    out, i, n = {}, 0, len(text)
    while True:
        j = text.find('(symbol "', i)
        if j < 0:
            break
        depth, k, q = 0, j, False
        while k < n:
            c = text[k]
            if q:
                if c == '\\': k += 1
                elif c == '"': q = False
            elif c == '"': q = True
            elif c == '(': depth += 1
            elif c == ')':
                depth -= 1
                if depth == 0:
                    break
            k += 1
        block = text[j:k + 1]
        name = re.match(r'\(symbol "([^"]+)"', block).group(1)
        # вложенные (symbol "X_0_1") пропускаем: они внутри блока верхнего уровня
        if ':' not in name and not re.search(r'_\d+_\d+$', name):
            out[name] = block
        i = k + 1
    return out


def sch_text(paper, title_block):
    """Текст .kicad_sch: title_block — словарь title/date/rev/company/comment1..6."""
    lib_symbols_sch = "\n".join(SYMBOLS[n] for n in sorted(used))
    tb = "\n".join([f'    (title "{title_block["title"]}")', f'    (date "{title_block.get("date", DATE)}")',
                    f'    (rev "{title_block["rev"]}")', f'    (company "{title_block.get("company", "МГТУ им. Н.Э. Баумана, группа СМ7-21М")}")'] +
                   [f'    (comment {i} "{title_block.get(f"comment{i}", "---")}")' for i in range(1, 7)])
    return _clean_numbers(f'(kicad_sch (version {SCH_VER}) (generator "eeschema") (generator_version "{SCH_GEN_VER}")\n'
            f'  (uuid "{ROOT_UUID}")\n  (paper "{paper}")\n  (title_block\n{tb}\n  )\n  (lib_symbols\n{lib_symbols_sch}\n  )\n'
            + "\n".join(items) + '\n  (sheet_instances (path "/" (page "1")))\n  (embedded_fonts no)\n)\n')


def lib_text():
    """Библиотека — объединение: символы этого генератора + символы из файла, которые использует схема другой
    платы (порты/таблицы создаются каждым генератором отдельно; неиспользуемые символы отбрасываются).
    Формат — KiCad 10 (LIB_VER); KiCad при сохранении лишь переразмечает отступы."""
    syms = {n: "  " + to_lib(SYMBOLS[n]).strip() for n in SYMBOLS}
    used_elsewhere = set()
    for sch in (ROOT / "boards").glob("*/*.kicad_sch"):
        if sch.stem != PROJECT:
            used_elsewhere |= set(re.findall(rf'\(lib_id "{LIB}:([^"]+)"\)', sch.read_text(encoding="utf-8")))
    if OUT_LIB.exists():
        for name, block in _top_symbols(OUT_LIB.read_text(encoding="utf-8")).items():
            if name in used_elsewhere:
                syms.setdefault(name, "  " + re.sub(r"\n\t*", "\n    ", block.strip()))
    return _clean_numbers(f'(kicad_symbol_lib (version {LIB_VER}) (generator "kicad_symbol_editor") (generator_version "{LIB_GEN_VER}")\n'
            + "\n".join(syms[n] for n in sorted(syms)) + "\n)\n")


SYM_LIB_TABLE = f'''(sym_lib_table
  (version 7)
  (lib (name "{LIB}")(type "KiCad")(uri "${{KIPRJMOD}}/../../lib/symbols/{LIB}.kicad_sym")(options "")(descr "Общая библиотека символов проекта «Учебный манипулятор»"))
)
'''
FP_LIB_TABLE = f'''(fp_lib_table
  (version 7)
  (lib (name "{LIB}")(type "KiCad")(uri "${{KIPRJMOD}}/../../lib/footprints/{LIB}.pretty")(options "")(descr "Общая библиотека footprint'ов проекта «Учебный манипулятор»"))
)
'''


def pro_text(project):
    return f'''{{
  "meta": {{
    "filename": "{project}.kicad_pro",
    "version": 3
  }},
  "erc": {{
    "rule_severities": {{
      "power_pin_not_driven": "ignore"
    }}
  }},
  "schematic": {{
    "page_layout_descr_file": "${{KIPRJMOD}}/../../lib/worksheets/gost_portrait.kicad_wks"
  }},
  "sheets": [
    [
      "{ROOT_UUID}",
      "Root"
    ]
  ],
  "text_variables": {{}}
}}
'''


def saved_by_kicad_ok(path):
    """Предохранитель (CLAUDE.md «Главный файл — тот, что сохранил Mikhail в KiCad»): файл с заголовком
    generator "eeschema"/"pcbnew" содержит ручную работу — поверх него генератор не пишет без --force.
    Возвращает True, если писать можно."""
    import sys
    if not path.exists() or "--force" in sys.argv:
        return True
    head = path.read_text(encoding="utf-8", errors="ignore")[:400]
    if '(generator "eeschema")' in head or '(generator "pcbnew")' in head:
        print(f"ОТКАЗ: {path} сохранён KiCad (ручная компоновка Mikhail) — генератор поверх не пишет.\n"
              f"       Правки вносятся точечно в файл; перегенерация — только по команде: добавьте --force,\n"
              f"       предварительно отложив копию файла вне репозитория.")
        return False
    return True


def write_project(project, paper, title_block, write_pro=True):
    """Записать boards/<project>/*.kicad_sch (+ .kicad_pro и таблицы, если их нет) и общую библиотеку символов.
    Библиотека пишется полностью (все символы всех плат), поэтому генераторы должны импортировать общий модуль."""
    board = ROOT / "boards" / project
    board.mkdir(parents=True, exist_ok=True)
    OUT_LIB.parent.mkdir(parents=True, exist_ok=True)
    out_sch = board / f"{project}.kicad_sch"
    if not saved_by_kicad_ok(out_sch):
        return
    out_sch.write_text(sch_text(paper, title_block), encoding="utf-8")
    if write_pro and not (board / f"{project}.kicad_pro").exists():
        (board / f"{project}.kicad_pro").write_text(pro_text(project), encoding="utf-8")
    for name, text_ in (("sym-lib-table", SYM_LIB_TABLE), ("fp-lib-table", FP_LIB_TABLE)):
        if not (board / name).exists():
            (board / name).write_text(text_, encoding="utf-8")
    OUT_LIB.write_text(lib_text(), encoding="utf-8")
    if not OUT_WKS.exists() and WKS_SRC.exists():
        OUT_WKS.parent.mkdir(parents=True, exist_ok=True)
        OUT_WKS.write_bytes(WKS_SRC.read_bytes())
    print(f"{project}.kicad_sch: {len(items)} элементов; {len(used)} символов из библиотеки")

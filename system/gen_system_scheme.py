#!/usr/bin/env python3
"""Функциональная схема стенда, лист Э2 (A2, ГОСТ, шрифт GOST 2.304).

Геометрия и подписи хранятся рядом в functional_scheme.json (дамп листа),
правки задаются списками EDIT_TEXT / ADD_TEXT ниже. PDF руками не править —
менять этот файл и перегенерировать из корня репозитория:

    python3 system/gen_system_scheme.py

Полные правила оформления листа — в скилле create-func-scheme.
Шрифт: положить TTF из lib/fonts/ в ~/.fonts и выполнить fc-cache -f.

Цвет подписи: чёрный — решение утверждено, красный (0xC00000) — не утверждено
(см. легенду на листе). Статусы берутся из bom/Component_Base.xlsx.
"""
import json, math, re, sys
from pathlib import Path
import cairo

BLACK, RED = 0x000000, 0xC00000

# ── правки к дампу: индекс подписи -> что заменить ───────────────────────────
# cx — новый центр по X (если подпись центрируется в блоке)
EDIT_TEXT = {
    # двигатель утверждён 19.09.2026 (E-041), модель по каталогу nfpshop
    73: dict(t="Мотор-редуктор",  cx=1300.7),
    74: dict(t="5840-31ZY-DSH",   cx=1300.7),
    75: dict(t="24 В, i = 670",   cx=1300.7, color=BLACK),
    # механическая передача — без подробностей
    76: dict(t="Механическая передача", cx=1478.3, size=13.32, y=230.0),
    77: dict(t=""),
    # электроника схвата — коротко
    89: dict(t="Электроника схвата М5", cx=1491.0, y=684.5),
    90: dict(t=""),
    91: dict(t="контроллер --- (13)",   cx=1491.0, y=699.3),
    # силовая часть утверждена вместе с двигателем: метки (6), (7), (9) сняты
    66: dict(t=""),
    69: dict(t=""),
    72: dict(t=""),
    132: dict(t="Ток →ADC ESP32 (делитель 10 к + 20 к); ОС по току, «режим безопасности»",
              color=BLACK),
    # клеммы ЛР согласованы 19.09.2026 (E-051)
    85: dict(t=""),
    # токосъёмное кольцо: требование известно, изделие не выбрано
    53: dict(t="Токосъёмное кольцо не менее 5 А --- (16)"),
    57: dict(t="— питание ДПТ M2…M4 (3 двигателя × 1,2 А ном.; кольцо не менее 5 А);"),
    # подпись раздачи +5P — по центру своей стрелки (x = 942,4)
    119: dict(cx=879.0, y=720.0),
    120: dict(cx=879.0, y=731.0),
    121: dict(cx=879.0, y=742.0),
    # перекомпоновка узла +5P: XL4015E поднят над магистралью +24
    105: dict(cx=879.0, y=803.0),
    106: dict(cx=879.0, y=819.0),
    111: dict(t=""),                       # «+24 →остров» — магистраль теперь прямая
    # E-091 и E-073 утверждены 20.09.2026 — метки сняты
    50: dict(t="вход ESP32, GPIO48", color=BLACK),
    # редакция листа
    19: dict(t="Редакция 11; доска Miro + решения 13–19.09.2026"),
    152: dict(t="чёрным — утверждено Mikhail (13–19.09.2026)"),
}

# врезка в линию UART схвата и рамка вокруг подписи раздачи +5P:
# блоки рисуются поверх линий, белая заливка их перекрывает
BOX_X, BOX_W, BOX_CY, BOX_H = 1073.0, 107.7, 685.4, 56.7
P5_X, P5_W, P5_Y, P5_H = 825.1, 107.7, 706.0, 50.0        # подпись раздачи +5P
XL_X, XL_W, XL_Y, XL_H = 825.1, 107.8, 780.0, 57.1        # блок XL4015E над магистралью
AX = XL_X + XL_W / 2                                       # ось отводов (879,0)
BUS_Y = 875.6                                              # магистраль +24

# элементы исходного листа, которые эта компоновка заменяет:
# 100 — прежний блок XL4015E, 170/171 — стрелка реле → XL4015E,
# 113/114 — прежний отвод +5P, 105/106 — прежний обход +24 к изолятору
DEL_DRAW = {100, 105, 106, 113, 114, 170, 171}

def _arrow(x, y, d):
    """наконечник: вылет 7,6 pt, полураствор 4,8 pt; d = "up" или "right"."""
    if d == "up":
        return [["l", [x - 4.8, y + 7.6], [x, y]], ["l", [x, y], [x + 4.8, y + 7.6]]]
    return [["l", [x - 7.6, y - 4.8], [x, y]], ["l", [x, y], [x - 7.6, y + 4.8]]]

def _thin(items):
    return dict(items=items, color=[0.0, 0.0, 0.0], fill=None, width=1.01, dashes=None)
ADD_DRAW = [
    dict(items=[["re", [BOX_X, BOX_CY - BOX_H / 2, BOX_W, BOX_H]]],
         color=[0.0, 0.0, 0.0], fill=[1.0, 1.0, 1.0], width=1.97, dashes=None),
    dict(items=[["re", [P5_X, P5_Y, P5_W, P5_H]]],
         color=[0.0, 0.0, 0.0], fill=[1.0, 1.0, 1.0], width=1.97, dashes=None),
    dict(items=[["re", [XL_X, XL_Y, XL_W, XL_H]]],
         color=[0.0, 0.0, 0.0], fill=[1.0, 1.0, 1.0], width=1.97, dashes=None),
    # магистраль +24 идёт от реле напрямую к изолированному DC-DC
    _thin([["l", [799.7, BUS_Y], [951.9, BUS_Y]]]),
    _thin(_arrow(951.9, BUS_Y, "right")),
    # отвод магистрали вверх на XL4015E и далее раздача +5P
    _thin([["l", [AX, BUS_Y], [AX, XL_Y + XL_H]]]),
    _thin(_arrow(AX, XL_Y + XL_H, "up")),
    _thin([["l", [AX, XL_Y], [AX, P5_Y + P5_H]]]),
    _thin(_arrow(AX, P5_Y + P5_H, "up")),
]

ADD_TEXT = [
    dict(t="Защита ESP-RX",        cx=BOX_X + BOX_W / 2, y=675.2, size=10.78, color=BLACK),
    dict(t="от 5 В схвата",        cx=BOX_X + BOX_W / 2, y=689.2, size=10.78, color=BLACK),
    dict(t="делитель 10 к + 20 к",  cx=BOX_X + BOX_W / 2, y=703.2, size=10.78, color=BLACK),
]


# ── отрисовка ───────────────────────────────────────────────────────────────
def dash_of(s):
    if not s: return []
    n = [float(x) for x in re.findall(r"[\d.]+", str(s))]
    return n[:-1] if len(n) > 1 else []

def main(data_path, out_path):
    d = json.load(open(data_path, encoding="utf-8"))
    surf = cairo.PDFSurface(str(out_path), d["w"], d["h"])
    cr = cairo.Context(surf)
    cr.set_line_cap(cairo.LINE_CAP_BUTT); cr.set_line_join(cairo.LINE_JOIN_MITER)

    for n, dr in enumerate(list(d["draw"]) + ADD_DRAW):
        if n in DEL_DRAW:
            continue
        cur = None
        for it in dr["items"]:
            if it[0] == "l":
                (x1, y1), (x2, y2) = it[1], it[2]
                if cur != (x1, y1): cr.move_to(x1, y1)
                cr.line_to(x2, y2); cur = (x2, y2)
            elif it[0] == "re":
                x, y, w, h = it[1]; cr.rectangle(x, y, w, h); cur = None
            elif it[0] == "c":
                (x1, y1), (a, b), (c, e), (x2, y2) = it[1], it[2], it[3], it[4]
                if cur != (x1, y1): cr.move_to(x1, y1)
                cr.curve_to(a, b, c, e, x2, y2); cur = (x2, y2)
        if dr.get("closePath"): cr.close_path()
        if dr.get("fill"):
            cr.set_source_rgb(*dr["fill"])
            cr.fill_preserve() if dr.get("color") else cr.fill()
        if dr.get("color"):
            cr.set_source_rgb(*dr["color"])
            cr.set_line_width(dr["width"] or 0.3)
            ds = dash_of(dr.get("dashes")); cr.set_dash(ds if ds else [], 0)
            cr.stroke()
        cr.new_path()

    cr.select_font_face("GOST 2.304", cairo.FONT_SLANT_ITALIC, cairo.FONT_WEIGHT_NORMAL)

    def draw_text(t, x, y, size, color, dirv=(1.0, 0.0), cx=None):
        cr.set_font_size(size)
        cr.set_source_rgb(((color >> 16) & 255) / 255, ((color >> 8) & 255) / 255, (color & 255) / 255)
        if cx is not None:
            xb, yb, w, h, dx, dy = cr.text_extents(t)
            x = cx - w / 2 - xb
        cr.save(); cr.translate(x, y)
        if tuple(dirv) == (0.0, -1.0): cr.rotate(-math.pi / 2)
        cr.move_to(0, 0); cr.show_text(t); cr.restore()

    for i, s in enumerate(d["text"]):
        e = EDIT_TEXT.get(i, {})
        draw_text(e.get("t", s["t"]), s["x"], e.get("y", s["y"]),
                  e.get("size", s["size"]), e.get("color", s["color"]),
                  s.get("dir", (1.0, 0.0)), e.get("cx"))
    for a in ADD_TEXT:
        draw_text(a["t"], a.get("x", 0.0), a["y"], a["size"], a["color"],
                  a.get("dir", (1.0, 0.0)), a.get("cx"))

    surf.finish()
    print("записано:", out_path)

if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    main(sys.argv[1] if len(sys.argv) > 1 else here / "functional_scheme.json",
         sys.argv[2] if len(sys.argv) > 2 else here / "functional_scheme_A2_v11.pdf")

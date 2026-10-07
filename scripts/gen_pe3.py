#!/usr/bin/env python3
"""Перечень элементов (ПЭ3) платы <КОД> — PDF по ГОСТ 2.701/2.702, лист A4, рамка по ГОСТ 2.104.

Источники: boards/<КОД>/<КОД>.kicad_sch (позиционные обозначения, значения, BaseID)
и bom/csv/Components.csv (наименования). Обозначение, наименования изделий и подписи —
scripts/doc_titles.py; правила оформления — корневой CLAUDE.md, раздел «Основная надпись».

Графы таблицы (ГОСТ 2.701, форма перечня): Поз. обозначение | Наименование | Кол. | Примечание.
  Наименование — модель из базы; у резисторов и конденсаторов модель не выбрана, поэтому
    пишется номинал и пометка «тип требует уточнения» (ничего не придумывать).
  Примечание — ID позиции в базе компонентов (E-0xx); «—», если позиции в базе нет.
Элементы сгруппированы по видам, группы — по алфавиту, внутри группы — по номеру позиции.
Одинаковые позиции (совпали наименование и примечание) объединяются в одну строку.

Запуск: python3 scripts/gen_pe3.py MC
Результат: docs/<КОД>/Перечень элементов.pdf (в репозиторий не коммитится без команды).
Шрифт: TTF из lib/fonts/ положить в ~/.fonts и выполнить fc-cache -f.
"""
import csv
import re
import sys
from pathlib import Path

import cairo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import doc_titles as dt                     # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CODE = sys.argv[1] if len(sys.argv) > 1 else "MC"

MM = 72 / 25.4
W, H = 210.0, 297.0                          # A4, книжная
FRAME = (20.0, 5.0, W - 5.0, H - 5.0)        # рамка: слева 20, остальные 5
COL = [20.0, 110.0, 10.0, 45.0]              # Поз. обозначение | Наименование | Кол. | Примечание
HEAD_H, ROW_H = 15.0, 8.0
TB1_H, TB2_H = 40.0, 15.0                    # основная надпись: форма 2 (лист 1) и форма 2а
FACE = "GOST 2.304"

# ---- вид элемента по буквенному коду позиционного обозначения (ГОСТ 2.710) --------------------------
GROUPS = [("C", "Конденсаторы"), ("DA", "Микросхемы аналоговые"), ("DD", "Микросхемы цифровые"),
          ("FU", "Предохранители"), ("HL", "Приборы световой сигнализации"), ("K", "Реле"),
          ("L", "Катушки индуктивности"), ("R", "Резисторы"), ("U", "Устройства"),
          ("VD", "Диоды"), ("VT", "Транзисторы"), ("VU", "Оптоэлектронные приборы"),
          ("XS", "Разъёмы"), ("X", "Разъёмы")]


def split_ref(ref):
    m = re.match(r"([A-Za-z]+)(\d+)$", ref)
    return (m.group(1), int(m.group(2))) if m else (ref, 0)


def group_of(ref):
    letters = split_ref(ref)[0]
    for pref, name in GROUPS:                       # XS раньше X: ищем самое длинное совпадение
        if letters == pref:
            return name
    for pref, name in GROUPS:
        if letters.startswith(pref):
            return name
    return "Прочие элементы"


# ---- исходные данные -------------------------------------------------------------------------------
def read_schematic(code):
    s = (ROOT / "boards" / code / f"{code}.kicad_sch").read_text(encoding="utf-8")
    out = []
    for b in s.split("\n\t(symbol\n")[1:]:
        lib = re.search(r'\(lib_id "manipulator:([^"]+)"\)', b)
        if not lib:
            continue
        props = dict(re.findall(r'\(property "([^"]+)" "([^"]*)"', b))
        ref = props.get("Reference", "")
        if ref.startswith("#") or not ref:
            continue
        out.append({"ref": ref, "value": props.get("Value", ""), "base": props.get("BaseID", "").strip()})
    return out


def read_base():
    p = ROOT / "bom" / "csv" / "Components.csv"
    names = {}
    for r in csv.DictReader(p.open(encoding="utf-8-sig")):
        names[r["ID"].strip()] = r["Название"].strip()
    return names


GLYPH_FIX = {"\u2300": "\u00d8"}                   # в шрифте нет ⌀ (U+2300), есть Ø


def clean(name):
    """Из базы в перечень идёт только тип изделия: пояснения после тире и скобки с запасом — убрать."""
    depth, cut = 0, None                            # тире внутри скобок — часть названия, не пояснение
    for i, ch in enumerate(name):
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(0, depth - 1)
        elif ch == "—" and depth == 0 and i and name[i - 1] == " ":
            cut = i - 1
            break
    if cut is not None:
        name = name[:cut]
    name = re.sub(r"\s*\((из запаса|подтяжка|LED|фильтр)[^)]*\)", "", name, flags=re.I)
    for a, b in GLYPH_FIX.items():
        name = name.replace(a, b)
    return name.strip()


# У резисторов и конденсаторов одна позиция базы может покрывать несколько элементов
# («…, делитель 10 кОм + 20 кОм»), поэтому наименование собирается из базы и номинала
# самого элемента: берётся часть позиции, относящаяся к этому виду изделия, и в ней
# номинал заменяется на номинал элемента по схеме. Если тип в базе не назван — пометка.
NOMINAL = re.compile(r"[\d.,]+\s*(Ом|кОм|МОм|пФ|нФ|мкФ|Гн|мГн|мкГн)\b", re.I)
R_WORDS = ("млт", "с2-", "с1-", "мон", "mf-", "cf-", "резистор")
C_WORDS = ("керамический", "электролитический", "плёночный", "пленочный", "танталовый",
           "конденсатор", "к10-", "к50-", "к73-")


def rc_name(letters, base, value):
    words = R_WORDS if letters == "R" else C_WORDS
    parts = [p.strip() for p in re.split(r"\s\+\s", base) if p.strip()]
    part = next((p for p in parts if p.lower().startswith(words)), None)
    if part is None:                                # тип изделия в базе не назван
        return None
    if len(parts) == 1:
        return part
    m = NOMINAL.search(part)                        # позиция общая: подставляем свой номинал
    out = part[:m.start()] + value + part[m.end():] if m else f"{part}, {value}"
    out = out.strip()
    return out[:1].upper() + out[1:]


def item_name(c, base_names):
    letters = split_ref(c["ref"])[0]
    base = clean(base_names.get(c["base"], "")) if c["base"] and c["base"] != "—" else ""
    if letters in ("R", "C"):
        return rc_name(letters, base, c["value"]) or f'{c["value"]} — тип требует уточнения'
    if base:
        return base
    return f'{c["value"]} — тип требует уточнения'


def refs_text(refs):
    """R9,R10 или R9…R13 — диапазон при трёх и более подряд идущих номерах."""
    refs = sorted(refs, key=split_ref)
    runs, cur = [], [refs[0]]
    for r in refs[1:]:
        p0, n0 = split_ref(cur[-1]); p1, n1 = split_ref(r)
        if p0 == p1 and n1 == n0 + 1:
            cur.append(r)
        else:
            runs.append(cur); cur = [r]
    runs.append(cur)
    return ",".join(f"{v[0]}…{v[-1]}" if len(v) > 2 else ",".join(v) for v in runs)


def build_rows(code):
    comps = read_schematic(code)
    base_names = read_base()
    by_group = {}
    for c in comps:
        by_group.setdefault(group_of(c["ref"]), []).append(c)
    rows = []                                        # (поз., наим., кол., прим.) | заголовок группы (5 полей) | None
    order = [g for _, g in GROUPS] + ["Прочие элементы"]
    seen = []
    for g in order:
        if g in by_group and g not in seen:
            seen.append(g)
    for g in seen:
        rows.append(None)                            # пустая строка перед заголовком группы
        rows.append(("", g, "", "", "head"))         # заголовок группы (подчёркивается)
        rows.append(None)
        merged = {}
        for c in sorted(by_group[g], key=lambda c: split_ref(c["ref"])):
            # объединяются позиции с совпавшими наименованием и примечанием; пока модель резисторов
            # и конденсаторов не выбрана, одинаковые номиналы с разными ID базы идут отдельными
            # строками — после выбора моделей наименования совпадут и строки сольются сами
            key = (item_name(c, base_names), c["base"] if c["base"] and c["base"] != "—" else "—")
            merged.setdefault(key, []).append(c["ref"])
        for (name, note), refs in sorted(merged.items(), key=lambda kv: split_ref(sorted(kv[1], key=split_ref)[0])):
            rows.append((refs_text(refs), name, str(len(refs)), note))
    while rows and rows[0] is None:
        rows.pop(0)
    return rows, len(comps)


# ---- оформление листа (ГОСТ 2.104) -----------------------------------------------------------------
THICK, THIN = 0.7, 0.35
CAP = 0.7                                        # доля высоты прописной буквы в кегле — измеряется


def measure_cap(cr):
    global CAP
    cr.select_font_face(FACE, cairo.FONT_SLANT_ITALIC, cairo.FONT_WEIGHT_NORMAL)
    cr.set_font_size(100.0)
    CAP = cr.text_extents("Н").height / 100.0


def font(cr, h):
    cr.select_font_face(FACE, cairo.FONT_SLANT_ITALIC, cairo.FONT_WEIGHT_NORMAL)
    cr.set_font_size(h / CAP)


def width_of(cr, s, h):
    font(cr, h)
    return cr.text_extents(s).x_advance


def text(cr, x, y, s, h=3.5, align="l", mid=True, rot=0.0):
    """x,y — точка привязки в мм; mid=True — y это середина строки по высоте прописных букв."""
    if not s:
        return
    font(cr, h)
    e = cr.text_extents(s)
    dx = {"l": 0.0, "c": -e.x_advance / 2, "r": -e.x_advance}[align]
    dy = h / 2 if mid else 0.0
    cr.save()
    cr.translate(x, y)
    if rot:
        cr.rotate(rot)
    cr.move_to(dx, dy)
    cr.show_text(s)
    cr.restore()


def line(cr, x1, y1, x2, y2, w=THIN):
    cr.set_line_width(w)
    cr.move_to(x1, y1)
    cr.line_to(x2, y2)
    cr.stroke()


def rect(cr, x1, y1, x2, y2, w=THIN):
    cr.set_line_width(w)
    cr.rectangle(x1, y1, x2 - x1, y2 - y1)
    cr.stroke()


def fit(cr, s, w, h, hmin=2.0):
    """Подобрать кегль, чтобы строка уместилась в графу шириной w мм (надпись не выходит за рамку)."""
    while h > hmin and width_of(cr, s, h) > w:
        h -= 0.25
    return h


def wrap(cr, s, w, h):
    """Разбить строку по ширине w мм при высоте букв h мм."""
    words, lines, cur = s.split(" "), [], ""
    for word in words:
        probe = f"{cur} {word}".strip()
        if cur and width_of(cr, probe, h) > w:
            lines.append(cur)
            cur = word
        else:
            cur = probe
    if cur:
        lines.append(cur)
    return lines


def side_graphs(cr):
    """Графы 19…23 на поле подшивки: слева от рамки, надписи снизу вверх."""
    x1, x2 = 8.0, 20.0
    top = [(5.0, 30.0, "Перв. примен."), (30.0, 55.0, "Справ. №")]
    bot = [(267.0, 292.0, "Инв. № подл."), (242.0, 267.0, "Подп. и дата"),
           (217.0, 242.0, "Взам. инв. №"), (192.0, 217.0, "Инв. № дубл."),
           (167.0, 192.0, "Подп. и дата")]
    for y1, y2, name in top + bot:
        rect(cr, x1, y1, x2, y2, THICK)
        text(cr, (x1 + x2) / 2, (y1 + y2) / 2, name, 2.5, "c", rot=-1.5707963)


def title_form2(cr, info):
    """Основная надпись по форме 2 (первый лист текстового документа), 185×40."""
    x0, y0 = FRAME[0], FRAME[3] - TB1_H                    # левый верхний угол надписи
    rect(cr, x0, y0, FRAME[2], FRAME[3], THICK)
    # верхняя часть: блок изменений 65 мм (3 строки) и графа 2 — обозначение документа
    cx = [x0, x0 + 7, x0 + 17, x0 + 40, x0 + 55, x0 + 65]
    for i in range(1, 4):
        line(cr, x0, y0 + 5 * i, x0 + 65, y0 + 5 * i, THIN if i < 3 else THICK)
    for x in cx[1:-1]:
        line(cr, x, y0, x, y0 + 15)
    line(cr, x0 + 65, y0, x0 + 65, FRAME[3], THICK)
    for lbl, a, b in zip(("Изм.", "Лист", "№ докум.", "Подп.", "Дата"), cx[:-1], cx[1:]):
        text(cr, (a + b) / 2, y0 + 12.5, lbl, 2.5, "c")
    # графа 2 — обозначение
    line(cr, x0 + 65, y0 + 15, FRAME[2], y0 + 15, THICK)
    text(cr, (x0 + 65 + FRAME[2]) / 2, y0 + 7.5, info["designation"], 7.0, "c")
    # нижняя левая часть: вид работы, фамилия, подпись, дата
    lx = [x0, x0 + 17, x0 + 40, x0 + 55, x0 + 65]
    for i in range(1, 5):
        line(cr, x0, y0 + 15 + 5 * i, x0 + 65, y0 + 15 + 5 * i)
    for x in lx[1:-1]:
        line(cr, x, y0 + 15, x, FRAME[3])
    for i, (lbl, who) in enumerate((("Разраб.", info["dev"]), ("Пров.", info["chk"]),
                                    ("Т. контр.", ""), ("Н. контр.", ""), ("Утв.", ""))):
        yc = y0 + 17.5 + 5 * i
        text(cr, x0 + 1, yc, lbl, 2.5)
        text(cr, (lx[1] + lx[2]) / 2, yc, who, fit(cr, who, 21.0, 3.5), "c")
    # графа 1 — наименование изделия и документа
    nx1, nx2 = x0 + 65, x0 + 135
    line(cr, nx2, y0 + 15, nx2, FRAME[3], THICK)
    hd = 3.5                                             # наименование документа — мельче изделия
    doc = wrap(cr, info["doc"], 66.0, hd)
    for h in (5.0, 4.5, 4.0, 3.5, 3.0):                  # кегль подбирается под высоту графы
        lines = []
        for part in info["item_lines"]:                  # наименование платы — с новой строки
            lines += wrap(cr, part, 66.0, h)
        lh, lhd = h + 1.0, hd + 1.0
        total = len(lines) * lh + len(doc) * lhd
        if total <= 23.5:
            break
    top = y0 + 15 + (25.0 - total) / 2
    for i, s in enumerate(lines):
        text(cr, (nx1 + nx2) / 2, top + lh * i + lh / 2, s, h, "c")
    top += len(lines) * lh
    for i, s in enumerate(doc):
        text(cr, (nx1 + nx2) / 2, top + lhd * i + lhd / 2, s, hd, "c")
    # правая часть: Лит., Лист, Листов, организация
    rx = x0 + 135
    line(cr, rx, y0 + 25, FRAME[2], y0 + 25, THICK)
    line(cr, rx, y0 + 20, FRAME[2], y0 + 20)
    for dx in (15.0, 30.0):
        line(cr, rx + dx, y0 + 15, rx + dx, y0 + 25)
    for dx in (5.0, 10.0):
        line(cr, rx + dx, y0 + 20, rx + dx, y0 + 25)
    text(cr, rx + 7.5, y0 + 17.5, "Лит.", 2.5, "c")
    text(cr, rx + 22.5, y0 + 17.5, "Лист", 2.5, "c")
    text(cr, rx + 40.0, y0 + 17.5, "Листов", 2.5, "c")
    text(cr, rx + 22.5, y0 + 22.5, str(info["sheet"]), 3.5, "c")
    text(cr, rx + 40.0, y0 + 22.5, str(info["sheets"]), 3.5, "c")
    org = [info["org"], f"группа {info['group']}"]
    for i, s in enumerate(org):
        text(cr, rx + 25.0, y0 + 29.0 + 6.0 * i, s, 3.5, "c")


def title_form2a(cr, info):
    """Основная надпись по форме 2а (последующие листы), 185×15."""
    x0, y0 = FRAME[0], FRAME[3] - TB2_H
    rect(cr, x0, y0, FRAME[2], FRAME[3], THICK)
    cx = [x0, x0 + 7, x0 + 17, x0 + 40, x0 + 55, x0 + 65]
    for i in (1, 2):
        line(cr, x0, y0 + 5 * i, x0 + 65, y0 + 5 * i)
    for x in cx[1:-1]:
        line(cr, x, y0, x, FRAME[3])
    line(cr, x0 + 65, y0, x0 + 65, FRAME[3], THICK)
    for lbl, a, b in zip(("Изм.", "Лист", "№ докум.", "Подп.", "Дата"), cx[:-1], cx[1:]):
        text(cr, (a + b) / 2, y0 + 12.5, lbl, 2.5, "c")
    sx = FRAME[2] - 10.0
    line(cr, sx, y0, sx, FRAME[3], THICK)
    line(cr, sx, y0 + 5, FRAME[2], y0 + 5)
    text(cr, (x0 + 65 + sx) / 2, y0 + 7.5, info["designation"], 7.0, "c")
    text(cr, sx + 5, y0 + 2.5, "Лист", 2.5, "c")
    text(cr, sx + 5, y0 + 10.0, str(info["sheet"]), 3.5, "c")


# ---- таблица перечня -------------------------------------------------------------------------------
def table_x():
    xs = [FRAME[0]]
    for w in COL:
        xs.append(xs[-1] + w)
    return xs


def draw_header(cr, y):
    xs = table_x()
    rect(cr, xs[0], y, xs[-1], y + HEAD_H, THICK)
    for x in xs[1:-1]:
        line(cr, x, y, x, y + HEAD_H, THICK)
    text(cr, (xs[0] + xs[1]) / 2, y + 5.0, "Поз.", 2.5, "c")
    text(cr, (xs[0] + xs[1]) / 2, y + 9.5, "обозначение", 2.5, "c")
    text(cr, (xs[1] + xs[2]) / 2, y + HEAD_H / 2, "Наименование", 3.5, "c")
    text(cr, (xs[2] + xs[3]) / 2, y + HEAD_H / 2, "Кол.", 3.5, "c")
    text(cr, (xs[3] + xs[4]) / 2, y + HEAD_H / 2, "Примечание", 3.5, "c")


def draw_rows(cr, y, rows, nrows, bottom):
    xs = table_x()
    for x in xs:
        line(cr, x, y, x, bottom, THICK)
    for i in range(nrows + 1):
        yy = min(y + ROW_H * i, bottom)
        line(cr, xs[0], yy, xs[-1], yy, THICK if i in (0, nrows) else THIN)
    for i, row in enumerate(rows):
        yc = y + ROW_H * i + ROW_H / 2
        if row is None:
            continue
        if is_head(row):                                     # заголовок группы — по центру, подчёркнут
            name = row[1]
            text(cr, (xs[1] + xs[2]) / 2, yc, name, 3.5, "c")
            w = width_of(cr, name, 3.5)
            line(cr, (xs[1] + xs[2] - w) / 2, yc + 2.6, (xs[1] + xs[2] + w) / 2, yc + 2.6)
            continue
        ref, name, qty, note = row
        text(cr, (xs[0] + xs[1]) / 2, yc, ref, fit(cr, ref, COL[0] - 2.0, 3.5), "c")
        text(cr, xs[1] + 2.0, yc, name, 3.5)
        text(cr, (xs[2] + xs[3]) / 2, yc, qty, 3.5, "c")
        text(cr, xs[3] + 2.0, yc, note, 3.5)


def layout(cr, rows):
    """Перенос длинных наименований: каждая строка переноса занимает отдельную строку таблицы."""
    out = []
    for row in rows:
        if row is None:
            out.append(None)
            continue
        if is_head(row):
            out.append(row)
            continue
        ref, name, qty, note = row
        parts = wrap(cr, name, COL[1] - 4.0, 3.5)
        out.append((ref, parts[0], qty, note))
        for p in parts[1:]:
            out.append(("", p, "", ""))
    return out


def is_head(row):
    return row is not None and len(row) == 5


def paginate(rows):
    cap1 = int((FRAME[3] - TB1_H - FRAME[1] - HEAD_H) // ROW_H)
    cap2 = int((FRAME[3] - TB2_H - FRAME[1] - HEAD_H) // ROW_H)
    pages, i = [], 0
    while i < len(rows):
        while i < len(rows) and rows[i] is None:            # лист не начинается с пустой строки
            i += 1
        if i >= len(rows):
            break
        cap = cap1 if not pages else cap2
        chunk = rows[i:i + cap]
        while chunk and (is_head(chunk[-1]) or chunk[-1] is None):
            chunk.pop()
        pages.append(chunk)
        i += len(chunk)
    return pages, cap1, cap2


def main():
    rows, total = build_rows(CODE)
    out = ROOT / "docs" / CODE / f"{dt.doc_name('ПЭ3')}.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    surf = cairo.PDFSurface(str(out), W * MM, H * MM)
    cr = cairo.Context(surf)
    cr.scale(MM, MM)
    measure_cap(cr)
    rows = layout(cr, rows)
    pages, cap1, cap2 = paginate(rows)
    info = {"designation": dt.designation(CODE, "ПЭ3"),
            "item_lines": [f"{dt.PROJECT}.", dt.board_name(CODE)],
            "doc": dt.doc_name("ПЭ3"), "dev": dt.DEV, "chk": dt.CHK,
            "org": dt.ORG, "group": dt.GROUP, "sheets": len(pages)}
    for n, page in enumerate(pages, 1):
        cr.set_source_rgb(0, 0, 0)
        rect(cr, FRAME[0], FRAME[1], FRAME[2], FRAME[3], THICK)
        side_graphs(cr)
        draw_header(cr, FRAME[1])
        first = n == 1
        bottom = FRAME[3] - (TB1_H if first else TB2_H)
        draw_rows(cr, FRAME[1] + HEAD_H, page, cap1 if first else cap2, bottom)
        info["sheet"] = n
        (title_form2 if first else title_form2a)(cr, info)
        cr.show_page()
    surf.finish()
    print(f"{out}: компонентов {total}, строк {len(rows)}, листов {len(pages)}")


if __name__ == "__main__":
    main()

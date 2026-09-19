#!/usr/bin/env python3
"""Сверка цепей схемы и платы <КОД> (по умолчанию PS): netlist из boards/<КОД>/<КОД>.kicad_sch против назначений
площадок в scripts/gen_PS_pcb.py (PLACE). Разбиение выводов на цепи должно совпадать с точностью до имён
безымянных цепей; именованные (символы питания) должны совпадать по имени.

Запуск: python3 scripts/check_sch_pcb.py   (из корня репозитория)
"""
import importlib.util
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODE = sys.argv[1] if len(sys.argv) > 1 else "PS"
sys.path.insert(0, str(ROOT / "scripts"))
SCH = ROOT / "boards" / CODE / f"{CODE}.kicad_sch"
spec = importlib.util.spec_from_file_location("gen", ROOT / "scripts" / f"gen_{CODE}_pcb.py")
g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)

s = SCH.read_text(encoding="utf-8")

# --- выводы библиотечных символов: {lib: [(num, x, y, hidden)]}
libpins = {}
lib_block = s[s.index("(lib_symbols"):s.index("\n  (symbol (lib_id")]
for m in re.finditer(r'\(symbol "manipulator:([^"]+)"(.*?)\n  \)\n', lib_block, re.S):
    pins = re.findall(r'\(pin \w+ line \(at ([-\d.]+) ([-\d.]+) (\d+)\) \(length ([-\d.]+)\)( \(hide yes\))?.*?\(number "([^"]+)"', m.group(2), re.S)
    libpins[m.group(1)] = [(num, float(x), float(y), bool(h)) for x, y, a, ln, h, num in pins]

# --- экземпляры
inst = re.findall(r'\(symbol \(lib_id "manipulator:([^"]+)"\) \(at ([-\d.]+) ([-\d.]+) (\d+)\).*?\(property "Reference" "([^"]+)".*?\(property "Value" "([^"]+)"', s, re.S)
P = lambda x, y: (round(x, 2), round(y, 2))
parent = {}


def find(a):
    while parent.setdefault(a, a) != a:
        a = parent[a]
    return a


def union(a, b):
    parent[find(a)] = find(b)


pinpts = []      # ((ref, num), point)
powerpts = []    # (net, point)
for lib, x, y, rot, ref, val in inst:
    x, y, rot = float(x), float(y), int(rot)
    for num, px, py, hidden in libpins[lib]:
        X, Y = (x + px, y - py) if rot == 0 else (x - px, y + py)
        pt = P(X, Y)
        if ref.startswith("#PWR"):
            powerpts.append((val, pt))
        else:
            pinpts.append(((ref, num), pt))
wires = [tuple(map(float, m)) for m in re.findall(r'\(wire \(pts \(xy ([-\d.]+) ([-\d.]+)\) \(xy ([-\d.]+) ([-\d.]+)\)\)', s)]
ncs = {P(float(a), float(b)) for a, b in re.findall(r'\(no_connect \(at ([-\d.]+) ([-\d.]+)\)', s)}

for x1, y1, x2, y2 in wires:
    union(("pt", P(x1, y1)), ("pt", P(x2, y2)))
for key, pt in pinpts:
    union(("pin", key), ("pt", pt))
for net, pt in powerpts:
    union(("net", net), ("pt", pt))
# вывод, лежащий на середине провода (Т без явного узла) — тоже соединение
for key, pt in pinpts:
    for x1, y1, x2, y2 in wires:
        dx, dy = x2 - x1, y2 - y1
        L2 = dx * dx + dy * dy
        t = ((pt[0] - x1) * dx + (pt[1] - y1) * dy) / L2 if L2 else 0
        if 0 <= t <= 1 and math.hypot(x1 + t * dx - pt[0], y1 + t * dy - pt[1]) < 0.01:
            union(("pin", key), ("pt", P(x1, y1)))

# цепи схемы: {root: {"name": ..., "pins": set}}
sch_nets = {}
for key, pt in pinpts:
    r = find(("pin", key))
    sch_nets.setdefault(r, {"name": None, "pins": set()})["pins"].add(key)
for net, pt in powerpts:
    r = find(("net", net))
    if r in sch_nets:
        if sch_nets[r]["name"] not in (None, net):
            print("ПРОБЛЕМА: две шины на одной цепи:", sch_nets[r]["name"], net)
        sch_nets[r]["name"] = net
# выводы без цепи
for key, pt in pinpts:
    r = find(("pin", key))
    if len(sch_nets[r]["pins"]) == 1 and sch_nets[r]["name"] is None:
        if pt not in ncs:
            print("ПРОБЛЕМА: вывод схемы не подключён и без флага NC:", key)

# --- плата
pcb_nets = {}
for ref, fp, val, x, y, nets in g.PLACE:
    for num, net in nets.items():
        if net.startswith("unconnected-") or not net:
            continue
        pcb_nets.setdefault(net, set()).add((ref, num))
pcb_pins = {p for v in pcb_nets.values() for p in v}
# площадка «3» реле встречается дважды в footprint — как вывод одна

problems = []
sch_groups = {frozenset(v["pins"]): v["name"] for v in sch_nets.values() if len(v["pins"]) > 1 or v["name"]}
pcb_groups = {frozenset(v): k for k, v in pcb_nets.items()}
for grp, name in sch_groups.items():
    if grp not in pcb_groups:
        near = [k for k in pcb_groups if k & grp]
        problems.append(f"цепь схемы {name or '(без имени)'} {sorted(grp)} не совпадает с платой; пересекающиеся цепи платы: "
                        + "; ".join(f"{pcb_groups[k]} {sorted(k)}" for k in near))
    elif name and pcb_groups[grp] != name:
        problems.append(f"имя цепи: схема {name}, плата {pcb_groups[grp]} для {sorted(grp)}")
for grp, name in pcb_groups.items():
    if grp not in sch_groups:
        problems.append(f"цепь платы {name} {sorted(grp)} отсутствует в схеме")
sch_pins = {k for k, _ in pinpts}
extra = pcb_pins - sch_pins
missing = {k for k in sch_pins if k not in pcb_pins and P(0, 0) and find(("pin", k)) in sch_nets and len(sch_nets[find(("pin", k))]["pins"]) > 1}
if extra:
    problems.append(f"на плате есть выводы, которых нет в схеме: {sorted(extra)}")
if missing:
    problems.append(f"выводы схемы без площадки на плате: {sorted(missing)}")

print(f"схема: {len(sch_groups)} цепей, {len(sch_pins)} выводов; плата: {len(pcb_groups)} цепей, {len(pcb_pins)} выводов")
for name in sorted(n for n in sch_groups.values() if n):
    print("  ", name, "→", sorted(next(k for k, v in sch_groups.items() if v == name)))
for p in problems:
    print("  ПРОБЛЕМА:", p)
print("расхождений:", len(problems))
sys.exit(1 if problems else 0)

#!/usr/bin/env python3
"""Перезапись библиотеки посадочных мест lib/footprints/manipulator.pretty без перегенерации плат.

Нужен, когда меняется общий код footprint'ов в pcb_common.py (геометрия, 3D-модели), а платы трогать нельзя:
LR.kicad_pcb сохранён в KiCad, PS/MC ждут решений. Собирает все места библиотеки (конструкторы pcb_common
со всеми вариантами) и локальные места генераторов плат (реле, модули — определены в gen_<КОД>_pcb.py;
генераторы импортируются, но write() не вызывается, файлы плат не меняются).

Запуск: python3 scripts/gen_footprints.py
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pcb_common as pc    # noqa: E402

# все места общей библиотеки (варианты, которых в библиотеке ещё нет, не создаются — хранится только используемое)
existing = {p.stem for p in pc.OUT_FP.glob("*.kicad_mod")}
pc.tb_dg301(); pc.tb_dg301(vertical=True)
for n in (2, 4, 5):
    for o in ("", "L", "R"):
        pc.jst_xh(n, o)
pc.jst_vh(2); pc.jst_vh(2, vertical=True); pc.jst_vh(2, orient="L")
pc.relay_nrp15(); pc.mornsun_ymd(); pc.d_smc(); pc.d_do41(); pc.r_axial(); pc.r_axial(vertical=True)
pc.cp_radial(); pc.c_disc(); pc.l_toroid(); pc.module_zone(); pc.pin_socket_1x22(); pc.module_cjmcu9548()
pc.dip6(); pc.dip6(horizontal=True); pc.dip16(); pc.d_do35(); pc.sot23(); pc.led_bicolor_5mm()
pc.idc_2x06(); pc.idc_2x06("D"); pc.fuse_ptc_radial()
for name in [n for n in pc.FPS if n not in existing]:
    del pc.FPS[name]
written = []
for name, f in pc.FPS.items():
    (pc.OUT_FP / f"{name}.kicad_mod").write_text(f.lib_file(), encoding="utf-8")
    written.append(name)
print(f"общая библиотека: записано {len(written)} мест, с 3D-моделью {sum(1 for n in written if pc.FPS[n].model)}")

# локальные места генераторов плат — каждый генератор в своём процессе (состояние pcb_common общее на процесс),
# write() не вызывается, файлы плат не меняются
here = Path(__file__).resolve().parent
for code in ("PS", "MC", "LR", "CH"):
    cmd = (f"import sys; sys.path.insert(0, {str(here)!r}); import pcb_common as pc, gen_{code}_pcb as g\n"
           f"for n, f in pc.FPS.items():\n"
           f"    (pc.OUT_FP / (n + '.kicad_mod')).write_text(f.lib_file(), encoding='utf-8')\n"
           f"print('gen_{code}_pcb: мест', len(pc.FPS), 'с моделью', sum(1 for f in pc.FPS.values() if f.model))")
    r = subprocess.run([sys.executable, "-c", cmd], capture_output=True, text=True)
    out = (r.stdout.strip().splitlines() or [""])[-1]
    if r.returncode:
        print(f"предупреждение: gen_{code}_pcb не выполнен — его локальные места не обновлены:\n{r.stderr.strip().splitlines()[-1]}")
    else:
        print(out)

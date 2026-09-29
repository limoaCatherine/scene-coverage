"""当前覆盖率：读场景表 → 按地图算效用 → 写平衡总览。"""
from __future__ import annotations

import openpyxl

from 场景覆盖 import config as cfg
from 场景覆盖.calc.layered_fact import calc_layered_facts
from 场景覆盖.load.layout_v2 import load_scene_v2
from 场景覆盖.load.matrices import read_all_matrices
from 场景覆盖.write.layered import write_layered


def run(
    framework_path: str | None = None,
    verbose: bool = False,
    verify: bool = True,
) -> dict:
    del verify
    if not verbose:
        cfg.QUIET = True
    path = str(framework_path or cfg.FRAMEWORK_FILE)
    cfg.FRAMEWORK_FILE = path

    wb = openpyxl.load_workbook(path, data_only=False)
    try:
        scene = load_scene_v2(wb)
        matrices = read_all_matrices(wb)
    finally:
        wb.close()

    layered = calc_layered_facts(
        scene,
        matrices["PVE属性克制"][1],
        matrices["PVP属性克制"][1],
        mat_size_pve=matrices["PVE体型克制"][2],
        weapon_types=matrices["PVE体型克制"][0],
    )
    out_path = write_layered(path, rankings={}, layered=layered)
    builds = list(layered["builds"])
    print("\n覆盖率仿真完成。")
    return {
        "ok": True,
        "path": out_path,
        "builds_detected": len(builds),
        "builds": builds,
        "verify_code": None,
        "layered": layered,
    }

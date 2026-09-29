# formula_proxy.py — 无 Excel COM / 无 formulas 缓存时，用源数值列近似公式列
"""地图价值 / 等级 PVE·PVP 占比 在 data_only 下常为 None（公式未缓存）。

本模块用同表已有数值源近似：
- PVE%/PVP% ← 玩法三维分布（按场景类型/玩法名 MATCH）
- 期望业务价值 ← 等级价值占比 × 玩法价值基准值
- 等级 PVE/PVP 价值占比 ← Σ(玩法份额×PVE%) × 价值占比
不改 xlsx，只改内存中的 worksheet 单元格。
"""
from __future__ import annotations

from 场景覆盖 import config as cfg


def _parse_lv(val) -> int | None:
    if val is None:
        return None
    s = str(val).strip()
    if s.upper().startswith("LV"):
        s = s[2:]
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return None


def _f(val, default=0.0) -> float:
    if val is None or isinstance(val, bool):
        return float(default)
    if isinstance(val, (int, float)):
        return float(val)
    try:
        return float(str(val).strip().rstrip("%"))
    except (TypeError, ValueError):
        return float(default)


def fill_scene_formula_proxies(ws) -> dict:
    """就地填补「场景覆盖」公式列的空缓存；返回诊断信息。"""
    info = {"filled_map_value": 0, "filled_map_pve": 0, "filled_level_beta": 0, "skipped": 0}

    col_pw = cfg.COL.get("玩法三维分布_玩法")
    col_pve = cfg.COL.get("玩法三维分布_PVE%") or cfg.COL.get("BE_PVE_PCT_COL")
    col_pvp = cfg.COL.get("玩法三维分布_PVP%") or cfg.COL.get("BE_PVP_PCT_COL")
    col_base = cfg.COL.get("玩法三维分布_玩法价值基准值")
    col_lv_label = cfg.COL.get("玩法等级分布占比_等级")
    col_lv_w = cfg.COL.get("玩法等级分布占比_价值占比")
    col_lv_pve = cfg.COL.get("玩法等级分布占比_PVE价值占比")
    col_lv_pvp = cfg.COL.get("玩法等级分布占比_PVP价值占比")

    # 等级 → 价值占比 + LV 份额列
    level_w: dict[int, float] = {}
    if col_lv_label and col_lv_w:
        for r in range(cfg.LEVEL_SUMMARY_DATA_START, cfg.LEVEL_SUMMARY_DATA_END + 1):
            lv = _parse_lv(ws.cell(r, col_lv_label).value)
            if lv is None:
                continue
            level_w[lv] = _f(ws.cell(r, col_lv_w).value)

    lv_share_cols: dict[int, int] = {}
    for lv in cfg.LEVELS_5STEP:
        c = cfg.COL.get(f"玩法三维分布_LV{lv}")
        if c:
            lv_share_cols[lv] = c

    # 玩法名 → (pve, pvp, base, row)
    playways: dict[str, tuple] = {}
    if col_pw and col_pve:
        empty = 0
        for r in range(cfg.BE_DATA_ROW_START, (ws.max_row or 200) + 1):
            name = ws.cell(r, col_pw).value
            if name is None or not str(name).strip():
                empty += 1
                if empty >= 2:
                    break
                continue
            empty = 0
            name = str(name).strip()
            if name == "玩法" or "合计" in name:
                continue
            pve_raw = ws.cell(r, col_pve).value
            pvp_raw = ws.cell(r, col_pvp).value if col_pvp else None
            if pve_raw is None and pvp_raw is None:
                continue
            pve = _f(pve_raw)
            pvp = _f(pvp_raw) if col_pvp else 0.0
            if col_base is None or ws.cell(r, col_base).value is None:
                continue
            base = _f(ws.cell(r, col_base).value)
            playways[name] = (pve, pvp, base, r)

    # 等级 β = Σ(份额×PVE%) / Σ(份额×(PVE%+PVP%))
    level_beta: dict[int, float] = {}
    for lv, c_share in lv_share_cols.items():
        num = den = 0.0
        for name, (pve, pvp, _b, r) in playways.items():
            share = _f(ws.cell(r, c_share).value)
            num += share * pve
            den += share * (pve + pvp)
        if den > 1e-15:
            level_beta[lv] = num / den

    # 填 玩法等级分布占比 PVE/PVP 价值占比
    if col_lv_label and col_lv_w and col_lv_pve and col_lv_pvp:
        for r in range(cfg.LEVEL_SUMMARY_DATA_START, cfg.LEVEL_SUMMARY_DATA_END + 1):
            lv = _parse_lv(ws.cell(r, col_lv_label).value)
            if lv is None:
                continue
            w = _f(ws.cell(r, col_lv_w).value)
            beta = level_beta.get(lv)
            if beta is None:
                continue
            cur_p = ws.cell(r, col_lv_pve).value
            cur_v = ws.cell(r, col_lv_pvp).value
            if _f(cur_p) == 0.0 and _f(cur_v) == 0.0:
                ws.cell(r, col_lv_pve).value = beta * w
                ws.cell(r, col_lv_pvp).value = (1.0 - beta) * w
                info["filled_level_beta"] += 1

    # 填 地图价值 公式列
    c_stype = cfg.COL.get("地图价值_场景类型")
    c_lv = cfg.COL.get("地图价值_等级")
    c_val = cfg.COL.get("地图价值_期望业务价值")
    c_pve = cfg.COL.get("地图价值_PVE占比")
    c_pvp = cfg.COL.get("地图价值_PVP占比")
    data_end = int(cfg.COL.get("SCENE_DATA_END") or (ws.max_row or 5))
    if c_stype and c_lv and c_val:
        for r in range(cfg.SCENE_DATA_START, data_end + 1):
            stype = ws.cell(r, c_stype).value
            if stype is None or not str(stype).strip() or "合计" in str(stype):
                continue
            stype = str(stype).strip()
            lv = _parse_lv(ws.cell(r, c_lv).value)
            pw = playways.get(stype) or playways.get(cfg.SCENE_TO_PLAYWAY.get(stype, ""), None)
            if pw is None:
                info["skipped"] += 1
                continue
            pve, pvp, base, _ = pw
            if c_pve and ws.cell(r, c_pve).value is None:
                ws.cell(r, c_pve).value = pve
                info["filled_map_pve"] += 1
            if c_pvp and ws.cell(r, c_pvp).value is None:
                ws.cell(r, c_pvp).value = pvp
            if ws.cell(r, c_val).value is None:
                if lv is None or lv not in level_w:
                    continue
                ws.cell(r, c_val).value = level_w[lv] * base
                info["filled_map_value"] += 1

    cfg.qprint(
        f"{cfg.PRINT_PREFIX_READ} 公式代理填充: "
        f"地图价值={info['filled_map_value']}, 地图PVE%={info['filled_map_pve']}, "
        f"等级β={info['filled_level_beta']}, 未匹配玩法行≈{info['skipped']}"
    )
    return info

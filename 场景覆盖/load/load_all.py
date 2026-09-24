# load_all.py — 组装覆盖率仿真所需的全部输入 data dict
import openpyxl

from 场景覆盖 import config as cfg

from .scenes import (
    read_map_encounters,
    read_scene_coverage,
    _validate_layer_chain,
    aggregate_scene_coverage,
    read_level_pve_pvp_ratios,
    read_level_value_ratios,
)
from .builds import (
    read_be_table,
    read_build_panel,
    read_playway_level_shares,
    compose_level_build_meta,
    derive_pvp_env_distributions,
)
from .matrices import read_all_matrices
from .layout_v2 import find_block


def _is_scene_v2(ws) -> bool:
    try:
        find_block(ws, "玩法")
        find_block(ws, "地图")
        find_block(ws, "遭遇")
        find_block(ws, "偏好")
        return True
    except Exception:
        return False


def _dict_to_playway_lists(by_lv: dict, real_builds: list) -> dict:
    """{lv: {build: w}} → {__LEVEL_META__: {lv: [w...]}}"""
    out = {}
    for lv, bw in by_lv.items():
        lst = [float(bw.get(b, 0.0)) for b in real_builds]
        s = sum(lst)
        if s > 0:
            lst = [x / s for x in lst]
        out[lv] = lst
    return {"__LEVEL_META__": out}


def _load_all_v2(wb):
    from .layout_v2 import load_scene_v2 as _load

    scene = _load(wb)
    builds = scene["weights"]["builds"]
    plays = scene["weights"]["play_names"]
    cube = scene["weights"]["cube"]
    raw_pve, raw_pvp = {}, {}
    for lv in range(1, 61):
        pve, pvp = {b: 0.0 for b in builds}, {b: 0.0 for b in builds}
        for play in plays:
            for b in builds:
                pve[b] += cube[(lv, "PVE", play, b)][0]
                pvp[b] += cube[(lv, "PVP", play, b)][0]
        raw_pve[lv], raw_pvp[lv] = pve, pvp

    def _fill(raw):
        first = next((raw[lv] for lv in range(1, 61) if sum(raw[lv].values()) > 0), None)
        if first is None:
            raise cfg.ConfigDriftError("全等级该模式权重为 0")
        last, out = first, {}
        for lv in range(1, 61):
            cur = raw[lv] if sum(raw[lv].values()) > 0 else last
            tot = sum(cur.values())
            out[lv] = {k: v / tot for k, v in cur.items()}
            last = out[lv]
        return out

    pve_by_lv, pvp_by_lv = _fill(raw_pve), _fill(raw_pvp)
    levels = list(range(1, 61))
    n_builds = len(builds)
    if n_builds > 0 and cfg.RANK_BLOCK_LAYOUT:
        bid, title, col0, _old = cfg.RANK_BLOCK_LAYOUT[0]
        cfg.RANK_BLOCK_LAYOUT[0] = (bid, title, col0, n_builds)
    all_matrices = read_all_matrices(wb)
    pve_table = {lv: {"build_weights": dict(pve_by_lv[lv])} for lv in levels}
    pvp_table = {lv: {"build_weights": dict(pvp_by_lv[lv])} for lv in levels}
    mat_attr_pve = all_matrices.get("PVE属性克制", ([], {}))[1]
    mat_attr_pvp = all_matrices.get("PVP属性克制", ([], {}))[1]
    wep_list, _, mat_size_pve = all_matrices.get("PVE体型克制", ([], [], {}))
    _, _, mat_size_pvp = all_matrices.get("PVP体型克制", ([], [], {}))
    at_pve, rc_pve, sz_pve = scene["attr_types"], scene["race_types"], scene["size_types"]
    pve_composite = derive_pvp_env_distributions(
        pve_table, scene["build_panel"], levels, at_pve, rc_pve, sz_pve, wep_list
    )
    pvp_composite = derive_pvp_env_distributions(
        pvp_table, scene["build_panel"], levels, at_pve, rc_pve, sz_pve, wep_list
    )
    playway_dist = {
        "PVE": _dict_to_playway_lists(pve_by_lv, builds),
        "PVP": _dict_to_playway_lists(pvp_by_lv, builds),
    }
    return {
        "levels_pve": levels,
        "pve_config": scene["pve_config"],
        "pvp_table": pvp_table,
        "pve_table": pve_table,
        "be_table": {
            "build_names": builds,
            "playways": [
                {
                    "name": p["name"],
                    "pve_pct": p["pve"],
                    "pvp_pct": p["pvp"],
                    "dist": [scene["prefs"]["prefs"][p["name"]].get(b, 0.0) for b in builds],
                }
                for p in scene["play"]["playways"]
            ],
        },
        "build_panel": scene["build_panel"],
        "attr_types": at_pve,
        "size_types": sz_pve,
        "race_types": rc_pve,
        "matrices": all_matrices,
        "attr_matrix_pve": mat_attr_pve,
        "attr_matrix_pvp": mat_attr_pvp,
        "weapon_types": wep_list,
        "size_matrix_pve": mat_size_pve,
        "size_matrix_pvp": mat_size_pvp,
        "pve_weights": {"__LEVEL_META__": 1.0},
        "pvp_weights": {"__LEVEL_META__": 1.0},
        "pve_playway_dist": playway_dist.get("PVE", {}),
        "pvp_playway_dist": playway_dist.get("PVP", {}),
        "pve_composite": pve_composite,
        "pvp_composite": pvp_composite,
        "scene_config_raw": {},
        "per_level_weights": scene["per_level_weights"],
        "per_level_weights_hat": dict(scene["per_level_weights"]),
        "level_weights": scene["level_weights"],
        "level_lifecycle_weights": scene["level_weights"],
        "level_value_ratios": scene["level_weights"],
        "meta_mode": "per_level",
        "meta_note": "分等级 meta=1–60 玩法份额×PVE%/PVP%×偏好；立方未先塌缩玩法",
        "scene_v2": scene,
    }


def load_all():
    """加载覆盖配置与克制矩阵, 返回 calc 所需 data dict。"""
    cfg.qprint("=" * 60)
    wb = openpyxl.load_workbook(cfg.FRAMEWORK_FILE, data_only=True)
    _scene_ws = wb[cfg.SHEET_SCENE]
    if _is_scene_v2(_scene_ws):
        cfg.qprint("加载覆盖配置与克制矩阵... (1–60 横排块)")
        data = _load_all_v2(wb)
        wb.close()
        return data

    cfg.qprint("加载覆盖配置与克制矩阵... (四层架构 + 按等级玩法 meta)")
    cfg.resolve_scenes(_scene_ws)
    cfg.resolve_columns(_scene_ws)
    # data_only 下地图价值/等级β公式常无缓存；用源数值列近似（无 COM）
    from .formula_proxy import fill_scene_formula_proxies
    fill_scene_formula_proxies(_scene_ws)
    # 动态看板条数 = 实际构筑数
    n_builds = int(cfg.COL.get("N_BE_BUILDS") or cfg.COL.get("N_SPEC3_BUILDS") or 0)
    if n_builds > 0 and cfg.RANK_BLOCK_LAYOUT:
        bid, title, col0, _old_n = cfg.RANK_BLOCK_LAYOUT[0]
        cfg.RANK_BLOCK_LAYOUT[0] = (bid, title, col0, n_builds)
    n_wep = len(cfg.WEAPON_MATRIX_TYPES)
    for i, (bid, title, col0, _n) in enumerate(cfg.RANK_BLOCK_LAYOUT):
        if bid == "weapon":
            cfg.RANK_BLOCK_LAYOUT[i] = (bid, title, col0, n_wep)

    map_encounters = read_map_encounters(wb)
    levels, scene_config, at_pve, sz_pve, rc_pve = read_scene_coverage(wb)

    build_panel = read_build_panel(wb)

    _validate_layer_chain(scene_config, map_encounters)

    excel_pve_pvp = read_level_pve_pvp_ratios(wb)

    pve_config, per_level_weights, levels, per_level_weights_hat = aggregate_scene_coverage(
        scene_config, map_encounters, build_panel,
        excel_pve_pvp=excel_pve_pvp,
    )

    all_matrices = read_all_matrices(wb)

    be_table = read_be_table(wb)
    if not be_table:
        raise cfg.ConfigDriftError(
            "BE 玩法流派偏好块为空 — 无法合成 PVE/PVP 流派 meta"
        )

    level_shares = read_playway_level_shares(wb)
    meta = compose_level_build_meta(be_table, level_shares, levels)
    real_builds = meta["real_builds"]

    playway_dist = {
        "PVE": _dict_to_playway_lists(meta["pve_by_lv"], real_builds),
        "PVP": _dict_to_playway_lists(meta["pvp_by_lv"], real_builds),
    }
    pve_weights = {"__LEVEL_META__": 1.0}
    pvp_weights = {"__LEVEL_META__": 1.0}

    pve_table = {lv: {"build_weights": dict(meta["pve_by_lv"][lv])} for lv in levels}
    pvp_table = {lv: {"build_weights": dict(meta["pvp_by_lv"][lv])} for lv in levels}

    level_weights = read_level_value_ratios(wb)

    wb.close()

    mat_attr_pve = all_matrices.get("PVE属性克制", ([], {}))[1]
    mat_attr_pvp = all_matrices.get("PVP属性克制", ([], {}))[1]
    wep_list, _, mat_size_pve = all_matrices.get("PVE体型克制", ([], [], {}))
    _, _, mat_size_pvp = all_matrices.get("PVP体型克制", ([], [], {}))

    # PVE/PVP 玩家侧三维+武器: 都由该等级流派 meta × 流派面板派生
    pve_composite = derive_pvp_env_distributions(
        pve_table, build_panel, levels, at_pve, rc_pve, sz_pve, wep_list
    )
    pvp_composite = derive_pvp_env_distributions(
        pvp_table, build_panel, levels, at_pve, rc_pve, sz_pve, wep_list
    )

    meta_note = (
        "分等级 meta=玩法三维分布×等级份额×PVE%/PVP%×BE流派"
        if meta["meta_mode"] == "per_level"
        else "回退: 全等级共用 BE 全局聚合 (缺玩法三维分布 LV 列)"
    )

    return {
        "levels_pve": levels,
        "pve_config": pve_config,
        "pvp_table": pvp_table,
        "pve_table": pve_table,
        "be_table": be_table,
        "build_panel": build_panel,
        "attr_types": at_pve,
        "size_types": sz_pve,
        "race_types": rc_pve,
        "matrices": all_matrices,
        "attr_matrix_pve": mat_attr_pve,
        "attr_matrix_pvp": mat_attr_pvp,
        "weapon_types": wep_list,
        "size_matrix_pve": mat_size_pve,
        "size_matrix_pvp": mat_size_pvp,
        "pve_weights": pve_weights,
        "pvp_weights": pvp_weights,
        "pve_playway_dist": playway_dist.get("PVE", {}),
        "pvp_playway_dist": playway_dist.get("PVP", {}),
        "pve_composite": pve_composite,
        "pvp_composite": pvp_composite,
        "scene_config_raw": scene_config,
        "per_level_weights": per_level_weights,
        "per_level_weights_hat": per_level_weights_hat,
        "level_weights": level_weights,
        "level_lifecycle_weights": level_weights,
        "level_value_ratios": level_weights,
        "meta_mode": meta["meta_mode"],
        "meta_note": meta_note,
    }

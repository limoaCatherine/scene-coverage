# fairness.py — 流派 BFI (攻相对 × 守倒数); 跨等级先加权攻守再算 BFI
from __future__ import annotations

from typing import Dict

import numpy as np

from 场景覆盖 import config as cfg
from .env import EnvBundle
from .matrix_ops import atk_utility_vec, expected_util
from .utilities import _playway_build_weights


def _bfi_from_utils(atk: Dict[str, float], deff: Dict[str, float], builds: list) -> Dict[str, dict]:
    n = len(builds)
    if n <= 0:
        return {}
    avg_atk = sum(atk[b] for b in builds) / n
    avg_def = sum(deff[b] for b in builds) / n
    if avg_atk <= 0 or avg_def <= 0:
        raise ValueError(
            f"{cfg.PRINT_PREFIX_WARN} BFI 均值 atk={avg_atk} def={avg_def}≤0, 业务数据缺失"
        )
    out = {}
    for b in builds:
        if deff[b] <= cfg.PROGRAM_EPS:
            raise ValueError(f"{cfg.PRINT_PREFIX_WARN} {b} 守方效用≤0")
        atk_r = atk[b] / avg_atk
        def_r = avg_def / deff[b]  # 挨打越少越好
        out[b] = {
            "attacker": round(atk[b], 4),
            "defender": round(deff[b], 4),
            "bfi": round(atk_r * def_r, 4),
        }
    return out


def calc_build_fairness_index(bundle: EnvBundle) -> Dict:
    """
    BFI(流派) = (攻方/均值攻) × (均值守/守方)
    跨等级综合: 先对攻/守做 W_L 加权, 再按上式算 BFI (可互验)。
    """
    builds = bundle.real_builds
    if not builds:
        raise ValueError(f"{cfg.PRINT_PREFIX_WARN} 无有效流派, 无法算 BFI")

    result = {"PVE": {}, "PVP": {}, "综合": {}, "跨等级综合": {}}

    for lv in bundle.levels:
        le = bundle.by_level[lv]
        # --- PVE: 各流派独立打怪物环境 (不依赖玩法内互相权重循环空转) ---
        monster = le.pve_attr
        mat = bundle.mat_attr_pve
        atk_v = atk_utility_vec(monster, mat)
        pve_atk = {b: float(bundle.build_attr[b] @ atk_v) for b in builds}
        pve_def = {b: expected_util(monster, bundle.build_attr[b], mat) for b in builds}

        # --- PVP meta ---
        pvp_bd = _playway_build_weights(
            bundle.pvp_playway_dist, bundle.pvp_weights, builds, lv
        )
        meta = np.zeros(len(bundle.attr_types))
        for b, bw in pvp_bd.items():
            meta += bw * bundle.build_attr[b]
        if meta.sum() <= 0:
            raise ValueError(f"{cfg.PRINT_PREFIX_WARN} Lv{lv} PVP meta sum≤0")
        meta = meta / meta.sum()
        matp = bundle.mat_attr_pvp
        atk_vm = atk_utility_vec(meta, matp)
        pvp_atk = {b: float(bundle.build_attr[b] @ atk_vm) for b in builds}
        pvp_def = {b: expected_util(meta, bundle.build_attr[b], matp) for b in builds}

        comp_atk = {
            b: le.beta_pve * pve_atk[b] + le.beta_pvp * pvp_atk[b] for b in builds
        }
        comp_def = {
            b: le.beta_pve * pve_def[b] + le.beta_pvp * pvp_def[b] for b in builds
        }

        result["PVE"][lv] = _bfi_from_utils(pve_atk, pve_def, builds)
        result["PVP"][lv] = _bfi_from_utils(pvp_atk, pvp_def, builds)
        result["综合"][lv] = _bfi_from_utils(comp_atk, comp_def, builds)

    # 跨等级: 先加权攻守, 再算 BFI
    atk_life = {b: 0.0 for b in builds}
    def_life = {b: 0.0 for b in builds}
    total_w = 0.0
    skipped = []
    for lv in bundle.levels:
        lw = bundle.level_weights.get(lv, 0.0)
        if lw <= 0:
            skipped.append(lv)
            continue
        total_w += lw
        for b in builds:
            atk_life[b] += lw * result["综合"][lv][b]["attacker"]
            def_life[b] += lw * result["综合"][lv][b]["defender"]
    if skipped:
        print(f"{cfg.PRINT_PREFIX_WARN} 跨等级 BFI 跳过 lw=0 等级: {skipped}")
    if total_w <= 0:
        raise ValueError(f"{cfg.PRINT_PREFIX_WARN} level_weights 全 0, 无法跨等级综合")
    atk_life = {b: v / total_w for b, v in atk_life.items()}
    def_life = {b: v / total_w for b, v in def_life.items()}
    result["跨等级综合"] = _bfi_from_utils(atk_life, def_life, builds)

    cfg.qprint(f"{cfg.PRINT_PREFIX_BFI} 流派平衡指数 (跨等级可互验)")
    return result

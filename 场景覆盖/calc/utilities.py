# utilities.py — 属性/武器/种族/体型效用 + 四象限
from __future__ import annotations

from typing import Dict

import numpy as np

from 场景覆盖 import config as cfg
from .env import EnvBundle, env_dist
from .matrix_ops import atk_utility_vec, def_hit_vec, expected_util


def _mix_scalar(pve: float, pvp: float, beta_pve: float, beta_pvp: float) -> float:
    return beta_pve * pve + beta_pvp * pvp


def _mix_dict(pve_d: dict, pvp_d: dict, beta_pve: float, beta_pvp: float) -> dict:
    keys = set(pve_d) | set(pvp_d)
    return {k: _mix_scalar(pve_d.get(k, 0.0), pvp_d.get(k, 0.0), beta_pve, beta_pvp) for k in keys}


def calc_attr_utility_breakdown(bundle: EnvBundle) -> Dict:
    """逐属性攻/守效用. 守方 = 挨打量(越大越疼)。"""
    result = {
        "PVE": {"attr_attacker": {}, "attr_defender": {}},
        "PVP": {"attr_attacker": {}, "attr_defender": {}},
        "综合": {"attr_attacker": {}, "attr_defender": {}},
    }
    for lv in bundle.levels:
        le = bundle.by_level[lv]
        for env, mat in (("PVE", bundle.mat_attr_pve), ("PVP", bundle.mat_attr_pvp)):
            dist = env_dist(le, env, "attr")
            atk = atk_utility_vec(dist, mat)
            hit = def_hit_vec(dist, mat)
            result[env]["attr_attacker"][lv] = {
                bundle.attr_types[i]: float(atk[i]) for i in range(len(bundle.attr_types))
            }
            result[env]["attr_defender"][lv] = {
                bundle.attr_types[i]: float(hit[i]) for i in range(len(bundle.attr_types))
            }
        result["综合"]["attr_attacker"][lv] = _mix_dict(
            result["PVE"]["attr_attacker"][lv],
            result["PVP"]["attr_attacker"][lv],
            le.beta_pve, le.beta_pvp,
        )
        result["综合"]["attr_defender"][lv] = _mix_dict(
            result["PVE"]["attr_defender"][lv],
            result["PVP"]["attr_defender"][lv],
            le.beta_pve, le.beta_pvp,
        )
    return result


def calc_weapon_size_utility(bundle: EnvBundle) -> Dict:
    """武器对体型分布的期望乘区. 综合 = β 加权 (已归一)。缺键已在 to_ndarray fail。"""
    result = {"PVE": {}, "PVP": {}, "综合": {}}
    for lv in bundle.levels:
        le = bundle.by_level[lv]
        for env, mat in (("PVE", bundle.mat_size_pve), ("PVP", bundle.mat_size_pvp)):
            size = env_dist(le, env, "size")
            # mat: weapon × size → util_w = (mat @ size)[w]
            util = mat @ size
            result[env][lv] = {
                bundle.weapon_types[i]: round(float(util[i]), 4)
                for i in range(len(bundle.weapon_types))
            }
        result["综合"][lv] = {
            w: round(_mix_scalar(
                result["PVE"][lv][w], result["PVP"][lv][w], le.beta_pve, le.beta_pvp
            ), 4)
            for w in bundle.weapon_types
        }
    return result


def calc_size_strength_utility(bundle: EnvBundle) -> Dict:
    """体型强度用效用: 武器 meta 打该体型的挨打量 (越大越疼)。

    PVE/PVP 均用该等级玩家侧武器分布 (流派 meta × 流派武器面板); 缺数据才 fail。
    强度排名侧会对挨打量取倒数。
    """
    result = {"PVE": {}, "PVP": {}, "综合": {}}
    n_w = len(bundle.weapon_types)
    for lv in bundle.levels:
        le = bundle.by_level[lv]
        if le.pve_weapon is None or len(le.pve_weapon) != n_w:
            raise ValueError(
                f"{cfg.PRINT_PREFIX_WARN} Lv{lv} 缺 PVE 武器 meta "
                f"(应由分等级流派×武器面板派生), 不允许 1/N 等权兜底"
            )
        if le.pvp_weapon is None or len(le.pvp_weapon) != n_w:
            raise ValueError(
                f"{cfg.PRINT_PREFIX_WARN} Lv{lv} 缺 PVP 武器 meta, 不允许 1/N 等权兜底"
            )
        hit_pve = le.pve_weapon @ bundle.mat_size_pve
        hit_pvp = le.pvp_weapon @ bundle.mat_size_pvp
        result["PVE"][lv] = {
            bundle.size_types[i]: float(hit_pve[i]) for i in range(len(bundle.size_types))
        }
        result["PVP"][lv] = {
            bundle.size_types[i]: float(hit_pvp[i]) for i in range(len(bundle.size_types))
        }
        result["综合"][lv] = _mix_dict(
            result["PVE"][lv], result["PVP"][lv], le.beta_pve, le.beta_pvp
        )
    return result


def calc_race_utility(bundle: EnvBundle) -> Dict:
    """种族攻/守效用. RO 通常无种族克制矩阵 → 返回 None, 排名改用环境覆盖占比。"""
    if bundle.mat_race_pve is None or bundle.mat_race_pvp is None:
        return None
    result = {
        "PVE": {"attacker": {}, "defender": {}},
        "PVP": {"attacker": {}, "defender": {}},
        "综合": {"attacker": {}, "defender": {}},
    }
    for lv in bundle.levels:
        le = bundle.by_level[lv]
        for env, mat in (("PVE", bundle.mat_race_pve), ("PVP", bundle.mat_race_pvp)):
            dist = env_dist(le, env, "race")
            atk = atk_utility_vec(dist, mat)
            hit = def_hit_vec(dist, mat)
            result[env]["attacker"][lv] = {
                bundle.race_types[i]: float(atk[i]) for i in range(len(bundle.race_types))
            }
            result[env]["defender"][lv] = {
                bundle.race_types[i]: float(hit[i]) for i in range(len(bundle.race_types))
            }
        result["综合"]["attacker"][lv] = _mix_dict(
            result["PVE"]["attacker"][lv], result["PVP"]["attacker"][lv],
            le.beta_pve, le.beta_pvp,
        )
        result["综合"]["defender"][lv] = _mix_dict(
            result["PVE"]["defender"][lv], result["PVP"]["defender"][lv],
            le.beta_pve, le.beta_pvp,
        )
    return result


def _playway_build_weights(playway_dist: dict, weights: dict, real_builds: list, lv: int) -> dict:
    """多玩法按 playway 权重加权后的流派分布 (已归一)。"""
    acc = {b: 0.0 for b in real_builds}
    w_sum = 0.0
    for pw, pw_dist in playway_dist.items():
        if lv not in pw_dist:
            continue
        pw_w = float(weights.get(pw, 0.0))
        if pw_w <= 0 and len(playway_dist) == 1:
            pw_w = 1.0
        dist = pw_dist[lv]
        n = min(len(real_builds), len(dist))
        local = {real_builds[i]: float(dist[i]) for i in range(n)}
        s = sum(local.values())
        if s <= 0:
            continue
        for b, v in local.items():
            acc[b] += pw_w * (v / s)
        w_sum += pw_w
    if w_sum <= 0:
        raise ValueError(f"{cfg.PRINT_PREFIX_WARN} Lv{lv} 玩法权重全 0")
    total = sum(acc.values())
    if total <= 0:
        raise ValueError(f"{cfg.PRINT_PREFIX_WARN} Lv{lv} 流派分布 sum≤0")
    return {b: v / total for b, v in acc.items()}


def calc_four_quadrant(bundle: EnvBundle) -> Dict:
    """PVE/PVP/综合 × 攻/守 标量 (玩法加权玩家属性 vs 环境)。"""
    result = {
        "PVE": {"attacker": {}, "defender": {}},
        "PVP": {"attacker": {}, "defender": {}},
        "综合": {"attacker": {}, "defender": {}},
    }
    if len(bundle.real_builds) <= 1:
        print(f"{cfg.PRINT_PREFIX_WARN} builds≤1, 四象限跳过")
        return result

    for lv in bundle.levels:
        le = bundle.by_level[lv]
        # PVE
        pve_bd = _playway_build_weights(
            bundle.pve_playway_dist, bundle.pve_weights, bundle.real_builds, lv
        )
        monster = le.pve_attr
        mat = bundle.mat_attr_pve
        atk_v = atk_utility_vec(monster, mat)
        pve_atk = pve_def = 0.0
        for b, bw in pve_bd.items():
            ba = bundle.build_attr[b]
            pve_atk += bw * float(ba @ atk_v)
            pve_def += bw * expected_util(monster, ba, mat)
        result["PVE"]["attacker"][lv] = pve_atk
        result["PVE"]["defender"][lv] = pve_def

        # PVP
        pvp_bd = _playway_build_weights(
            bundle.pvp_playway_dist, bundle.pvp_weights, bundle.real_builds, lv
        )
        meta = np.zeros(len(bundle.attr_types))
        for b, bw in pvp_bd.items():
            meta += bw * bundle.build_attr[b]
        meta = meta / meta.sum() if meta.sum() > 0 else meta
        matp = bundle.mat_attr_pvp
        env_atk = atk_utility_vec(meta, matp)
        env_hit = def_hit_vec(meta, matp)
        pvp_atk = pvp_def = 0.0
        for b, bw in pvp_bd.items():
            ba = bundle.build_attr[b]
            pvp_atk += bw * float(ba @ env_atk)
            pvp_def += bw * float(ba @ env_hit)
        result["PVP"]["attacker"][lv] = pvp_atk
        result["PVP"]["defender"][lv] = pvp_def

        result["综合"]["attacker"][lv] = _mix_scalar(pve_atk, pvp_atk, le.beta_pve, le.beta_pvp)
        result["综合"]["defender"][lv] = _mix_scalar(pve_def, pvp_def, le.beta_pve, le.beta_pvp)

    cfg.qprint(f"{cfg.PRINT_PREFIX_QUAD} 场景属性乘区·攻守")
    return result

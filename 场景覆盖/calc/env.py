# env.py — EnvBundle: 权重链 + 每等级 PVE/PVP/综合环境（全工具只算一次）
"""
权重链:
  场景行 Q = V × α → 等级内 E_pve / E_pvp
  综合 E_mix = β_pve×E_pve + β_pvp×E_pvp  (β 来自 Excel 等级曲线, 已归一)
  终身用 level_weights W_L
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from 场景覆盖 import config as cfg
from .matrix_ops import normalize_dist, to_ndarray


@dataclass
class LevelEnv:
    level: int
    beta_pve: float
    beta_pvp: float
    beta_hat_pve: float  # 场景行推导, 供对照
    pve_attr: np.ndarray
    pve_race: np.ndarray
    pve_size: np.ndarray
    pvp_attr: np.ndarray
    pvp_race: np.ndarray
    pvp_size: np.ndarray
    pvp_weapon: Optional[np.ndarray]
    pve_weapon: Optional[np.ndarray]  # 玩家侧 PVE 武器 meta (流派加权, 非等权)
    mix_attr: np.ndarray
    mix_race: np.ndarray
    mix_size: np.ndarray


@dataclass
class EnvBundle:
    levels: List[int]
    level_weights: Dict[int, float]  # W_L, sum=1
    attr_types: List[str]
    race_types: List[str]
    size_types: List[str]
    weapon_types: List[str]
    mat_attr_pve: np.ndarray
    mat_attr_pvp: np.ndarray
    mat_size_pve: np.ndarray  # weapon × size
    mat_size_pvp: np.ndarray
    mat_race_pve: Optional[np.ndarray] = None
    mat_race_pvp: Optional[np.ndarray] = None
    by_level: Dict[int, LevelEnv] = field(default_factory=dict)
    beta_warnings: List[str] = field(default_factory=list)
    real_builds: List[str] = field(default_factory=list)
    build_attr: Dict[str, np.ndarray] = field(default_factory=dict)
    build_race: Dict[str, str] = field(default_factory=dict)
    build_size: Dict[str, str] = field(default_factory=dict)
    pve_playway_dist: dict = field(default_factory=dict)
    pvp_playway_dist: dict = field(default_factory=dict)
    pve_weights: dict = field(default_factory=dict)
    pvp_weights: dict = field(default_factory=dict)
    meta_note: str = ""


def _weighted_scene_dist(scenarios: list, key: str, n: int, lv: int) -> np.ndarray:
    if not scenarios:
        raise ValueError(
            f"{cfg.PRINT_PREFIX_WARN} Lv{lv} 场景列表为空, 不允许均匀兜底"
        )
    total = sum(s["weight"] for s in scenarios)
    if total <= 0:
        raise ValueError(f"{cfg.PRINT_PREFIX_WARN} Lv{lv} 场景 weight 总和≤0")
    out = np.zeros(n)
    for s in scenarios:
        v = s[key]
        arr = v if isinstance(v, np.ndarray) else np.asarray(v, dtype=float)
        out += (s["weight"] / total) * arr
    return normalize_dist(out, f"Lv{lv}.{key}")


def _require_beta(pw: dict, lv: int) -> tuple:
    if pw is None:
        raise ValueError(
            f"{cfg.PRINT_PREFIX_WARN} Lv{lv} per_level_weights 缺失, "
            f"业务真值应写入场景覆盖等级 PVE/PVP 价值占比"
        )
    w_pve, w_pvp = pw.get("pve_weight"), pw.get("pvp_weight")
    if w_pve is None or w_pvp is None:
        raise ValueError(f"{cfg.PRINT_PREFIX_WARN} Lv{lv} 缺 pve_weight/pvp_weight")
    total = w_pve + w_pvp
    if total <= cfg.PROGRAM_EPS:
        raise ValueError(f"{cfg.PRINT_PREFIX_WARN} Lv{lv} pve+pvp={total}≤0")
    return w_pve / total, w_pvp / total


def _norm_build_attr(name: str, arr: np.ndarray) -> np.ndarray:
    s = float(arr.sum())
    if s <= 0:
        raise ValueError(f"{cfg.PRINT_PREFIX_WARN} 流派{name} 属性分布 sum≤0")
    if abs(s - 1.0) > cfg.USER_EPS:
        raise ValueError(
            f"{cfg.PRINT_PREFIX_WARN} 流派{name} 属性分布 sum={s:.3f}≠1.0"
        )
    return arr


def build_env_bundle(data: dict) -> EnvBundle:
    """从 load_all() 的 data 构建 EnvBundle。"""
    levels = sorted(data.get("levels_pve", []))
    if not levels:
        raise ValueError(f"{cfg.PRINT_PREFIX_WARN} levels_pve 为空")

    attr_types = list(data["attr_types"])
    race_types = list(data["race_types"])
    size_types = list(data["size_types"])
    weapon_types = list(data["weapon_types"])

    mat_attr_pve = to_ndarray(data["attr_matrix_pve"], attr_types, attr_types)
    mat_attr_pvp = to_ndarray(data["attr_matrix_pvp"], attr_types, attr_types)
    mat_size_pve = to_ndarray(data["size_matrix_pve"], weapon_types, size_types)
    mat_size_pvp = to_ndarray(data["size_matrix_pvp"], weapon_types, size_types)

    mat_race_pve = mat_race_pvp = None
    race_m_pve = data.get("race_matrix_pve")
    race_m_pvp = data.get("race_matrix_pvp")
    if race_m_pve:
        mat_race_pve = to_ndarray(race_m_pve, race_types, race_types)
    if race_m_pvp:
        mat_race_pvp = to_ndarray(race_m_pvp, race_types, race_types)

    level_weights = dict(data.get("level_weights") or data.get("level_lifecycle_weights") or {})
    if not level_weights:
        raise cfg.ConfigDriftError("level_weights 为空 — 应写入场景覆盖等级价值占比")
    tw = sum(level_weights.values())
    if tw <= 0:
        raise cfg.ConfigDriftError("level_weights 总和≤0")
    level_weights = {lv: w / tw for lv, w in level_weights.items()}

    panel = data["build_panel"]
    elem_dmg = panel.get("elem_dmg", {})
    builds = panel.get("build_names", [])
    real_builds = [b for b in builds if b in elem_dmg and b != cfg.STANDARD_BUILD_NAME]
    if not real_builds:
        real_builds = [b for b in builds if b in elem_dmg]

    build_attr = {}
    for b in real_builds:
        ba = np.array([float(elem_dmg[b].get(a, 0.0)) for a in attr_types], dtype=float)
        build_attr[b] = _norm_build_attr(b, ba)

    build_race = dict(panel.get("species_data", {}))
    build_size = dict(panel.get("size_data", {}))

    pve_config = data["pve_config"]
    pvp_composite = data.get("pvp_composite") or {}
    pve_player = data.get("pve_composite") or {}  # 玩家侧 PVE 流派派生 (含武器)
    per_level = data.get("per_level_weights") or {}
    # β̂：excel 等级曲线覆盖前的场景行推导口径，供体检双源对照（2026-07-30 贯通）
    per_level_hat = data.get("per_level_weights_hat") or {}

    beta_warnings = []
    by_level: Dict[int, LevelEnv] = {}

    for lv in levels:
        # 怪物侧三维: 场景价值 × 地图遭遇
        pve_attr = _weighted_scene_dist(pve_config.get(lv, []), "attr", len(attr_types), lv)
        pve_race = _weighted_scene_dist(pve_config.get(lv, []), "race", len(race_types), lv)
        pve_size = _weighted_scene_dist(pve_config.get(lv, []), "size", len(size_types), lv)

        if lv not in pvp_composite:
            raise ValueError(f"{cfg.PRINT_PREFIX_WARN} Lv{lv} pvp_composite 缺失")
        pc = pvp_composite[lv]
        for dim in ("attr", "race", "size"):
            if dim not in pc or np.asarray(pc[dim]).sum() <= 0:
                raise ValueError(f"{cfg.PRINT_PREFIX_WARN} Lv{lv} pvp_composite.{dim} 缺失或全0")
        pvp_attr = normalize_dist(np.asarray(pc["attr"], dtype=float), f"Lv{lv}.pvp_attr")
        pvp_race = normalize_dist(np.asarray(pc["race"], dtype=float), f"Lv{lv}.pvp_race")
        pvp_size = normalize_dist(np.asarray(pc["size"], dtype=float), f"Lv{lv}.pvp_size")
        pvp_weapon = None
        if "weapon_dist" in pc and np.asarray(pc["weapon_dist"]).sum() > 0:
            pvp_weapon = normalize_dist(
                np.asarray(pc["weapon_dist"], dtype=float), f"Lv{lv}.pvp_weapon"
            )

        pve_weapon = None
        if lv in pve_player and "weapon_dist" in pve_player[lv]:
            wd = np.asarray(pve_player[lv]["weapon_dist"], dtype=float)
            if wd.sum() > 0:
                pve_weapon = normalize_dist(wd, f"Lv{lv}.pve_weapon")

        beta_pve, beta_pvp = _require_beta(per_level.get(lv), lv)
        hat_w = per_level_hat.get(lv) or {}
        hat = float(hat_w.get("pve_weight", beta_pve))

        # 综合三维: 怪物PVE环境 × β + 玩家PVP环境 × β
        mix_attr = normalize_dist(beta_pve * pve_attr + beta_pvp * pvp_attr, f"Lv{lv}.mix_attr")
        mix_race = normalize_dist(beta_pve * pve_race + beta_pvp * pvp_race, f"Lv{lv}.mix_race")
        mix_size = normalize_dist(beta_pve * pve_size + beta_pvp * pvp_size, f"Lv{lv}.mix_size")

        by_level[lv] = LevelEnv(
            level=lv,
            beta_pve=beta_pve,
            beta_pvp=beta_pvp,
            beta_hat_pve=hat,
            pve_attr=pve_attr,
            pve_race=pve_race,
            pve_size=pve_size,
            pvp_attr=pvp_attr,
            pvp_race=pvp_race,
            pvp_size=pvp_size,
            pvp_weapon=pvp_weapon,
            pve_weapon=pve_weapon,
            mix_attr=mix_attr,
            mix_race=mix_race,
            mix_size=mix_size,
        )

    pve_pw = data.get("pve_playway_dist") or {}
    pvp_pw = data.get("pvp_playway_dist") or {}
    pvp_table = data.get("pvp_table") or {}
    if not pvp_pw and pvp_table:
        synth = {"__PVP_TABLE__": {}}
        for lv in levels:
            bw = (pvp_table.get(lv) or {}).get("build_weights") or {}
            dist = [float(bw.get(b, 0.0)) for b in real_builds]
            s = sum(dist)
            if s > 0:
                synth["__PVP_TABLE__"][lv] = [x / s for x in dist]
        if synth["__PVP_TABLE__"]:
            pvp_pw = synth
            data = {**data, "pvp_weights": {"__PVP_TABLE__": 1.0}}

    if not pvp_pw:
        raise ValueError(
            f"{cfg.PRINT_PREFIX_WARN} PVP 玩法分布缺失 (pvp_playway_dist + pvp_table 皆空)"
        )
    if not pve_pw:
        raise ValueError(f"{cfg.PRINT_PREFIX_WARN} PVE 玩法分布为空")

    meta_note = data.get("meta_note") or ""

    cfg.qprint(f"{cfg.PRINT_PREFIX_AGGREGATE} EnvBundle 就绪: {len(levels)} 等级"
               f"{(' | ' + meta_note) if meta_note else ''}")
    return EnvBundle(
        levels=levels,
        level_weights=level_weights,
        attr_types=attr_types,
        race_types=race_types,
        size_types=size_types,
        weapon_types=weapon_types,
        mat_attr_pve=mat_attr_pve,
        mat_attr_pvp=mat_attr_pvp,
        mat_size_pve=mat_size_pve,
        mat_size_pvp=mat_size_pvp,
        mat_race_pve=mat_race_pve,
        mat_race_pvp=mat_race_pvp,
        by_level=by_level,
        beta_warnings=beta_warnings,
        real_builds=real_builds,
        build_attr=build_attr,
        build_race=build_race,
        build_size=build_size,
        pve_playway_dist=pve_pw,
        pvp_playway_dist=pvp_pw,
        pve_weights=data.get("pve_weights") or {},
        pvp_weights=data.get("pvp_weights") or {},
        meta_note=meta_note,
    )


def env_dist(le: LevelEnv, env: str, dim: str) -> np.ndarray:
    """env in PVE/PVP/综合; dim in attr/race/size。"""
    key = {"PVE": "pve", "PVP": "pvp", "综合": "mix"}[env]
    return getattr(le, f"{key}_{dim}")


def mat_for(bundle: EnvBundle, dim: str, env: str) -> np.ndarray:
    """dim: attr|size|race; env: PVE|PVP|综合 → 综合默认用 PVE 矩阵做展示时可再混。"""
    if dim == "attr":
        return bundle.mat_attr_pve if env == "PVE" else bundle.mat_attr_pvp if env == "PVP" else None
    if dim == "size":
        return bundle.mat_size_pve if env == "PVE" else bundle.mat_size_pvp if env == "PVP" else None
    if dim == "race":
        return bundle.mat_race_pve if env == "PVE" else bundle.mat_race_pvp if env == "PVP" else None
    raise KeyError(dim)

# ranking.py — 五维看板: 乘区(真实) + 指数(相对) + 偏离/差值
"""
展示术语见 config 顶部注释。计算口径：

  输出乘区 / 承伤乘区 = 克制矩阵期望（未维内归一）
  平衡/克制/抗性指数 = 维内均值归一（1.0=平均），供 PASS/WARN
  偏离均值% = (指数−1)×100
  相对均值差(体型) = mean_hit − hit（正=比平均少挨）

  流派/属性 = 先 W_L 加权攻/守，再算 BFI 风格指数
  体型 = 先 W_L 加权承伤，再算差值与抗性指数
  武器/种族占比 = 先逐级真实量，再 W_L 加权
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from 场景覆盖 import config as cfg
from .env import EnvBundle


def _status(dim: str, value: float) -> Tuple[str, object]:
    th = (cfg.RANK_REL_THRESHOLDS or {}).get(dim)
    if not th:
        return "—", None
    lo, hi = th["pass"]
    if lo <= value <= hi:
        return "PASS", cfg.FILL_PASS
    wlo, whi = th["warn"]
    if wlo <= value <= whi:
        return "WARN", cfg.FILL_WARN
    return "FAIL", cfg.FILL_FAIL


def _mean_rel(scores: Dict[str, float], label: str) -> Dict[str, float]:
    if not scores:
        raise ValueError(f"{cfg.PRINT_PREFIX_WARN} {label} 排名分数为空")
    m = sum(scores.values()) / len(scores)
    if m <= 0:
        raise ValueError(f"{cfg.PRINT_PREFIX_WARN} {label} 排名均值≤0")
    return {k: v / m for k, v in scores.items()}


def _bfi_style_scores(atk: Dict[str, float], deff: Dict[str, float]) -> Dict[str, float]:
    keys = list(atk.keys())
    avg_a = sum(atk[k] for k in keys) / len(keys)
    avg_d = sum(deff[k] for k in keys) / len(keys)
    if avg_a <= 0 or avg_d <= 0:
        raise ValueError(f"{cfg.PRINT_PREFIX_WARN} 攻/守均值≤0, 无法算强度")
    out = {}
    for k in keys:
        if deff[k] <= cfg.PROGRAM_EPS:
            raise ValueError(f"{cfg.PRINT_PREFIX_WARN} {k} 守方效用≤0")
        out[k] = (atk[k] / avg_a) * (avg_d / deff[k])
    return out


def _cross_level_score(
    per_lv: Dict[int, Dict[str, float]], level_weights: Dict[int, float], label: str
) -> Dict[str, float]:
    """per_lv[lv][name] = 真实量; 按 W_L 加权。"""
    if not per_lv:
        raise ValueError(f"{cfg.PRINT_PREFIX_WARN} {label} 无等级数据")
    keys = list(next(iter(per_lv.values())).keys())
    acc = {k: 0.0 for k in keys}
    tw = 0.0
    for lv, d in per_lv.items():
        lw = float(level_weights.get(lv, 0.0))
        if lw <= 0:
            continue
        tw += lw
        for k in keys:
            acc[k] += lw * float(d.get(k, 0.0))
    if tw <= 0:
        raise ValueError(f"{cfg.PRINT_PREFIX_WARN} {label} level_weights 全0")
    return {k: v / tw for k, v in acc.items()}


def _row_atk_def(
    name: str,
    atk: float,
    deff: float,
    rel: float,
    dim: str,
) -> dict:
    """流派/属性行：输出乘区、承伤乘区、指数、偏离均值%。"""
    pct = (rel - 1.0) * 100.0
    status, fill = _status(dim, rel)
    return {
        "name": name,
        "atk": float(atk),
        "def": float(deff),
        "rel": float(rel),
        "vs_pct": float(pct),
        "status": status,
        "fill": fill,
    }


def _row_single(
    name: str,
    real: float,
    rel: float,
    vs_pct: float,
    dim: str,
) -> dict:
    """武器/种族/体型行：真实量、指数、偏离%或相对均值差。"""
    status, fill = _status(dim, rel)
    return {
        "name": name,
        "real": float(real),
        "rel": float(rel),
        "vs_pct": float(vs_pct),
        "status": status,
        "fill": fill,
    }


def build_all_rankings(
    bundle: EnvBundle,
    detailed: dict,
    size_weapon_util: dict,
    size_hit_util: dict,
    race_util: dict | None,
    bfi: dict,
    pure_dist: dict,
) -> dict:
    """
    返回:
      {
        "blocks": {build|elem|race|size|weapon: [row_dict, ...]},
        "race_mode": "matrix" | "coverage_share",
        "meta_note": str,
      }
    """
    lw = bundle.level_weights
    blocks = {}

    # ---- 流派 ----
    cross = bfi.get("跨等级综合") or {}
    build_raw = {
        b: d for b, d in cross.items() if b != cfg.STANDARD_BUILD_NAME
    }
    if not build_raw:
        raise ValueError(f"{cfg.PRINT_PREFIX_WARN} 流派跨等级 BFI 为空")
    build_scores = {b: float(d["bfi"]) for b, d in build_raw.items()}
    build_rel = _mean_rel(build_scores, "流派")
    blocks["build"] = _finalize_atk_def(
        {
            b: (float(build_raw[b]["attacker"]), float(build_raw[b]["defender"]), build_rel[b])
            for b in build_rel
        },
        "流派",
    )

    # ---- 属性 ----
    atk_acc: Dict[str, float] = {}
    def_acc: Dict[str, float] = {}
    tw_attr = 0.0
    for lv, atk_d in detailed.get("综合", {}).get("attr_attacker", {}).items():
        w = float(lw.get(lv, 0.0))
        if w <= 0:
            continue
        def_d = detailed["综合"]["attr_defender"][lv]
        for k, v in atk_d.items():
            atk_acc[k] = atk_acc.get(k, 0.0) + w * float(v)
            def_acc[k] = def_acc.get(k, 0.0) + w * float(def_d.get(k, 0.0))
        tw_attr += w
    if not atk_acc or tw_attr <= 0:
        raise ValueError(f"{cfg.PRINT_PREFIX_WARN} 属性跨级加权无数据")
    atk_w = {k: v / tw_attr for k, v in atk_acc.items()}
    def_w = {k: v / tw_attr for k, v in def_acc.items()}
    attr_life = _bfi_style_scores(atk_w, def_w)
    attr_rel = _mean_rel(attr_life, "属性")
    blocks["elem"] = _finalize_atk_def(
        {k: (atk_w[k], def_w[k], attr_rel[k]) for k in attr_rel},
        "属性",
    )

    # ---- 武器 ----
    per_lv_w = {}
    for lv, d in (size_weapon_util.get("综合") or {}).items():
        per_lv_w[lv] = {w: float(v) for w, v in d.items()}
    w_life = _cross_level_score(per_lv_w, lw, "武器")
    w_rel = _mean_rel(w_life, "武器")
    blocks["weapon"] = _finalize_single(
        {k: (w_life[k], w_rel[k], (w_rel[k] - 1.0) * 100.0) for k in w_rel},
        "武器",
    )

    # ---- 体型 ----
    per_lv_hit = {}
    for lv, d in (size_hit_util.get("综合") or {}).items():
        per_lv_hit[lv] = {}
        for sz, hit in d.items():
            if float(hit) <= cfg.PROGRAM_EPS:
                raise ValueError(f"{cfg.PRINT_PREFIX_WARN} 体型{sz} 挨打量≤0")
            per_lv_hit[lv][sz] = float(hit)
    hit_life = _cross_level_score(per_lv_hit, lw, "体型承伤")
    mean_hit = sum(hit_life.values()) / len(hit_life)
    if mean_hit <= cfg.PROGRAM_EPS:
        raise ValueError(f"{cfg.PRINT_PREFIX_WARN} 体型承伤均值≤0")
    sz_scores = {sz: 1.0 / hit for sz, hit in hit_life.items()}
    sz_rel = _mean_rel(sz_scores, "体型")
    blocks["size"] = _finalize_single(
        {
            sz: (
                hit_life[sz],
                sz_rel[sz],
                mean_hit - hit_life[sz],
            )
            for sz in sz_rel
        },
        "体型",
        sort_by_rel=True,
    )

    # ---- 种族 ----
    if race_util is not None:
        race_mode = "matrix"
        atk_acc_r: Dict[str, float] = {}
        def_acc_r: Dict[str, float] = {}
        tw_r = 0.0
        for lv, atk_d in race_util["综合"]["attacker"].items():
            w = float(lw.get(lv, 0.0))
            if w <= 0:
                continue
            def_d = race_util["综合"]["defender"][lv]
            for k, v in atk_d.items():
                atk_acc_r[k] = atk_acc_r.get(k, 0.0) + w * float(v)
                def_acc_r[k] = def_acc_r.get(k, 0.0) + w * float(def_d.get(k, 0.0))
            tw_r += w
        if not atk_acc_r or tw_r <= 0:
            raise ValueError(f"{cfg.PRINT_PREFIX_WARN} 种族矩阵跨级无数据")
        atk_rw = {k: v / tw_r for k, v in atk_acc_r.items()}
        def_rw = {k: v / tw_r for k, v in def_acc_r.items()}
        r_life = _bfi_style_scores(atk_rw, def_rw)
        r_rel = _mean_rel(r_life, "种族")
        blocks["race"] = _finalize_atk_def(
            {k: (atk_rw[k], def_rw[k], r_rel[k]) for k in r_rel},
            "种族",
        )
    else:
        race_mode = "coverage_share"
        per_lv_r = {}
        for lv in pure_dist:
            per_lv_r[lv] = {
                k: float(v) for k, v in pure_dist[lv]["综合"]["种族"].items()
            }
        r_life = _cross_level_score(per_lv_r, lw, "种族场景占比")
        r_rel = _mean_rel(r_life, "种族场景占比")
        blocks["race"] = _finalize_single(
            {k: (r_life[k], r_rel[k], (r_rel[k] - 1.0) * 100.0) for k in r_rel},
            "种族",
        )

    return {
        "blocks": blocks,
        "race_mode": race_mode,
        "meta_note": bundle.meta_note,
    }


def _finalize_atk_def(
    data: Dict[str, Tuple[float, float, float]], dim: str
) -> List[dict]:
    rows = []
    for name, (atk, deff, rel) in sorted(data.items(), key=lambda x: (-x[1][2], x[0])):
        rows.append(_row_atk_def(name, atk, deff, rel, dim))
    return rows


def 命中层相对(sim_hits: Dict[str, dict]) -> dict:
    """用解释器最终伤害做相对均值，不着色、不发明 PASS 带。"""
    vals: Dict[str, float] = {}
    errors: Dict[str, str] = {}
    for name, row in (sim_hits or {}).items():
        if not isinstance(row, dict):
            continue
        if row.get("error"):
            errors[name] = str(row["error"])
            continue
        dmg = row.get("最终伤害")
        if not isinstance(dmg, (int, float)):
            errors[name] = "无最终伤害"
            continue
        vals[name] = float(dmg)
    if not vals:
        raise ValueError("命中层无最终伤害，无法排名")
    mean = sum(vals.values()) / len(vals)
    ranked = sorted(vals.items(), key=lambda x: -x[1])
    return {
        "均值最终伤害": mean,
        "相对均值": {k: v / mean for k, v in vals.items()},
        "排序": [{"构筑": k, "最终伤害": v, "相对均值": v / mean} for k, v in ranked],
        "误差": errors,
        "着色": "无（公式参数无 RANK 带）",
    }


def _finalize_single(
    data: Dict[str, Tuple[float, float, float]],
    dim: str,
    sort_by_rel: bool = True,
) -> List[dict]:
    rows = []
    key_fn = (lambda x: (-x[1][1], x[0])) if sort_by_rel else (lambda x: (-x[1][0], x[0]))
    for name, (real, rel, vs_pct) in sorted(data.items(), key=key_fn):
        rows.append(_row_single(name, real, rel, vs_pct, dim))
    return rows

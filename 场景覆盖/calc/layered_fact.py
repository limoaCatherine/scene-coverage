# -*- coding: utf-8 -*-
"""按等级×模式×玩法×流派算克制效用。"""
from __future__ import annotations

from collections import defaultdict

import numpy as np

from 场景覆盖 import config as cfg
from 场景覆盖.calc.matrix_ops import atk_utility_vec, expected_util, to_ndarray
from 场景覆盖.load.layout_v2 import _maps_by_play, active_tier


def _bfi(atk: float, deff: float, avg_atk: float, avg_def: float) -> float:
    if deff <= cfg.PROGRAM_EPS or avg_atk <= 0 or avg_def <= 0:
        raise ValueError("BFI 分母为 0")
    return (atk / avg_atk) * (avg_def / deff)


def playway_pve_env(pve_config: dict, lv: int, play: str, n_attr: int, n_race: int, n_size: int):
    rows = [s for s in pve_config.get(lv, []) if s.get("type") == play]
    if not rows:
        return None
    w = sum(s["weight"] for s in rows)
    if w <= 0:
        return None
    attr = np.zeros(n_attr)
    race = np.zeros(n_race)
    size = np.zeros(n_size)
    for s in rows:
        q = s["weight"] / w
        attr += q * np.asarray(s["attr"], dtype=float)
        race += q * np.asarray(s["race"], dtype=float)
        size += q * np.asarray(s["size"], dtype=float)
    return {"attr": attr, "race": race, "size": size}


def calc_layered_facts(
    scene: dict,
    mat_attr_pve,
    mat_attr_pvp,
    mat_size_pve=None,
    weapon_types=None,
) -> dict:
    panel = scene["build_panel"]
    builds = scene["weights"]["builds"]
    plays = scene["weights"]["play_names"]
    cube = scene["weights"]["cube"]
    attr_types = scene["attr_types"]
    elem = panel["elem_dmg"]
    build_attr = {}
    for b in builds:
        vec = np.array([float(elem[b].get(a, 0.0)) for a in attr_types], dtype=float)
        s = float(vec.sum())
        if s <= 0:
            raise ValueError(f"流派 {b} 属性分布和≤0")
        build_attr[b] = vec / s

    n_a, n_r, n_s = len(attr_types), len(scene["race_types"]), len(scene["size_types"])
    if not hasattr(mat_attr_pve, "ndim"):
        mat_attr_pve = to_ndarray(mat_attr_pve, attr_types, attr_types)
    if not hasattr(mat_attr_pvp, "ndim"):
        mat_attr_pvp = to_ndarray(mat_attr_pvp, attr_types, attr_types)
    prefs = scene["prefs"]["prefs"]
    facts = []
    by_lv = defaultdict(lambda: defaultdict(lambda: {"atk": 0.0, "defn": 0.0, "w": 0.0, "tw": 0.0, "tu": 0.0}))
    by_play = defaultdict(lambda: defaultdict(lambda: {"atk": 0.0, "defn": 0.0, "w": 0.0, "tw": 0.0, "tu": 0.0}))
    by_mode = defaultdict(lambda: defaultdict(lambda: {"atk": 0.0, "defn": 0.0, "w": 0.0, "tw": 0.0, "tu": 0.0}))
    by_map_raw = defaultdict(lambda: defaultdict(lambda: {"atk": 0.0, "defn": 0.0, "w": 0.0, "tw": 0.0, "tu": 0.0}))

    levels_blk = scene["levels_blk"]
    shares = scene["play"]["shares"]
    play_meta = {p["name"]: p for p in scene["play"]["playways"]}
    by_pw = _maps_by_play(scene["maps_enc"])
    encounters = scene["maps_enc"]["encounters"]
    share_sum = {lv: sum(shares[n][lv] for n in plays) for lv in range(1, 61)}

    for lv in range(1, 61):
        denom = share_sum[lv]
        if denom <= 0:
            continue
        for play in plays:
            meta = play_meta[play]
            share = shares[play][lv]
            if share <= 0 or play not in prefs:
                continue
            tier = active_tier(by_pw.get(play) or [], lv)
            if not tier:
                continue
            base_v = levels_blk["value"][lv] * share / denom
            base_t = levels_blk["time"][lv] * share / denom
            for mode, pct in (("PVE", meta["pve"]), ("PVP", meta["pvp"])):
                if pct <= 0:
                    continue
                mat = mat_attr_pve if mode == "PVE" else mat_attr_pvp
                opp = None
                if mode == "PVP":
                    acc = np.zeros(n_a)
                    for b, p in prefs[play].items():
                        if b in build_attr:
                            acc += p * build_attr[b]
                    if acc.sum() > 0:
                        opp = acc / acc.sum()
                for m, frac in tier:
                    monster = opp
                    if mode == "PVE":
                        enc = encounters.get(m["name"])
                        if enc is None:
                            continue
                        monster = np.asarray(enc["attr"], dtype=float)
                    if monster is None or float(np.asarray(monster).sum()) <= 0:
                        continue
                    atk_v = atk_utility_vec(monster, mat)
                    for b in builds:
                        pref = prefs[play].get(b, 0.0)
                        if pref <= 0:
                            continue
                        wv = base_v * pct * frac * pref
                        wt = base_t * pct * frac * pref
                        if wv + wt <= cfg.PROGRAM_EPS:
                            continue
                        atk = float(build_attr[b] @ atk_v)
                        deff = expected_util(monster, build_attr[b], mat)
                        rec = {
                            "等级": lv,
                            "模式": mode,
                            "玩法": play,
                            "地图": m["name"],
                            "流派": b,
                            "价值权重": wv,
                            "时长权重": wt,
                            "克制效用": atk,
                            "收益效用": wv * atk,
                            "时间效用": wt * atk,
                            "输出乘区": atk,
                            "承伤乘区": deff,
                        }
                        facts.append(rec)
                        for bucket, dim in (
                            (by_lv[lv][b], None),
                            (by_play[play][b], None),
                            (by_mode[mode][b], None),
                            (by_map_raw[m["name"]][b], None),
                        ):
                            bucket["atk"] += atk * wv
                            bucket["defn"] += deff * wv
                            bucket["w"] += wv
                            bucket["tw"] += wt
                            bucket["tu"] += wt * atk

    def _roll(store):
        out = {}
        for dim, builds_d in store.items():
            out[dim] = {}
            for b, d in builds_d.items():
                if d["w"] <= 0:
                    continue
                out[dim][b] = {
                    "输出乘区": d["atk"] / d["w"],
                    "承伤乘区": d["defn"] / d["w"],
                    "价值权重": d["w"],
                    "时长权重": d.get("tw", 0.0),
                    "时间效用": d.get("tu", 0.0),
                    "收益效用": d["atk"],
                }
            if not out[dim]:
                continue
            aa = sum(v["输出乘区"] for v in out[dim].values()) / len(out[dim])
            ad = sum(v["承伤乘区"] for v in out[dim].values()) / len(out[dim])
            for b, v in out[dim].items():
                v["平衡指数"] = _bfi(v["输出乘区"], v["承伤乘区"], aa, ad)
        return out

    maps = scene["maps_enc"]["maps"]
    encounters = scene["maps_enc"]["encounters"]
    map_meta = {m["name"]: {"玩法": m["playway"], "等级": int(m["level"])} for m in maps}

    # 三维：元素=克制矩阵；体型=武器×体型矩阵；种族无矩阵则只出环境占比+流派三维权重
    by_elem_raw = defaultdict(lambda: defaultdict(lambda: {"atk": 0.0, "defn": 0.0, "w": 0.0}))
    for i, aname in enumerate(attr_types):
        monster = np.zeros(n_a)
        monster[i] = 1.0
        atk_v = atk_utility_vec(monster, mat_attr_pve)
        for b in builds:
            atk = float(build_attr[b] @ atk_v)
            deff = expected_util(monster, build_attr[b], mat_attr_pve)
            by_elem_raw[aname][b] = {"atk": atk, "defn": deff, "w": 1.0}

    by_size_raw = defaultdict(lambda: defaultdict(lambda: {"atk": 0.0, "defn": 0.0, "w": 0.0}))
    size_types = scene["size_types"]
    panel = scene["build_panel"]
    wep_names = list(weapon_types or panel.get("weapon_types") or [])
    if mat_size_pve is not None and wep_names:
        mat_s = to_ndarray(mat_size_pve, wep_names, size_types) if not hasattr(mat_size_pve, "ndim") else mat_size_pve
        for b in builds:
            wmix = np.array([float(panel["weapon"].get(b, {}).get(w, 0.0)) for w in wep_names], dtype=float)
            s = float(wmix.sum())
            if s <= 0:
                continue
            wmix = wmix / s
            vs = wmix @ mat_s
            for i, sname in enumerate(size_types):
                by_size_raw[sname][b] = {"atk": float(vs[i]), "defn": float(vs[i]), "w": 1.0}

    race_types = scene["race_types"]
    race_env = {r: 0.0 for r in race_types}
    size_env = {s: 0.0 for s in size_types}
    for m in maps:
        enc = encounters.get(m["name"])
        if enc is None:
            continue
        rvec = np.asarray(enc["race"], dtype=float)
        svec = np.asarray(enc["size"], dtype=float)
        for i, rname in enumerate(race_types):
            race_env[rname] += float(rvec[i])
        for i, sname in enumerate(size_types):
            size_env[sname] += float(svec[i])
    tot_re = sum(race_env.values())
    if tot_re > 0:
        race_env = {k: v / tot_re for k, v in race_env.items()}
    tot_se = sum(size_env.values())
    if tot_se > 0:
        size_env = {k: v / tot_se for k, v in size_env.items()}
    race_dist = panel.get("race_dist") or {}
    size_dist = panel.get("size_dist") or {}

    return {
        "facts": facts,
        "by_level": _roll(by_lv),
        "by_playway": _roll(by_play),
        "by_mode": _roll(by_mode),
        "by_map": _roll(by_map_raw),
        "by_elem": _roll(by_elem_raw),
        "by_size": _roll(by_size_raw) if by_size_raw else {},
        "map_meta": map_meta,
        "race_env": race_env,
        "size_env": size_env,
        "race_dist": race_dist,
        "size_dist": size_dist,
        "race_types": race_types,
        "size_types": size_types,
        "attr_types": attr_types,
        "builds": builds,
        "play_names": plays,
    }

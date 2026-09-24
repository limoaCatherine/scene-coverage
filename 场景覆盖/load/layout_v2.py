# -*- coding: utf-8 -*-
"""读横排 1–60「场景覆盖」块，合成等级×模式×玩法×流派权重。"""
from __future__ import annotations

from collections import defaultdict

import numpy as np

from 场景覆盖 import config as cfg
from 场景覆盖.config import ConfigDriftError
from .scenes import _safe_float


LEVELS = list(range(1, 61))
BLOCK_NAMES = ("等级", "玩法", "地图", "遭遇", "偏好", "权重校验", "流派三维")
ATTRS = ["无属性", "火属性", "水属性", "风属性", "地属性", "毒属性", "圣属性", "暗属性", "念属性", "不死属性"]
RACES = ["人形", "动物", "植物", "昆虫", "鱼贝", "恶魔", "天使", "龙", "不死", "无形"]
SIZES = ["小体型", "中体型", "大体型"]


def _blank(v) -> bool:
    return v is None or (isinstance(v, str) and not str(v).strip())


def _r3_map(ws) -> dict:
    return cfg._build_inherit_map(ws, 3)


def find_block(ws, name: str) -> tuple[int, int]:
    r1_map = _r3_map(ws)
    return cfg.block_col_span(ws, name, r1_map=r1_map)


def _header_col(ws, start: int, end: int, name: str) -> int:
    want = str(name).strip()
    for c in range(start, end + 1):
        v = ws.cell(4, c).value
        if v is not None and str(v).strip() == want:
            return c
    raise ConfigDriftError(f"块内未找到表头 {name!r} (C{start}-C{end})")


def _data_rows(ws, key_col: int, start=5, stop=None):
    last = stop or (ws.max_row or start)
    empty = 0
    for r in range(start, last + 1):
        v = ws.cell(r, key_col).value
        if _blank(v):
            empty += 1
            if empty >= 2:
                break
            continue
        empty = 0
        yield r, v


def read_levels(ws) -> dict:
    s, e = find_block(ws, "等级")
    c_lv = _header_col(ws, s, e, "等级")
    c_val = _header_col(ws, s, e, "价值占比")
    c_time = _header_col(ws, s, e, "时长占比")
    value, time = {}, {}
    for r, v in _data_rows(ws, c_lv):
        lv = int(float(v))
        value[lv] = _safe_float(ws.cell(r, c_val).value)
        time[lv] = _safe_float(ws.cell(r, c_time).value)
    if set(value) != set(LEVELS):
        raise ConfigDriftError(f"等级块应有 1–60，实际 {sorted(value)[:8]}…共{len(value)}")
    sv, st = sum(value.values()), sum(time.values())
    if sv <= 0 or st <= 0:
        raise ConfigDriftError("等级价值/时长总和≤0")
    value = {k: v / sv for k, v in value.items()}
    time = {k: v / st for k, v in time.items()}
    return {"value": value, "time": time}


def read_playways(ws) -> dict:
    s, e = find_block(ws, "玩法")
    c_name = _header_col(ws, s, e, "玩法")
    c_typ = _header_col(ws, s, e, "类型")
    c_open = _header_col(ws, s, e, "开放等级")
    c_pve = _header_col(ws, s, e, "PVE%")
    c_pvp = _header_col(ws, s, e, "PVP%")
    lv_cols = {}
    for lv in LEVELS:
        lv_cols[lv] = _header_col(ws, s, e, f"LV{lv}")
    playways = []
    shares = {}
    for r, name in _data_rows(ws, c_name):
        name = str(name).strip()
        rec = {
            "name": name,
            "type": str(ws.cell(r, c_typ).value or "").strip(),
            "open": int(float(ws.cell(r, c_open).value or 1)),
            "pve": _safe_float(ws.cell(r, c_pve).value),
            "pvp": _safe_float(ws.cell(r, c_pvp).value),
        }
        row = {}
        for lv, c in lv_cols.items():
            raw = ws.cell(r, c).value
            row[lv] = 0.0 if _blank(raw) else _safe_float(raw)
        playways.append(rec)
        shares[name] = row
    if not playways:
        raise ConfigDriftError("玩法块无数据行")
    # 列归一（已在表内做；再防一手）
    for lv in LEVELS:
        tot = sum(shares[p["name"]][lv] for p in playways)
        if tot <= 0:
            raise ConfigDriftError(f"LV{lv} 玩法份额列和≤0")
        for p in playways:
            shares[p["name"]][lv] /= tot
    return {"playways": playways, "shares": shares}


def read_maps_and_encounters(ws) -> dict:
    sm, em = find_block(ws, "地图")
    se, ee = find_block(ws, "遭遇")
    c_name = _header_col(ws, sm, em, "地图")
    c_pw = _header_col(ws, sm, em, "玩法")
    c_lv = _header_col(ws, sm, em, "等级")
    attr_cols = [_header_col(ws, se, ee, a) for a in ATTRS]
    race_cols = [_header_col(ws, se, ee, a) for a in RACES]
    size_cols = [_header_col(ws, se, ee, a) for a in SIZES]
    maps, encounters = [], {}
    missing = []
    for r, name in _data_rows(ws, c_name):
        name = str(name).strip()
        pw = str(ws.cell(r, c_pw).value or "").strip()
        lv = int(float(ws.cell(r, c_lv).value))
        maps.append({"name": name, "playway": pw, "level": lv, "row": r})
        try:
            attr = np.array([_safe_float(ws.cell(r, c).value) for c in attr_cols], dtype=float)
            race = np.array([_safe_float(ws.cell(r, c).value) for c in race_cols], dtype=float)
            size = np.array([_safe_float(ws.cell(r, c).value) for c in size_cols], dtype=float)
        except ConfigDriftError:
            missing.append(name)
            continue
        if attr.sum() <= 0 or race.sum() <= 0 or size.sum() <= 0:
            missing.append(name)
            continue
        encounters[name] = {
            "attr": attr / attr.sum(),
            "race": race / race.sum(),
            "size": size / size.sum(),
        }
    if missing:
        raise ConfigDriftError(
            f"遭遇三维缺失或不均匀兜底禁止：{missing[:8]}{'…' if len(missing) > 8 else ''}"
        )
    if not maps:
        raise ConfigDriftError("地图块无数据")
    return {"maps": maps, "encounters": encounters}


def read_prefs(ws) -> dict:
    s, e = find_block(ws, "偏好")
    c_name = _header_col(ws, s, e, "玩法")
    builds = []
    for c in range(s + 1, e + 1):
        h = ws.cell(4, c).value
        if h is None or str(h).strip() in {"", "合计", "校验"}:
            continue
        builds.append((c, str(h).strip()))
    if not builds:
        raise ConfigDriftError("偏好块无构筑列")
    prefs = {}
    for r, name in _data_rows(ws, c_name):
        name = str(name).strip()
        dist = []
        for c, _b in builds:
            raw = ws.cell(r, c).value
            dist.append(0.0 if _blank(raw) else _safe_float(raw))
        tot = sum(dist)
        if tot <= 0:
            raise ConfigDriftError(f"偏好 {name} 行和≤0")
        prefs[name] = {builds[i][1]: dist[i] / tot for i in range(len(builds))}
    return {"builds": [b for _c, b in builds], "prefs": prefs}


def compose_weights(levels_blk: dict, play: dict, prefs: dict) -> dict:
    """W(lv, mode, play, build) = V(lv,mode) × Share_mode(play,lv) × Pref."""
    playways = play["playways"]
    shares = play["shares"]
    pref = prefs["prefs"]
    builds = prefs["builds"]
    value = levels_blk["value"]
    timew = levels_blk["time"]
    names = [p["name"] for p in playways]
    pve = {p["name"]: p["pve"] for p in playways}
    pvp = {p["name"]: p["pvp"] for p in playways}

    cube = {}  # (lv, mode, play, build) -> (w_value, w_time)
    for lv in LEVELS:
        s = sum(shares[n][lv] for n in names)
        if s <= 0:
            raise ConfigDriftError(f"LV{lv} 玩法份额和≤0")
        beta_pve = sum(shares[n][lv] * pve[n] for n in names) / s
        beta_pvp = sum(shares[n][lv] * pvp[n] for n in names) / s
        v_mode = {"PVE": value[lv] * beta_pve, "PVP": value[lv] * beta_pvp}
        t_mode = {"PVE": timew[lv] * beta_pve, "PVP": timew[lv] * beta_pvp}
        for mode, pct in (("PVE", pve), ("PVP", pvp)):
            denom = sum(shares[n][lv] * pct[n] for n in names)
            for n in names:
                if n not in pref:
                    raise ConfigDriftError(f"偏好缺玩法 {n}")
                sh = 0.0 if denom <= 0 else shares[n][lv] * pct[n] / denom
                for b in builds:
                    cube[(lv, mode, n, b)] = (
                        v_mode[mode] * sh * pref[n][b],
                        t_mode[mode] * sh * pref[n][b],
                    )
    return {"cube": cube, "builds": builds, "play_names": names}


def compose_pve_config(play: dict, maps_enc: dict, levels_blk: dict) -> dict:
    """每等级：玩法份额×PVE% 均摊到该玩法地图的遭遇三维。"""
    shares = play["shares"]
    pve = {p["name"]: p["pve"] for p in play["playways"]}
    by_pw = defaultdict(list)
    for m in maps_enc["maps"]:
        by_pw[m["playway"]].append(m)
    pve_config = {}
    for lv in LEVELS:
        rows = []
        for p in play["playways"]:
            n = p["name"]
            w = levels_blk["value"][lv] * shares[n][lv] * pve[n]
            if w <= cfg.PROGRAM_EPS:
                continue
            maps = by_pw.get(n) or []
            if not maps:
                continue
            part = w / len(maps)
            for m in maps:
                enc = maps_enc["encounters"][m["name"]]
                rows.append({
                    "name": f"{n}-{m['name']}",
                    "type": n,
                    "level": lv,
                    "weight": part,
                    "attr": enc["attr"].copy(),
                    "race": enc["race"].copy(),
                    "size": enc["size"].copy(),
                })
        if not rows:
            raise ConfigDriftError(f"Lv{lv} 无可用 PVE 遭遇（玩法未挂地图或份额为 0）")
        pve_config[lv] = rows
    return pve_config


def read_spec3_panel(ws) -> dict:
    s, e = find_block(ws, "流派三维")
    c_cat = _header_col(ws, s, e, "大类")
    c_sub = _header_col(ws, s, e, "小类")
    builds = []
    for c in range(s, e + 1):
        h = ws.cell(4, c).value
        if h is None:
            continue
        name = str(h).strip()
        if name in {"大类", "小类", ""}:
            continue
        builds.append((c, name))
    if not builds:
        raise ConfigDriftError("流派三维无构筑列")
    build_names = [b for _c, b in builds]
    sections = {"属性": [], "武器类型": [], "种族": [], "体型": []}
    last = None
    for r in range(5, min(int(ws.max_row or 5), 80) + 1):
        cat = ws.cell(r, c_cat).value
        sub = ws.cell(r, c_sub).value
        if not _blank(cat):
            last = str(cat).strip()
        if last not in sections or _blank(sub):
            continue
        sections[last].append((r, str(sub).strip()))

    elem_dmg = {b: {} for b in build_names}
    elements = []
    for r, elem in sections["属性"]:
        elements.append(elem)
        for c, b in builds:
            elem_dmg[b][elem] = _safe_float(ws.cell(r, c).value)

    weapon = {}
    if not sections["武器类型"]:
        raise ConfigDriftError("流派三维无武器类型段")
    for c, b in builds:
        wp = {}
        for r, name in sections["武器类型"]:
            p = _safe_float(ws.cell(r, c).value)
            if p > 0:
                wp[name] = wp.get(name, 0.0) + p
        if not wp:
            raise ConfigDriftError(f"流派 {b} 武器概率全 0")
        weapon[b] = wp

    def _best(section: str, label: str) -> dict:
        rows = sections[section]
        if not rows:
            raise ConfigDriftError(f"流派三维无{section}段")
        out = {}
        for c, b in builds:
            best, bp = None, -1.0
            for r, name in rows:
                p = _safe_float(ws.cell(r, c).value)
                if p > bp:
                    best, bp = name, p
            if not best or bp <= 0:
                raise ConfigDriftError(f"流派 {b} {label} 缺失")
            out[b] = best
        return out

    def _dist(section: str) -> dict:
        rows = sections[section]
        out = {b: {} for _c, b in builds}
        for r, name in rows:
            for c, b in builds:
                out[b][name] = _safe_float(ws.cell(r, c).value)
        for b in out:
            tot = sum(out[b].values())
            if tot > 0:
                out[b] = {k: v / tot for k, v in out[b].items()}
        return out

    return {
        "elem_dmg": elem_dmg,
        "weapon": weapon,
        "elements": elements,
        "weapon_types": list(cfg.WEAPON_MATRIX_TYPES),
        "build_names": build_names,
        "size_data": _best("体型", "体型"),
        "species_data": _best("种族", "种族"),
        "race_dist": _dist("种族"),
        "size_dist": _dist("体型"),
    }


def apply_types():
    cfg.ATTR_TYPES.clear()
    cfg.ATTR_TYPES.extend(ATTRS)
    cfg.RACE_TYPES.clear()
    cfg.RACE_TYPES.extend(RACES)
    cfg.SIZE_TYPES.clear()
    cfg.SIZE_TYPES.extend(SIZES)
    cfg.LEVELS_5STEP = list(LEVELS)


def load_scene_v2(wb) -> dict:
    ws = wb[cfg.SHEET_SCENE]
    apply_types()
    levels_blk = read_levels(ws)
    play = read_playways(ws)
    maps_enc = read_maps_and_encounters(ws)
    prefs = read_prefs(ws)
    weights = compose_weights(levels_blk, play, prefs)
    pve_config = compose_pve_config(play, maps_enc, levels_blk)
    panel = read_spec3_panel(ws)
    # β from 玩法加权
    per_level = {}
    names = [p["name"] for p in play["playways"]]
    pve = {p["name"]: p["pve"] for p in play["playways"]}
    pvp = {p["name"]: p["pvp"] for p in play["playways"]}
    for lv in LEVELS:
        s = sum(play["shares"][n][lv] for n in names)
        bp = sum(play["shares"][n][lv] * pve[n] for n in names) / s
        bq = sum(play["shares"][n][lv] * pvp[n] for n in names) / s
        per_level[lv] = {"pve_weight": bp, "pvp_weight": bq}
    return {
        "levels_blk": levels_blk,
        "play": play,
        "maps_enc": maps_enc,
        "prefs": prefs,
        "weights": weights,
        "pve_config": pve_config,
        "build_panel": panel,
        "per_level_weights": per_level,
        "level_weights": levels_blk["value"],
        "attr_types": list(ATTRS),
        "race_types": list(RACES),
        "size_types": list(SIZES),
    }

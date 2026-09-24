# builds.py — BE 块 / PVP 表 / 流派面板 / PVP 环境分布派生
import numpy as np

from 场景覆盖 import config as cfg
from .scenes import _safe_float, _find_sheet


def _resolve_with_required(build_name: str, best_value, data_dict: dict,
                           dim_label: str) -> object:
    """build 维度数据缺失时直接 raise (不允许兜底)。"""
    if best_value:
        return best_value
    raise ValueError(
        f"{cfg.PRINT_PREFIX_WARN} 流派 {build_name} {dim_label} 缺失, "
        f"业务真值应直接写入场景覆盖 Sheet R5-R40 区段, 不允许兜底"
    )


def read_be_table(wb) -> dict:
    """读取玩法流派偏好区块,按 PVE%/PVP% 加权拆出 PVE/PVP 流派分布。"""
    sheet_name = _find_sheet(wb, cfg.SHEET_SCENE)
    ws = wb[sheet_name]

    title_row = None
    for r in range(1, ws.max_row + 1):
        be_val = ws.cell(row=r, column=cfg.COL["BE_PLAYWAY_COL"]).value
        if be_val and isinstance(be_val, str) and be_val.strip() == "玩法":
            bf_check = ws.cell(row=r, column=cfg.COL["BE_BUILD_COL_START"]).value
            if bf_check and isinstance(bf_check, str) and len(bf_check.strip()) >= 2:
                title_row = r
                break

    if title_row is None:
        cfg.qprint(f"{cfg.PRINT_PREFIX_READ} 场景覆盖Sheet BE 块未找到 (BE 列无'玩法'标题), "
                   f"将从玩法流派偏好Sheet聚合")
        return {}

    header_row = title_row
    build_names = []
    for c in range(cfg.COL["BE_BUILD_COL_START"],
                   cfg.COL["BE_BUILD_COL_START"] + cfg.COL["N_BE_BUILDS"]):
        v = ws.cell(row=header_row, column=c).value
        if v is None:
            break
        s = str(v).strip()
        if not s:
            break
        build_names.append(s)

    if len(build_names) != cfg.COL["N_BE_BUILDS"]:
        print(f"{cfg.PRINT_PREFIX_WARN} BE 块表头实际 {len(build_names)} 列, "
              f"cfg.COL[N_BE_BUILDS]={cfg.COL['N_BE_BUILDS']}, 不一致 — Excel 改了 build 数没同步 cfg")

    if not build_names:
        cfg.qprint(f"{cfg.PRINT_PREFIX_READ} BE 块表头为空, 将从玩法流派偏好Sheet聚合")
        return {}

    n_build = len(build_names)
    pve_col = cfg.COL["BE_PVE_PCT_COL"]
    pvp_col = cfg.COL["BE_PVP_PCT_COL"]

    playway_records = []
    empty_streak = 0
    # 读到连续空行为止; 不再用 N_BE_PLAYWAYS 硬截断 (表内已扩到 70+ 玩法)
    max_rows = int(cfg.COL.get("N_BE_PLAYWAYS") or 0)
    soft_cap = max(max_rows, 200)  # 安全上限, 防坏表死循环
    for r in range(title_row + 1, ws.max_row + 1):
        if len(playway_records) >= soft_cap:
            print(f"{cfg.PRINT_PREFIX_WARN} BE 玩法行已达 soft_cap={soft_cap}, 停止继续读")
            break
        pw_name = ws.cell(row=r, column=cfg.COL["BE_PLAYWAY_COL"]).value
        if pw_name is None or not str(pw_name).strip():
            empty_streak += 1
            if empty_streak >= 2:
                break
            continue
        empty_streak = 0
        pw_name = str(pw_name).strip()

        pve_pct = _safe_float(ws.cell(row=r, column=pve_col).value)
        pvp_pct = _safe_float(ws.cell(row=r, column=pvp_col).value)

        dist = []
        for i in range(n_build):
            val = _safe_float(ws.cell(row=r, column=cfg.COL["BE_BUILD_COL_START"] + i).value)
            dist.append(val)
        total = sum(dist)

        if pve_pct + pvp_pct < cfg.USER_EPS:
            print(f"{cfg.PRINT_PREFIX_WARN} BE 块玩法[{pw_name}] R{r} "
                  f"PVE%+PVP%={pve_pct + pvp_pct:.3f}=0, 跳过")
            continue
        if abs(pve_pct + pvp_pct - 1.0) > 0.01:
            print(f"{cfg.PRINT_PREFIX_WARN} BE 块玩法[{pw_name}] R{r} "
                  f"PVE%+PVP%={pve_pct + pvp_pct:.3f}≠1.0, 业务可能填错")

        normalized = [v / total for v in dist] if total > 0 else [0.0] * n_build
        playway_records.append({
            "name": pw_name,
            "pve_pct": pve_pct,
            "pvp_pct": pvp_pct,
            "dist": normalized,
            "dist_sum": total,
        })

    if not playway_records:
        cfg.qprint(f"{cfg.PRINT_PREFIX_READ} BE 块数据行全空, 将从玩法流派偏好Sheet聚合")
        return {}

    total_pve = sum(rec["pve_pct"] for rec in playway_records)
    total_pvp = sum(rec["pvp_pct"] for rec in playway_records)

    if total_pve <= cfg.USER_EPS:
        raise ValueError(
            f"BE 块 {len(playway_records)} 行玩法 PVE% 总和={total_pve:.4f}≤0, "
            f"业务必须在 R5-R20 的 PVE%(AZ)列填占比,否则无法计算 PVE 流派分布"
        )
    if total_pvp <= cfg.USER_EPS:
        raise ValueError(
            f"BE 块 {len(playway_records)} 行玩法 PVP% 总和={total_pvp:.4f}≤0, "
            f"业务必须在 R5-R20 的 PVP%(BA)列填占比,否则无法计算 PVP 流派分布"
        )

    pve_avg = [sum(rec["dist"][b] * rec["pve_pct"] for rec in playway_records) / total_pve
               for b in range(n_build)]
    pvp_avg = [sum(rec["dist"][b] * rec["pvp_pct"] for rec in playway_records) / total_pvp
               for b in range(n_build)]

    pve_dist = {build_names[b]: pve_avg[b] for b in range(n_build)}
    pvp_dist = {build_names[b]: pvp_avg[b] for b in range(n_build)}

    cfg.qprint(f"{cfg.PRINT_PREFIX_READ} BE 块严格加权 PVE/PVP 流派分布: "
               f"{len(playway_records)} 玩法 × {n_build} 流派, "
               f"PVE 总占比={total_pve:.3f}, PVP 总占比={total_pvp:.3f}, "
               f"pve_sum={sum(pve_avg):.4f}, pvp_sum={sum(pvp_avg):.4f}")

    return {
        "pve_dist": pve_dist,
        "pvp_dist": pvp_dist,
        "build_names": build_names,
        "playways": playway_records,  # 含 dist, 供按等级三维分布加权
        "playway_count": len(playway_records),
        "playway_debug": [
            {"name": rec["name"], "pve_pct": rec["pve_pct"], "pvp_pct": rec["pvp_pct"],
             "dist_sum": rec["dist_sum"]} for rec in playway_records
        ],
        "source": "BE",
    }


def read_playway_level_shares(wb) -> dict:
    """读「玩法三维分布」块: 各玩法在 LV10..LV60 的活跃/价值份额.

    返回: {playway_name: {level: float}}
    各等级列内份额随后在 compose 时归一化 (表内原始和不一定=1)。
    """
    sheet_name = _find_sheet(wb, cfg.SHEET_SCENE)
    ws = wb[sheet_name]

    col_pw = cfg.COL.get("玩法三维分布_玩法")
    if not col_pw:
        cfg.qprint(f"{cfg.PRINT_PREFIX_WARN} 未找到「玩法三维分布_玩法」列, 无法按等级拆 meta")
        return {}

    lv_cols = {}
    for lv in cfg.LEVELS_5STEP:
        key = f"玩法三维分布_LV{lv}"
        if key in cfg.COL:
            lv_cols[lv] = cfg.COL[key]
    if not lv_cols:
        cfg.qprint(f"{cfg.PRINT_PREFIX_WARN} 玩法三维分布无 LV 列, 无法按等级拆 meta")
        return {}

    # 找数据起始行 (R4=表头「玩法」)
    start = None
    for r in range(1, min(30, ws.max_row + 1)):
        if str(ws.cell(r, col_pw).value or "").strip() == "玩法":
            start = r + 1
            break
    if start is None:
        start = cfg.BE_DATA_ROW_START

    result = {}
    empty = 0
    for r in range(start, ws.max_row + 1):
        name = ws.cell(r, col_pw).value
        if name is None or not str(name).strip():
            empty += 1
            if empty >= 2:
                break
            continue
        empty = 0
        name = str(name).strip()
        if "合计" in name:
            continue
        result[name] = {
            lv: _safe_float(ws.cell(r, c).value) for lv, c in lv_cols.items()
        }

    cfg.qprint(f"{cfg.PRINT_PREFIX_READ} 玩法三维分布: {len(result)} 玩法 × {len(lv_cols)} 等级")
    return result


def compose_level_build_meta(be_table: dict, level_shares: dict, levels: list) -> dict:
    """用「等级活跃份额 × 玩法PVE%/PVP% × 玩法内流派分布」合成每等级 PVE/PVP 流派 meta.

    返回:
      pve_by_lv / pvp_by_lv: {lv: {build: weight}}
      real_builds: list
      meta_mode: 'per_level' | 'global_fallback'
    """
    all_builds = list(be_table.get("build_names", []))
    build_names = [b for b in all_builds if b != cfg.STANDARD_BUILD_NAME]
    playways = be_table.get("playways") or []
    if not build_names or not playways:
        raise ValueError(f"{cfg.PRINT_PREFIX_WARN} BE 缺 playways/build_names, 无法合成等级 meta")

    be_by_name = {rec["name"]: rec for rec in playways}
    # dist 下标对齐 BE 表头全列 (含可能的木桩列)
    idx_of = {b: i for i, b in enumerate(all_builds)}

    if not level_shares:
        # 回退: 全等级共用全局 BE 聚合
        pve_g = {b: float(be_table["pve_dist"].get(b, 0.0)) for b in build_names}
        pvp_g = {b: float(be_table["pvp_dist"].get(b, 0.0)) for b in build_names}
        sp, sq = sum(pve_g.values()), sum(pvp_g.values())
        if sp > 0:
            pve_g = {k: v / sp for k, v in pve_g.items()}
        if sq > 0:
            pvp_g = {k: v / sq for k, v in pvp_g.items()}
        return {
            "pve_by_lv": {lv: dict(pve_g) for lv in levels},
            "pvp_by_lv": {lv: dict(pvp_g) for lv in levels},
            "real_builds": build_names,
            "meta_mode": "global_fallback",
        }

    # 名称对齐
    shared = sorted(set(level_shares) & set(be_by_name))
    only_lv = sorted(set(level_shares) - set(be_by_name))
    only_be = sorted(set(be_by_name) - set(level_shares))
    if only_lv:
        print(f"{cfg.PRINT_PREFIX_WARN} 三维分布有、BE 无流派行的玩法 (跳过 {len(only_lv)}): "
              f"{only_lv[:12]}{'...' if len(only_lv) > 12 else ''}")
    if only_be:
        print(f"{cfg.PRINT_PREFIX_WARN} BE 有、三维分布无的玩法 (跳过 {len(only_be)}): "
              f"{only_be[:12]}{'...' if len(only_be) > 12 else ''}")
    if not shared:
        raise ValueError(
            f"{cfg.PRINT_PREFIX_WARN} 玩法三维分布与 BE 玩法名无交集, 无法按等级合成 meta"
        )
    print(f"{cfg.PRINT_PREFIX_READ} 分等级 meta 对齐玩法 {len(shared)}/"
          f"{len(set(level_shares)|set(be_by_name))} "
          f"(三维{len(level_shares)} × BE{len(be_by_name)})")

    pve_by_lv, pvp_by_lv = {}, {}
    for lv in levels:
        raw = {pw: float(level_shares[pw].get(lv, 0.0)) for pw in shared}
        act_sum = sum(raw.values())
        if act_sum <= cfg.PROGRAM_EPS:
            # 该等级无活跃份额 → 用全局聚合兜底该级
            pve_by_lv[lv] = {b: float(be_table["pve_dist"].get(b, 0.0)) for b in build_names}
            pvp_by_lv[lv] = {b: float(be_table["pvp_dist"].get(b, 0.0)) for b in build_names}
            sp = sum(pve_by_lv[lv].values())
            sq = sum(pvp_by_lv[lv].values())
            if sp > 0:
                pve_by_lv[lv] = {k: v / sp for k, v in pve_by_lv[lv].items()}
            if sq > 0:
                pvp_by_lv[lv] = {k: v / sq for k, v in pvp_by_lv[lv].items()}
            continue

        pve_acc = {b: 0.0 for b in build_names}
        pvp_acc = {b: 0.0 for b in build_names}
        w_pve_tot = w_pvp_tot = 0.0
        for pw in shared:
            activity = raw[pw] / act_sum
            rec = be_by_name[pw]
            wp = activity * float(rec["pve_pct"])
            wq = activity * float(rec["pvp_pct"])
            dist = rec["dist"]
            for b in build_names:
                i = idx_of.get(b)
                if i is not None and i < len(dist):
                    pve_acc[b] += wp * float(dist[i])
                    pvp_acc[b] += wq * float(dist[i])
            w_pve_tot += wp
            w_pvp_tot += wq

        if w_pve_tot > cfg.PROGRAM_EPS:
            pve_by_lv[lv] = {b: pve_acc[b] / w_pve_tot for b in build_names}
        else:
            pve_by_lv[lv] = {b: float(be_table["pve_dist"].get(b, 0.0)) for b in build_names}
            sp = sum(pve_by_lv[lv].values()) or 1.0
            pve_by_lv[lv] = {k: v / sp for k, v in pve_by_lv[lv].items()}

        if w_pvp_tot > cfg.PROGRAM_EPS:
            pvp_by_lv[lv] = {b: pvp_acc[b] / w_pvp_tot for b in build_names}
        else:
            pvp_by_lv[lv] = {b: float(be_table["pvp_dist"].get(b, 0.0)) for b in build_names}
            sq = sum(pvp_by_lv[lv].values()) or 1.0
            pvp_by_lv[lv] = {k: v / sq for k, v in pvp_by_lv[lv].items()}

    # 诊断: Lv10 vs Lv60 是否真的不同 (始终打印, 便于确认「完全真实」)
    if 10 in pve_by_lv and 60 in pve_by_lv:
        drift = sum(abs(pve_by_lv[10][b] - pve_by_lv[60][b]) for b in build_names)
        print(f"{cfg.PRINT_PREFIX_READ} 分等级 meta 就绪: "
              f"{len(shared)} 玩法对齐, Lv10↔Lv60 PVE流派 L1漂移={drift:.4f}")

    return {
        "pve_by_lv": pve_by_lv,
        "pvp_by_lv": pvp_by_lv,
        "real_builds": build_names,
        "meta_mode": "per_level",
    }


def read_pvp_table(wb) -> dict:
    """兼容层: 旧 API 读 PVP 整体流派分布 (BE 块契约)。"""
    be = read_be_table(wb)
    if not be:
        return {}
    avg_dict = be["pvp_dist"]
    return {lv: {"build_weights": dict(avg_dict)} for lv in cfg.LEVELS_5STEP}


def derive_pvp_env_distributions(pvp_table: dict, build_panel: dict, levels: list,
                                 attr_types: list, race_types: list,
                                 size_types: list, weapon_types: list) -> dict:
    """从 pvp_table + build_panel 派生 PVP 各维度真实分布。"""
    elem_dmg = build_panel.get("elem_dmg", {})
    species_data = build_panel.get("species_data", {})
    size_data = build_panel.get("size_data", {})
    weapon = build_panel.get("weapon", {})

    n_attr, n_race, n_size, n_weapon = (
        len(attr_types), len(race_types), len(size_types), len(weapon_types))

    result = {}
    for lv in levels:
        lv_data = pvp_table.get(lv) if pvp_table else None
        if not lv_data:
            continue
        bw_dict = lv_data.get("build_weights", {})
        if not bw_dict:
            continue

        attr_dist = np.zeros(n_attr)
        for bname, bw in bw_dict.items():
            if bname not in elem_dmg:
                continue
            for i, attr in enumerate(attr_types):
                attr_dist[i] += bw * elem_dmg[bname].get(attr, 0.0)
        s = float(attr_dist.sum())
        if s <= 0:
            raise ValueError(
                f"{cfg.PRINT_PREFIX_WARN} Lv{lv} pvp attr 分布 sum={s}≤0, "
                f"build_weights 与 elem_dmg 不匹配, 业务数据缺失而非均衡, 不允许均匀兜底"
            )
        attr_dist = attr_dist / s

        race_dist = np.zeros(n_race)
        missing_race_builds = []
        for bname, bw in bw_dict.items():
            rc = species_data.get(bname)
            if rc in race_types:
                race_dist[race_types.index(rc)] += bw
            else:
                missing_race_builds.append((bname, rc))
        if missing_race_builds:
            raise ValueError(
                f"{cfg.PRINT_PREFIX_WARN} Lv{lv} {len(missing_race_builds)} 个流派 race 缺失 "
                f"(示例: {missing_race_builds[:3]}), "
                f"业务真值应写入场景覆盖 Sheet R33-R42, 不允许兜底"
            )
        s = float(race_dist.sum())
        if s <= 0:
            raise ValueError(f"{cfg.PRINT_PREFIX_WARN} Lv{lv} pvp race 分布 sum={s}≤0")
        race_dist = race_dist / s

        size_dist = np.zeros(n_size)
        missing_size_builds = []
        for bname, bw in bw_dict.items():
            sz = size_data.get(bname)
            if sz in size_types:
                size_dist[size_types.index(sz)] += bw
            else:
                missing_size_builds.append((bname, sz))
        if missing_size_builds:
            raise ValueError(
                f"{cfg.PRINT_PREFIX_WARN} Lv{lv} {len(missing_size_builds)} 个流派 size 缺失 "
                f"(示例: {missing_size_builds[:3]}), "
                f"业务真值应写入场景覆盖 Sheet R38-R40, 不允许兜底"
            )
        s = float(size_dist.sum())
        if s <= 0:
            raise ValueError(f"{cfg.PRINT_PREFIX_WARN} Lv{lv} pvp size 分布 sum={s}≤0")
        size_dist = size_dist / s

        weapon_dist = np.zeros(n_weapon)
        missing_weapon_builds = []
        for bname, bw in bw_dict.items():
            wp_prob = weapon.get(bname)
            if not isinstance(wp_prob, dict) or not wp_prob:
                missing_weapon_builds.append((bname, None))
                continue
            coarse_total = sum(wp_prob.values())
            if coarse_total <= 0:
                missing_weapon_builds.append((bname, "粗概率 sum=0"))
                continue
            for coarse_name, coarse_p in wp_prob.items():
                bridge = cfg.WEAPON_NAME_BRIDGE.get(coarse_name)
                if not bridge:
                    missing_weapon_builds.append((bname, f"粗武器 {coarse_name!r} 不在 bridge"))
                    continue
                share_per_fine = (coarse_p / coarse_total) / len(bridge)
                for fine_name in bridge:
                    if fine_name in weapon_types:
                        weapon_dist[weapon_types.index(fine_name)] += bw * share_per_fine
                    else:
                        missing_weapon_builds.append((bname, f"细武器 {fine_name!r} 不在 matrix"))
        if missing_weapon_builds:
            raise ValueError(
                f"{cfg.PRINT_PREFIX_WARN} Lv{lv} {len(missing_weapon_builds)} 个流派 weapon 桥接失败, "
                f"业务真值应写入场景覆盖 Sheet R15-R32 (粗) / 克制矩阵 R32-R49 (细), 不允许兜底. "
                f"示例: {missing_weapon_builds[:3]}"
            )
        s = float(weapon_dist.sum())
        if s <= 0:
            raise ValueError(f"{cfg.PRINT_PREFIX_WARN} Lv{lv} pvp weapon 分布 sum={s}≤0")
        weapon_dist = weapon_dist / s

        result[lv] = {
            "attr": attr_dist,
            "race": race_dist,
            "size": size_dist,
            "weapon_dist": weapon_dist,
        }

    n_derived = len(result)
    if n_derived:
        cfg.qprint(f"{cfg.PRINT_PREFIX_READ} 玩家侧三维/武器分布 "
                   f"(派生自流派 meta, {n_derived}/{len(levels)} 等级)")
    return result


def read_build_panel(wb):
    """读取流派三维面板（按「大类」分段，不写死行号）。

    大类 ∈ {属性, 武器类型, 种族, 体型}；构筑列 = R4 自 C3 起连续非空。
    """
    ws_scn = wb[cfg.SHEET_SCENE]

    # 构筑列：优先用 resolve 结果，否则扫 R4
    build_names = []
    start_c = int(cfg.COL.get("SPEC3_BUILD_COL_START") or 3)
    n_b = int(cfg.COL.get("N_SPEC3_BUILDS") or 0)
    if n_b > 0:
        for c in range(start_c, start_c + n_b):
            v = ws_scn.cell(row=4, column=c).value
            if v is None or not str(v).strip():
                break
            build_names.append(str(v).strip())
    if not build_names:
        for c in range(3, 40):
            v = ws_scn.cell(row=4, column=c).value
            if not v:
                break
            s = str(v).strip()
            if s in ("大类", "小类"):
                continue
            build_names.append(s)
    if not build_names:
        raise ValueError("找不到流派表头（场景覆盖 流派三维 R4）")

    if cfg.STANDARD_BUILD_NAME in build_names:
        build_names.remove(cfg.STANDARD_BUILD_NAME)
        build_names.insert(0, cfg.STANDARD_BUILD_NAME)

    # 按大类分段收集行
    sections: dict[str, list] = {"属性": [], "武器类型": [], "种族": [], "体型": []}
    last_cat = None
    for r in range(5, min(int(ws_scn.max_row or 5), 80) + 1):
        cat_raw = ws_scn.cell(row=r, column=1).value
        sub = ws_scn.cell(row=r, column=2).value
        if cat_raw is not None and str(cat_raw).strip():
            last_cat = str(cat_raw).strip()
        if last_cat not in sections:
            # 允许空大类继承；未知大类跳过
            if sub is None:
                continue
            continue
        if sub is None or not str(sub).strip():
            continue
        sections[last_cat].append((r, str(sub).strip()))

    elements = []
    elem_dmg = {b: {} for b in build_names}
    for r, elem in sections["属性"]:
        elements.append(elem)
        for i, build in enumerate(build_names):
            val = _safe_float(ws_scn.cell(row=r, column=3 + i).value)
            elem_dmg[build][elem] = val

    weapon = {}
    weapon_rows = sections["武器类型"]
    if not weapon_rows:
        raise ValueError(f"{cfg.PRINT_PREFIX_WARN} 流派三维未找到「武器类型」段")
    for i, build in enumerate(build_names):
        col = 3 + i
        wp_prob = {}
        for r, wp_name in weapon_rows:
            prob = _safe_float(ws_scn.cell(row=r, column=col).value)
            if prob > 0:
                wp_prob[wp_name] = wp_prob.get(wp_name, 0.0) + prob
        if not wp_prob:
            raise ValueError(
                f"{cfg.PRINT_PREFIX_WARN} 流派 {build} 武器概率全 0（武器类型段漏填）"
            )
        weapon[build] = wp_prob

    size_data = {}
    size_rows = sections["体型"]
    if not size_rows:
        raise ValueError(f"{cfg.PRINT_PREFIX_WARN} 流派三维未找到「体型」段")
    for i, build in enumerate(build_names):
        col = 3 + i
        best_sz = None
        best_prob = -1.0
        for r, sz_name in size_rows:
            prob = _safe_float(ws_scn.cell(row=r, column=col).value)
            if prob > best_prob:
                best_prob = prob
                best_sz = sz_name
        if best_sz and best_prob > 0:
            size_data[build] = best_sz
        else:
            size_data[build] = _resolve_with_required(
                build, best_sz, size_data, "体型")

    species_data = {}
    race_rows = sections["种族"]
    if not race_rows:
        raise ValueError(f"{cfg.PRINT_PREFIX_WARN} 流派三维未找到「种族」段")
    for i, build in enumerate(build_names):
        col = 3 + i
        best_rc = None
        best_prob = -1.0
        for r, rc_name in race_rows:
            prob = _safe_float(ws_scn.cell(row=r, column=col).value)
            if prob > best_prob:
                best_prob = prob
                best_rc = rc_name
        if best_rc and best_prob > 0:
            species_data[build] = best_rc
        else:
            species_data[build] = _resolve_with_required(
                build, best_rc, species_data, "种族")

    cfg.qprint(
        f"{cfg.PRINT_PREFIX_READ} 流派面板 {len(build_names)} 构筑 "
        f"(属性{len(elements)}/武器{len(weapon_rows)}/种族{len(race_rows)}/体型{len(size_rows)})"
    )
    return {
        "elem_dmg": elem_dmg,
        "weapon": weapon,
        "elements": elements,
        "weapon_types": list(cfg.WEAPON_MATRIX_TYPES),
        "build_names": build_names,
        "size_data": size_data,
        "species_data": species_data,
    }

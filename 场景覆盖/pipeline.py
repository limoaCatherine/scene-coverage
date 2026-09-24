# pipeline.py — load → env → calc → rank → write
from __future__ import annotations

from 场景覆盖 import config as cfg
from 场景覆盖.load import load_all
from 场景覆盖.calc import (
    build_env_bundle,
    calc_distributions,
    calc_attr_utility_breakdown,
    calc_weapon_size_utility,
    calc_size_strength_utility,
    calc_race_utility,
    calc_four_quadrant,
    calc_build_fairness_index,
    build_all_rankings,
)
from 场景覆盖.write import write_results, write_layered
from 场景覆盖.calc.layered_fact import calc_layered_facts


def run(
    framework_path: str | None = None,
    verbose: bool = False,
    verify: bool = True,
) -> dict:
    """跑完整覆盖率仿真; 默认结束后自动体检结果表。

    verify=False 可跳过体检 (对应 启动_场景覆盖 --skip-verify)。
    """
    if not verbose:
        cfg.QUIET = True
    path = str(framework_path or cfg.FRAMEWORK_FILE)
    # -w 覆盖默认路径（load_all 读 cfg.FRAMEWORK_FILE）
    cfg.FRAMEWORK_FILE = path

    try:
        # 全框架含 UDF，formulas 整簿重算会挂死；v2 场景覆盖读的是格子值
        print(f"{cfg.PRINT_PREFIX_WARN} refill_formula_cache 跳过: 全框架 UDF")
    except Exception as e:
        print(f"{cfg.PRINT_PREFIX_WARN} refill_formula_cache 跳过: {e}")

    data = load_all()
    from 场景覆盖.calc.sim_bridge import 流派对木桩命中
    from 场景覆盖.calc.ranking import 命中层相对

    sim_hits, gold_hits, hit_rank = {}, {}, None
    try:
        sim_hits = 流派对木桩命中(path)
        from ssot.金标命中 import 金标对木桩命中
        gold_hits = 金标对木桩命中(path)
        hit_rank = 命中层相对(sim_hits) if any(
            isinstance(v, dict) and isinstance(v.get("最终伤害"), (int, float)) for v in sim_hits.values()
        ) else None
    except Exception as e:
        print(f"[警告] 命中层跳过: {e}")
    if hit_rank is None:
        print("[警告] 命中层未写入数值；矩阵覆盖率仍跑，但不当作真实 DPS。")

    bundle = build_env_bundle(data)
    pure_dist = calc_distributions(bundle)
    detailed = calc_attr_utility_breakdown(bundle)
    size_weapon_util = calc_weapon_size_utility(bundle)
    size_hit_util = calc_size_strength_utility(bundle)
    race_util = calc_race_utility(bundle)
    quad = calc_four_quadrant(bundle)
    bfi = calc_build_fairness_index(bundle)

    rankings = build_all_rankings(
        bundle, detailed, size_weapon_util, size_hit_util, race_util, bfi, pure_dist
    )

    scene_v2 = data.get("scene_v2")
    layered = None
    if scene_v2 is not None:
        layered = calc_layered_facts(
            scene_v2,
            data["attr_matrix_pve"],
            data["attr_matrix_pvp"],
            mat_size_pve=data.get("size_matrix_pve"),
            weapon_types=data.get("weapon_types"),
        )
        out_path = write_layered(
            path, rankings=rankings, layered=layered, meta_note=bundle.meta_note
        )
    else:
        out_path = write_results(
            path,
            detailed=detailed,
            pure_dist=pure_dist,
            quad=quad,
            bfi=bfi,
            size_weapon_util=size_weapon_util,
            size_types=bundle.size_types,
            rankings=rankings,
            meta_note=bundle.meta_note,
            size_hit_util=size_hit_util,
        )

    # 批注/体检只打沙盒，禁止 openpyxl 回写正式框架簿
    try:
        from 场景覆盖.load.annotate_excel import annotate_playway_usage
        annotate_playway_usage(out_path)
    except Exception as e:
        print(f"{cfg.PRINT_PREFIX_WARN} 标注 Excel 说明失败 (可忽略): {e}")

    print("\n覆盖率仿真完成。")

    verify_code = None
    if verify:
        from 场景覆盖.verify import run_healthcheck
        verify_code = run_healthcheck(
            bundle=bundle,
            bfi=bfi,
            rankings=rankings,
            pure_dist=pure_dist,
            xlsx_path=out_path,
            check_sheet=True,
        )
        if verify_code != 0:
            print("[警告] 仿真已写出结果, 但体检未全部通过, 请对照上方明细。")

    builds = []
    try:
        builds = list((bfi.get("跨等级综合") or {}).keys())
    except Exception:
        pass

    return {
        "ok": True,
        "path": out_path,
        "builds_detected": len(builds),
        "builds": builds,
        "verify_code": verify_code,
        "bfi": bfi,
        "rankings": rankings,
        "pure_dist": pure_dist,
        "bundle": bundle,
        "detailed": detailed,
        "size_weapon_util": size_weapon_util,
        "quad": quad,
        "sim_hits": sim_hits,
        "gold_hits": gold_hits,
        "hit_rank": hit_rank,
        "layered": layered,
    }

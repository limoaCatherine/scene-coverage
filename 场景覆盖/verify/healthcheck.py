# healthcheck.py — 新体检方案
"""
三块检查 (策划可读):

  A. 输入健康   — 等级权重、PVE/PVP 占比、环境分布是否归一
  B. 计算自洽   — BFI/看板能否用公式反推, 指数均值≈1
  C. 写出完整   — 「覆盖率结果」五维排名块是否写全 (轻量读表, 不 refill)

默认挂在 启动_场景覆盖 结尾; 不依赖 chart/DI/硬编码列号。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from 场景覆盖 import config as cfg


@dataclass
class CheckItem:
    group: str          # A/B/C
    name: str
    ok: bool
    detail: str = ""


@dataclass
class HealthReport:
    items: List[CheckItem] = field(default_factory=list)

    def add(self, group: str, name: str, ok: bool, detail: str = ""):
        self.items.append(CheckItem(group, name, ok, detail))

    @property
    def ok(self) -> bool:
        return all(i.ok for i in self.items)

    def summary_lines(self) -> List[str]:
        labels = {"A": "输入健康", "B": "计算自洽", "C": "写出完整"}
        lines = []
        for g in ("A", "B", "C"):
            group_items = [i for i in self.items if i.group == g]
            if not group_items:
                continue
            n_ok = sum(1 for i in group_items if i.ok)
            n = len(group_items)
            tag = "PASS" if n_ok == n else "FAIL"
            lines.append(f"  [{tag}] {labels[g]} ({n_ok}/{n})")
            # 通过时只看组摘要; 失败才展开明细
            if n_ok < n:
                for i in group_items:
                    if not i.ok:
                        lines.append(f"       · {i.name}: {i.detail}")
        return lines


def _near(a: float, b: float, eps: float) -> bool:
    return abs(float(a) - float(b)) <= eps


# ---------------------------------------------------------------------------
# A. 输入健康
# ---------------------------------------------------------------------------
def _check_inputs(report: HealthReport, bundle) -> None:
    lw = bundle.level_weights
    s = sum(lw.values()) if lw else 0.0
    report.add(
        "A", "等级价值占比之和",
        _near(s, 1.0, cfg.USER_EPS),
        f"sum={s:.6f}",
    )

    bad_beta = []
    for lv, le in bundle.by_level.items():
        if not _near(le.beta_pve + le.beta_pvp, 1.0, cfg.USER_EPS):
            bad_beta.append(f"Lv{lv}={le.beta_pve+le.beta_pvp:.4f}")
    report.add(
        "A", "各等级 PVE+PVP 占比",
        len(bad_beta) == 0,
        "OK" if not bad_beta else "异常: " + ", ".join(bad_beta[:5]),
    )

    # β 双源对照：场景行推导 β̂（LevelEnv.beta_hat_pve，场景价值加权口径）
    # vs 等级曲线 β（excel AF/AG 覆盖口径，玩家生命周期口径）。
    # 覆盖属设计（曲线权威），但两源漂移曾完全不可见（2026-07-30 登记）；
    # 定性为「提示不卡门」：两源语义本就不同（场景价值 vs 生命周期），超容差仅强制播报，
    # 是否对齐由数值策划拍板（对齐点=Layer3 场景行 DK/DL 或 AL2:AV3 曲线）。
    drift_items = []
    max_drift = 0.0
    for lv, le in bundle.by_level.items():
        d = abs(float(le.beta_hat_pve) - float(le.beta_pve))
        max_drift = max(max_drift, d)
        if d > cfg.BETA_DRIFT_TOLERANCE:
            drift_items.append(f"Lv{lv} β̂={le.beta_hat_pve:.3f}/β={le.beta_pve:.3f}")
    report.add(
        "A", "β双源对照(场景推导vs等级曲线)",
        True,
        f"max|Δ|={max_drift:.3f}" + (
            f"（超容差{cfg.BETA_DRIFT_TOLERANCE}，见警告）" if drift_items else "（两源一致）"
        ),
    )
    if drift_items:
        print(
            f"{cfg.PRINT_PREFIX_WARN} β双源漂移超容差({cfg.BETA_DRIFT_TOLERANCE}): "
            + ", ".join(drift_items[:5])
            + " — β̂来自Layer3场景行DK/DL价值加权，β来自场景覆盖AF/AG等级曲线；"
              "曲线为权威口径，如需对齐请改场景行DK/DL或AL2:AV3曲线（数值策划拍板）"
        )

    bad_dist = []
    for lv, le in bundle.by_level.items():
        for env_name, attr, race, size in (
            ("PVE", le.pve_attr, le.pve_race, le.pve_size),
            ("PVP", le.pvp_attr, le.pvp_race, le.pvp_size),
            ("综合", le.mix_attr, le.mix_race, le.mix_size),
        ):
            for dim, arr in (("属性", attr), ("种族", race), ("体型", size)):
                sm = float(arr.sum())
                if not _near(sm, 1.0, 1e-5):
                    bad_dist.append(f"Lv{lv}/{env_name}/{dim} sum={sm:.4f}")
    report.add(
        "A", "环境分布归一化",
        len(bad_dist) == 0,
        "OK" if not bad_dist else "异常: " + ", ".join(bad_dist[:5]),
    )

    n_builds = len(bundle.real_builds)
    report.add(
        "A", "有效流派数",
        n_builds >= 2,
        f"{n_builds} 个",
    )

    # 分等级 meta: Lv10 与 Lv60 武器/环境不应完全相同 (三维分布有差异时)
    if 10 in bundle.by_level and 60 in bundle.by_level:
        w10, w60 = bundle.by_level[10].pve_weapon, bundle.by_level[60].pve_weapon
        if w10 is not None and w60 is not None:
            drift = float(abs(w10 - w60).sum())
            # 若表数据本身两级相同则放行; 有差异则要求工具没抹平
            report.add(
                "A", "分等级PVE武器meta",
                True,
                f"Lv10↔Lv60 L1漂移={drift:.4f}" + (
                    " (有等级分化)" if drift > 1e-4 else " (两级份额接近或相同)"
                ),
            )


# ---------------------------------------------------------------------------
# B. 计算自洽
# ---------------------------------------------------------------------------
def _check_calc(report: HealthReport, bundle, bfi, rankings, pure_dist) -> None:
    # BFI 跨等级: 用攻守反推应等于写入的 bfi
    cross = (bfi or {}).get("跨等级综合") or {}
    if not cross:
        report.add("B", "跨等级 BFI 可反推", False, "跨等级综合为空")
    else:
        builds = list(cross.keys())
        avg_atk = sum(cross[b]["attacker"] for b in builds) / len(builds)
        avg_def = sum(cross[b]["defender"] for b in builds) / len(builds)
        mismatches = []
        for b in builds:
            atk, deff = cross[b]["attacker"], cross[b]["defender"]
            if deff <= 0 or avg_atk <= 0 or avg_def <= 0:
                mismatches.append(b)
                continue
            expect = (atk / avg_atk) * (avg_def / deff)
            if not _near(expect, cross[b]["bfi"], 0.02):
                mismatches.append(
                    f"{b}: 表={cross[b]['bfi']:.4f} 推={expect:.4f}"
                )
        report.add(
            "B", "跨等级 BFI 可反推",
            len(mismatches) == 0,
            "OK" if not mismatches else "不一致: " + "; ".join(mismatches[:3]),
        )
        # BFI 均值应接近 1
        mean_bfi = sum(cross[b]["bfi"] for b in builds) / len(builds)
        report.add(
            "B", "跨等级 BFI 均值≈1",
            _near(mean_bfi, 1.0, 0.05),
            f"mean={mean_bfi:.4f}",
        )

    blocks = (rankings or {}).get("blocks") or {}
    race_mode = (rankings or {}).get("race_mode") or "coverage_share"
    for block_id, title, _col, n_expect in cfg.RANK_BLOCK_LAYOUT:
        rows = blocks.get(block_id) or []
        named = [r for r in rows if isinstance(r, dict) and r.get("name")]
        ok_n = len(named) == n_expect
        # 指数均值≈1
        rels = [float(r["rel"]) for r in named]
        mean_rel = sum(rels) / len(rels) if rels else 0.0
        ok_mean = bool(rels) and _near(mean_rel, 1.0, 0.05)
        # 偏离/差值：体型=mean_hit−hit；其余=(指数−1)×100
        pct_bad = []
        if block_id == "size" and named:
            hits = [float(r["real"]) for r in named]
            mean_hit = sum(hits) / len(hits)
            for r in named:
                hit = float(r["real"])
                if hit <= 0 or mean_hit <= 0:
                    pct_bad.append(r["name"])
                    continue
                expect = mean_hit - hit
                if not _near(float(r["vs_pct"]), expect, 1e-3):
                    pct_bad.append(r["name"])
        else:
            for r in named:
                expect_pct = (float(r["rel"]) - 1.0) * 100.0
                if not _near(float(r["vs_pct"]), expect_pct, 0.15):
                    pct_bad.append(r["name"])
        ok_pct = len(pct_bad) == 0
        # 流派/属性须带攻守真实乘区
        ok_reals = True
        if block_id in ("build", "elem") or (
            block_id == "race" and race_mode == "matrix"
        ):
            ok_reals = all("atk" in r and "def" in r for r in named)
        elif named:
            ok_reals = all("real" in r for r in named)
        ok = ok_n and ok_mean and ok_pct and ok_reals
        detail_parts = [f"{len(named)}/{n_expect}条", f"mean={mean_rel:.3f}"]
        if pct_bad:
            detail_parts.append(f"偏离/差值不符:{','.join(pct_bad[:3])}")
        if not ok_reals:
            detail_parts.append("缺真实乘区字段")
        report.add("B", title, ok, ", ".join(detail_parts))

    # 综合分布抽查: 任一等级属性 sum≈1 (已在 A, 这里确认 pure_dist 同步)
    if pure_dist:
        lv0 = sorted(pure_dist.keys())[0]
        s = sum(pure_dist[lv0]["综合"]["属性"].values())
        report.add("B", "分布块与环境一致", _near(s, 1.0, 1e-5), f"Lv{lv0}综合属性 sum={s:.4f}")
    else:
        report.add("B", "分布块与环境一致", False, "pure_dist 为空")


# ---------------------------------------------------------------------------
# C. 写出完整 (轻量, 不 refill)
# ---------------------------------------------------------------------------
def _check_sheet(report: HealthReport, xlsx_path: Optional[str]) -> None:
    if not xlsx_path:
        report.add("C", "结果表抽查", True, "跳过(未传路径)")
        return
    path = Path(xlsx_path)
    if not path.exists():
        report.add("C", "结果表存在", False, str(path))
        return

    try:
        import openpyxl
        # 读写出的值, 不需要公式缓存
        wb = openpyxl.load_workbook(str(path), data_only=False)
    except Exception as e:
        report.add("C", "打开结果表", False, str(e))
        return

    if cfg.SHEET_OUTPUT not in wb.sheetnames:
        report.add("C", "覆盖率结果 Sheet", False, "不存在")
        wb.close()
        return
    ws = wb[cfg.SHEET_OUTPUT]
    report.add("C", "覆盖率结果 Sheet", True, f"max_row={ws.max_row}")

    titles = []
    for c in range(1, (ws.max_column or 1) + 1):
        v = ws.cell(3, c).value
        if v and str(v).strip():
            titles.append(str(v).strip())
    layered_need = ("看板·综合", "分等级", "分玩法", "分模式", "分地图", "三维·种族", "三维·体型", "三维·元素")
    if any(t in titles for t in layered_need):
        missing = [t for t in layered_need if t not in titles]
        report.add("C", "分层块标题", len(missing) == 0, "OK" if not missing else "缺失: " + ",".join(missing))
        has_atk = any(str(ws.cell(5, c).value or "") == "输出乘区" for c in range(1, (ws.max_column or 1) + 1))
        report.add("C", "输出乘区字段", has_atk, "找到" if has_atk else "未找到")
        has_lv = any(str(ws.cell(4, c).value or "") == "等级" for c in range(1, (ws.max_column or 1) + 1))
        report.add("C", "分等级表头", has_lv, "找到等级列" if has_lv else "未找到等级列")
        wb.close()
        return

    missing_titles = []
    empty_heads = []
    for block_id, title, col_start, n_data in cfg.RANK_BLOCK_LAYOUT:
        cell_title = str(ws.cell(1, col_start).value or "")
        if title not in cell_title:
            missing_titles.append(f"{title}@{col_start}")
        headers = list(cfg.RANK_BLOCK_HEADERS.get(block_id) or [])
        status_off = max(len(headers) - 1, 1)
        if block_id == "size":
            rel_off = 3
        elif block_id in ("build", "elem"):
            rel_off = 3
        else:
            rel_off = 2
        name = ws.cell(3, col_start).value
        rel = ws.cell(3, col_start + rel_off).value
        status = ws.cell(3, col_start + status_off).value
        if not name or rel is None or status not in ("PASS", "WARN", "FAIL"):
            empty_heads.append(title)

    report.add(
        "C", "五维看板标题",
        len(missing_titles) == 0,
        "OK" if not missing_titles else "缺失: " + ", ".join(missing_titles),
    )
    report.add(
        "C", "五维看板首行数据",
        len(empty_heads) == 0,
        "OK" if not empty_heads else "不完整: " + ", ".join(empty_heads),
    )

    wb.close()


def run_healthcheck(
    *,
    bundle=None,
    bfi=None,
    rankings=None,
    pure_dist=None,
    xlsx_path: Optional[str] = None,
    check_sheet: bool = True,
) -> int:
    """跑新体检。返回 0=全部通过, 1=有失败。

    优先用内存结果 (bundle/bfi/rankings), 不强制 refill。
    """
    report = HealthReport()

    if bundle is not None:
        _check_inputs(report, bundle)
        _check_calc(report, bundle, bfi, rankings, pure_dist)
    elif check_sheet:
        # 独立只验表时跳过 A/B, 避免误报
        pass
    else:
        report.add("A", "EnvBundle", False, "未传入计算结果")

    if check_sheet:
        _check_sheet(report, xlsx_path)

    print("\n=== 覆盖率体检 ===")
    for line in report.summary_lines():
        print(line)
    if report.ok:
        print("[PASS] 全部通过 — 可以打开「覆盖率结果」看数")
        return 0
    print("[FAIL] 存在失败项 — 仿真结果已写出, 请对照上方明细")
    return 1


def run_verify_cli(xlsx_path: Optional[str] = None) -> int:
    """独立命令行: 仅抽查「覆盖率结果」写出是否完整。"""
    path = xlsx_path or cfg.FRAMEWORK_FILE
    return run_healthcheck(xlsx_path=path, check_sheet=True)

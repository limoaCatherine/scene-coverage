"""场景覆盖指标骨架。"""
from __future__ import annotations

from typing import Any


def 覆盖率指标(
    已跑场景: list[str],
    全量场景: list[str],
) -> dict[str, Any]:
    total = len(全量场景)
    done = len(set(已跑场景) & set(全量场景))
    rate = (done / total) if total else 0.0
    missing = sorted(set(全量场景) - set(已跑场景))
    return {
        "总数": total,
        "已覆盖": done,
        "覆盖率": rate,
        "缺失": missing,
    }


coverage_metrics = 覆盖率指标

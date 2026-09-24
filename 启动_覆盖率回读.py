
def _publish_out(name: str):
    from pathlib import Path
    dest = Path(__file__).resolve().parents[0] / "out" / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    return dest

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""回读覆盖率沙盒：只核看板有数，不改正式簿。"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from typing import Optional, cast

if hasattr(sys.stdout, "reconfigure"):
    cast(io.TextIOWrapper, sys.stdout).reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    cast(io.TextIOWrapper, sys.stderr).reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_SIBLING_REPOS = ("combat-sim", "scene-coverage", "attr-value", "scene-balance", "numeric-ssot", "doc-format")
for _name in _SIBLING_REPOS:
    _p = ROOT.parent / _name
    if _p.is_dir() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

SANDBOX = _publish_out("sandbox-覆盖率结果.xlsx")


def main(argv: Optional[list[str]] = None) -> int:
    del argv
    from openpyxl import load_workbook

    if not SANDBOX.is_file():
        print("无沙盒覆盖率结果")
        return 5
    wb = load_workbook(SANDBOX, data_only=True)
    try:
        if "覆盖率结果" not in wb.sheetnames:
            print("沙盒无覆盖率结果 sheet")
            return 5
        ws = wb["覆盖率结果"]
        nums = 0
        samples = []
        for r in range(1, min(40, (ws.max_row or 1) + 1)):
            for c in range(1, min(20, (ws.max_column or 1) + 1)):
                v = ws.cell(r, c).value
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    nums += 1
                    if len(samples) < 12:
                        samples.append({"r": r, "c": c, "v": v, "left": ws.cell(r, 1).value})
        titles = [ws.cell(1, c).value for c in range(1, 16) if ws.cell(1, c).value]
    finally:
        wb.close()
    dest = _publish_out("coverage_reread.json")
    dest.write_text(
        json.dumps(
            {
                "path": str(SANDBOX),
                "bytes": SANDBOX.stat().st_size,
                "R1标题": titles,
                "前40x20数字格": nums,
                "样例": samples,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps({"数字格": nums, "R1": titles[:6], "写出": str(dest)}, ensure_ascii=False))
    return 0 if nums else 5


if __name__ == "__main__":
    raise SystemExit(main())


def _publish_out(name: str):
    from pathlib import Path
    dest = Path(__file__).resolve().parents[0] / "out" / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    return dest

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""命中层相对均值：解释器最终伤害，不发明 PASS 带。"""
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


def main(argv: Optional[list[str]] = None) -> int:
    del argv
    from 场景覆盖.calc.sim_bridge import 流派对木桩命中
    from 场景覆盖.calc.ranking import 命中层相对

    hits = 流派对木桩命中()
    rank = 命中层相对(hits)
    dest = _publish_out("hit_layer_rank.json")
    dest.write_text(json.dumps(rank, ensure_ascii=False, indent=2), encoding="utf-8")
    top = (rank.get("排序") or [{}])[0]
    print(json.dumps({"均值": rank.get("均值最终伤害"), "第一": top, "写出": str(dest)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

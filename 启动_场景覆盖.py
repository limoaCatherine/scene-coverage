#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""策划入口：启动_场景覆盖.py"""
from __future__ import annotations

import argparse
import io
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
    from 场景覆盖.pipeline import run
    from 场景覆盖 import config as cfg

    ap = argparse.ArgumentParser(description="场景覆盖率（全链路）")
    ap.add_argument("-w", "--workbook", default=None, help="框架 xlsx 路径")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--skip-verify", action="store_true")
    args = ap.parse_args(argv)
    wb = args.workbook or str(cfg.FRAMEWORK_FILE)
    result = run(wb, verbose=args.verbose, verify=not args.skip_verify)
    builds = result.get("builds") or []
    print(
        f"[启动] path={result.get('path')} builds={result.get('builds_detected')} "
        f"verify={result.get('verify_code')} names={builds}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

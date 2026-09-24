"""产品线 D：场景覆盖（全链路：load → calc → write → verify）。"""
from __future__ import annotations

__version__ = "2.1.0"

from 场景覆盖.指标 import 覆盖率指标

__all__ = ["覆盖率指标", "pipeline"]

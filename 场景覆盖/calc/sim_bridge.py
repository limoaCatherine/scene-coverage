"""旧命中桥接已移除。覆盖率不再调用战斗模拟器。"""
from __future__ import annotations


def 流派对木桩命中(path=None) -> dict:
    del path
    raise RuntimeError("命中桥接已移除。战斗结果请跑 启动_战斗模拟.py")

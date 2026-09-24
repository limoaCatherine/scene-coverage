# -*- coding: utf-8 -*-
"""覆盖率的命中层：用战斗流程解释器，不用静态效用矩阵拍 DPS。"""
from __future__ import annotations

from openpyxl import load_workbook

from ssot import 框架路径
from ssot.实体工厂 import 读木桩面板, 合成木桩守方
from ssot.加载 import 加载公式参数表, 加载属性用途名, 加载转入公式
from ssot.场景离散 import 加载流派三维主离散
from ssot.转入求值 import 命名分支武器
from 战斗模拟.内核.流程解释器 import 流程解释器, 构建上下文
from 战斗模拟.load.面板 import 加载流派面板


def 选命中通道(武器: str, 转入: dict[str, str]) -> tuple[str, str]:
    """返回 (面板主键, 伤害类型)。武器名必须出现在对应转入公式的显式列表中。"""
    mag_w = 命名分支武器(转入.get("基础魔法攻击", ""))
    phy_w = 命名分支武器(转入.get("基础物理攻击", ""))
    if 武器 in mag_w and 武器 in phy_w:
        raise ValueError(f"武器 {武器!r} 同时出现在基础物理/魔法攻击转入公式")
    if 武器 in mag_w:
        return "魔法攻击", "魔法"
    if 武器 in phy_w:
        return "物理攻击", "物理"
    raise ValueError(
        f"武器 {武器!r} 未出现在基础物理/魔法攻击转入公式的显式列表"
        f"（物理={sorted(phy_w)} 魔法={sorted(mag_w)}）"
    )


def 流派对木桩命中(path=None) -> dict[str, dict]:
    """各流派按武器通道走伤害PVE（必中）打木桩。"""
    p = path or 框架路径()
    dummy = 读木桩面板(p)
    hp = dummy["生命值"]
    转入 = 加载转入公式(p)
    用途名 = 加载属性用途名(p)
    fp = 加载公式参数表(p)
    离散 = 加载流派三维主离散(p)
    wb = load_workbook(p, data_only=True)
    try:
        panels = 加载流派面板(wb)
    finally:
        wb.close()
    it = 流程解释器(工作簿路径=p)
    out: dict[str, dict] = {}
    for name, panel in panels.items():
        武器 = (离散.get(name) or {}).get("武器") or "无"
        key, dtype = 选命中通道(武器, 转入)
        atk = float(panel.属性.get(key) or 0.0)
        if atk <= 0:
            out[name] = {key: atk, "武器": 武器, "error": f"面板{key}未算出"}
            continue
        atk_p = {k: v for k, v in panel.属性.items() if isinstance(v, (int, float))}
        if "生命值" not in atk_p:
            raise ValueError(f"{name} 生命值未进缓存")
        hp_atk = float(atk_p["生命值"])
        atk_p["生命"] = hp_atk
        atk_p["当前生命"] = hp_atk
        dfd = 合成木桩守方(
            p,
            攻方等级=float(atk_p.get("等级") or 0),
            木桩=dummy,
            转入=转入,
            用途名=用途名,
            公式参数=fp,
        )
        dfd["生命"] = hp
        dfd["当前生命"] = hp
        ctx = 构建上下文(
            基础伤害=atk,
            伤害类型=dtype,
            攻方=atk_p,
            守方=dfd,
            标记={"必中"},
        )
        ctx["命中位"] = "必中"
        r = it.执行管线("伤害PVE", ctx)
        out[name] = {
            "武器": 武器,
            "通道": key,
            "伤害类型": dtype,
            key: atk,
            "木桩生命": hp,
            "最终伤害": r.最终伤害,
            "实际扣血": r.实际扣血,
            "步数": r.步数,
        }
    return out

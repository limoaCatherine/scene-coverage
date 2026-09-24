# 场景覆盖

全链路覆盖率仿真：读「场景覆盖」表头构筑 → 环境/效用/BFI/五维排名 → 写回「覆盖率结果」。

## 运行

```bash
cd /workspace/数值工具
.venv/bin/python 启动_场景覆盖.py -w /workspace/combat-framework/战斗数值框架.xlsx
```

可选：`-v` 详日志，`--skip-verify` 跳过体检。

## 构筑数

**不写死 20/11**。`玩法流派偏好` / `流派三维` 的 R4 表头有多少构筑列就读多少（当前框架为标准模型 11 构筑：正面铁壁…彗星天灾）。

## 公式缓存

box 无 Excel COM。玩法偏好/三维等已是数值则直接读；`地图价值` 期望价值与 PVE% 等公式列若无缓存，由 `load/formula_proxy.py` 用源列近似，不挂起 COM。

## 布局

```
场景覆盖/
  __init__.py  config.py  pipeline.py  指标.py  README.md
  load/   calc/   write/   verify/
```

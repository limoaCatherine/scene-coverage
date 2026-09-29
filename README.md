# 场景覆盖（scene-coverage）

全链路场景覆盖率工具：读取框架工作簿中的场景覆盖配置，按地图档位与 PVE/PVP 比例计算流派效用，并写回「覆盖率结果」。

本仓库**不包含**框架表。默认会写结果表，请先复制工作簿再运行。

## 能力

- 读取场景覆盖六块：等级、玩法、地图、遭遇、偏好、流派三维
- 按地图档位与模式权重合成流派效用
- 写回平衡总览与地图×流派结果
- 可选结果体检（可用 `--skip-verify` 跳过）
- 历史口径保留在包内 `旧口径/`，当前入口不调用

## 布局

```
scene-coverage/
  启动_场景覆盖.py
  启动_命中层排名.py
  启动_覆盖率回读.py
  场景覆盖/
    pipeline.py
    load/ calc/ write/ verify/
    旧口径/
```

## 同级依赖

| 仓库 | 用途 |
|------|------|
| `combat-sim` | 公共层与战斗模拟桥接 |
| `numeric-ssot` | 框架路径与表常量 |

## 环境

与 `combat-sim` 相同：`BATTLE_SIM_WORKBOOK` / `FRAMEWORK_WORKBOOK`，或 `-w` 指定路径。

## 运行

需要 Python 3.11+。

```bash
pip install -r requirements.txt
python 启动_场景覆盖.py -w path\to\框架表.xlsx
python 启动_场景覆盖.py -w path\to\框架表.xlsx -v
python 启动_场景覆盖.py -w path\to\框架表.xlsx --skip-verify
```

辅助脚本产物写到本仓库 `out/`。

## 许可

[MIT](LICENSE)

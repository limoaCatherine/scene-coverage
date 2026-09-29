# 场景覆盖

读「场景覆盖」六块，按地图档位和 PVE/PVP 比例算流派效用，写回「覆盖率结果」。

仓库不包含项目框架表。请先复制一份工作簿再跑，默认会写结果表。

依赖同级目录中的仓库：`combat-sim`（战斗模拟、公共）、`numeric-ssot`。

## 运行

```bash
pip install -r requirements.txt
python 启动_场景覆盖.py -w 框架表.xlsx
```

`-v` 打详细日志，`--skip-verify` 跳过结果体检。旧口径代码保留在包内 `旧口径/`，当前入口不调用。批跑写出的文件在本仓库 `out/`。

## 许可

[MIT](LICENSE)。

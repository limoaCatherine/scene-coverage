# 场景覆盖

全链路覆盖率仿真，迭代中。读框架表里的场景和构筑，算环境、效用、公平指数和排名，并写回覆盖率结果。

仓库不包含项目框架表。请先复制一份工作簿再跑，默认会写结果表。

依赖同级目录中的仓库：`combat-sim`（战斗模拟、公共）、`numeric-ssot`。

## 运行

```bash
pip install -r requirements.txt
python 启动_场景覆盖.py -w 框架表.xlsx
```

`-v` 打详细日志，`--skip-verify` 跳过结果体检。构筑列数由表头决定，不在代码里写死。批跑写出的文件在本仓库 `out/`。

## 许可

[MIT](LICENSE)。

# 随包功能验证工具

本目录提供九例验证所需的 Windows 程序。使用工程入口即可调用随包 Python、EQY 和匹配工具。

在工程根目录执行：

```powershell
scripts\run_python.cmd scripts\evaluate_official_nine.py --out results\new_assessment --phase all
scripts\run_python.cmd scripts\measure_official_efficiency.py --out results\new_efficiency --assessment results\new_assessment
```

每次使用新的输出目录。验证用 Yosys 和比赛综合用的两份程序分别保存，入口按用途调用。

## 目录内容

| 位置 | 内容 |
|---|---|
| `bin/` | EQY 及匹配的验证用 Yosys |
| `lib/` | Python 3.11.9 官方 Windows 便携版和 Click |
| `share/yosys/` | 模型和 EQY 支持文件 |
| `msys/` | make、bash、sh、grep 及运行库 |
| `licenses/` | 软件版本与原作者许可 |
| `sources/` | 对应 MSYS 软件源码和构建说明压缩包 |
| `eqy_windows_paths.patch` | EQY 支持文件在含空格目录下的查找修改 |

scripts/run_eqy.py 默认从本目录启动工具。工程入口通过随包 Python 执行 EQY，处理原 Windows 启动器无法使用含空格 Python 路径的问题。

上游来源为 [EQY](https://github.com/YosysHQ/eqy)、[OSS CAD Suite](https://github.com/YosysHQ/oss-cad-suite-build)、[Python 3.11.9](https://www.python.org/downloads/release/python-3119/) 和 [MSYS2](https://www.msys2.org/)。

本目录只保留当前 EQY SAT 流程需要的模型、插件和辅助程序。原作者许可及随工具提供的对应源码均保留。正式效率测量的环境要求见根目录 README.md。

## 文件位置索引（2026-11-04）

相对工程位置：`binary/formal/`。下表列出本层全部文件和子目录。

[返回上一层](../README.md)

| 名称与位置 | 类型及内容 |
|---|---|
| [bin/](bin/README.md) | 子目录；点击查看其全部文件位置 |
| [lib/](lib/README.md) | 子目录；点击查看其全部文件位置 |
| [licenses/](licenses/README.md) | 子目录；点击查看其全部文件位置 |
| [msys/](msys/README.md) | 子目录；点击查看其全部文件位置 |
| [share/](share/README.md) | 子目录；点击查看其全部文件位置 |
| [sources/](sources/README.md) | 子目录；点击查看其全部文件位置 |
| [CONTENTS.json](CONTENTS.json) | 结果或配置文件 |
| [eqy_windows_paths.patch](eqy_windows_paths.patch) | 源码修改文件 |
| [README.md](README.md) | 本目录文件索引 |

# 运行与检查入口

| 入口 | 用途 |
|---|---|
| `run_python.cmd` | 选择随附、外部验证工具或系统 Python |
| `evaluate_official_nine.py` | 正式九例综合、资源统计和 EQY 比较 |
| `measure_official_efficiency.py` | 九例效率测量，保留预热、初测和追加读数 |
| `verify_shipped_binary.py` | 程序、源码、运行依赖与当前结果的对应检查 |
| `verify_parameter_variants.py` | 参数和位宽检查 |
| `verify_algorithm_changes.py` | 初值和嵌套运算检查 |
| `verify_generality.py` | 通用结构和限制条件检查 |
| `verify_priority_safety.py` | 优先链检查；其三项结果已包含于通用结构组 |
| `verify_command_rules.py` | 独立命令与禁止选项检查 |
| `verify_mapped_outputs.py` | 最终器件映射后比较 |
| `patch_synth_intel_cc.py` | 生成及检查综合调用修改 |
| `build_general_candidate.py` | 使用已配置构建目录重新编译指定源码并链接 |
| `build_current_docs.cjs` | 根据指定结果生成可编辑报告 |
| `package_current.py` | 读取当前结果并生成真正的 RAR；默认不包含外部验证工具和视频 |
| `test_official_rules.py` | 效率统计方式检查 |
| `validation_support.py`、`delivery_runtime.py`、`pmux_preflight.py` | 当前入口调用的辅助功能 |
| `run_eqy.py` | 当前入口导入其工具函数；旧版直接执行方式不作为正式入口 |

`algorithm_cases/`、`generality_cases/`、`priority_cases/` 保存补充检查输入，不计入正式九例面积平均值。

从工程根目录调用这些脚本，并为重新执行的结果选择新目录。使用入口见[工程根目录 README](../README.md)。

## 文件位置索引（2026-11-04）

相对工程位置：`scripts/`。下表列出本层全部文件和子目录。

[返回上一层](../README.md)

| 名称与位置 | 类型及内容 |
|---|---|
| [algorithm_cases/](algorithm_cases/README.md) | 子目录；点击查看其全部文件位置 |
| [generality_cases/](generality_cases/README.md) | 子目录；点击查看其全部文件位置 |
| [priority_cases/](priority_cases/README.md) | 子目录；点击查看其全部文件位置 |
| [build_current_docs.cjs](build_current_docs.cjs) | JavaScript 源码 |
| [build_general_candidate.py](build_general_candidate.py) | Python 源码 |
| [delivery_runtime.py](delivery_runtime.py) | Python 源码 |
| [evaluate_official_nine.py](evaluate_official_nine.py) | Python 源码 |
| [measure_official_efficiency.py](measure_official_efficiency.py) | Python 源码 |
| [package_current.py](package_current.py) | Python 源码 |
| [patch_synth_intel_cc.py](patch_synth_intel_cc.py) | Python 源码 |
| [pmux_preflight.py](pmux_preflight.py) | Python 源码 |
| [README.md](README.md) | 本目录文件索引 |
| [run_eqy.py](run_eqy.py) | Python 源码 |
| [run_python.cmd](run_python.cmd) | Windows 命令脚本 |
| [test_official_rules.py](test_official_rules.py) | Python 源码 |
| [validation_support.py](validation_support.py) | Python 源码 |
| [verify_algorithm_changes.py](verify_algorithm_changes.py) | Python 源码 |
| [verify_command_rules.py](verify_command_rules.py) | Python 源码 |
| [verify_generality.py](verify_generality.py) | Python 源码 |
| [verify_mapped_outputs.py](verify_mapped_outputs.py) | Python 源码 |
| [verify_parameter_variants.py](verify_parameter_variants.py) | Python 源码 |
| [verify_priority_safety.py](verify_priority_safety.py) | Python 源码 |
| [verify_shipped_binary.py](verify_shipped_binary.py) | Python 源码 |

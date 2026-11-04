# 当前程序构建与检查

当前优化程序由最终PMUX源码及综合调用源码重新编译、链接。公开Yosys版本0.69+24，对应d0e71cfb7；ABC为该公开版本的配套子模块。两版共同应用Windows二进制输出修正。原有其他pass实现、步骤顺序与ABC9命令保持原样。

新增命令固定采用结构优化。额外综合与ABC实现已删除，两个可能进入额外综合的旧选项立即拒绝；本次独立命令检查均符合预期。

九例平均逻辑单元缩减 **21.590824805%**，逐例均未增加；DFF和顶层IO位数逐例与原版相同。正式九例两版的18项EQY全部通过，连同补充项目共69项EQY通过；两个禁止选项均按预期拒绝。

[编译输入](inputs.csv)、[PMUX编译输出](pmux_compile.txt)、[综合调用编译输出](synth_compile.txt)、[链接输出](link.txt)、[原版配置](configure.txt)、[程序与九例检查](file_check.json)。

编译入口位于 `../../scripts/build_general_candidate.py`，程序使用入口见[工程根目录 README](../../README.md)。本目录保留已有编译设置、输入清单及编译输出。

## 文件位置索引（2026-11-04）

相对工程位置：`results/current_build/`。下表列出本层全部文件和子目录。

[返回上一层](../README.md)

| 名称与位置 | 类型及内容 |
|---|---|
| [configure.txt](configure.txt) | 说明或执行输出 |
| [file_check.json](file_check.json) | 结果或配置文件 |
| [inputs.csv](inputs.csv) | 数据表 |
| [link.txt](link.txt) | 说明或执行输出 |
| [pmux_compile.txt](pmux_compile.txt) | 说明或执行输出 |
| [README.md](README.md) | 本目录文件索引 |
| [synth_compile.txt](synth_compile.txt) | 说明或执行输出 |

# 通用结构补充用例

这些输入与官方九例分开，不计入面积平均值。

- `decode_counterexample.v`：两个比较常量的共同位含0，显式启用较窄比较共享。
- `decode_wide_counterexample.v`：8位比较的共同位含0，分别检查默认共享及显式关闭。
- `shallow_w6.v`、`shallow_w17_signed.v`、`shallow_w5.v`：两层选择的不同位宽与符号，5位结构应保留原运算。
- `shallow_constants.v`：运算分支与常量分支混合。
- `shallow_external.v`：运算结果同时被树外输出使用，应跳过共享。
- `shallow_priority.v`：内部优先条件与多层默认路径。

从工程根目录执行 `scripts/run_python.cmd scripts/verify_generality.py --out <新目录>`，会同时检查 `scripts/priority_cases/` 的三个输入，共12项。检查保留所有真实输入输出，不按临时内部名称强制对应；故意取反真实输出后，工具必须报告不等价。

## 文件位置索引（2026-11-04）

相对工程位置：`scripts/generality_cases/`。下表列出本层全部文件和子目录。

[返回上一层](../README.md)

| 名称与位置 | 类型及内容 |
|---|---|
| [decode_counterexample.v](decode_counterexample.v) | Verilog 电路或模型 |
| [decode_wide_counterexample.v](decode_wide_counterexample.v) | Verilog 电路或模型 |
| [README.md](README.md) | 本目录文件索引 |
| [shallow_constants.v](shallow_constants.v) | Verilog 电路或模型 |
| [shallow_external.v](shallow_external.v) | Verilog 电路或模型 |
| [shallow_priority.v](shallow_priority.v) | Verilog 电路或模型 |
| [shallow_w17_signed.v](shallow_w17_signed.v) | Verilog 电路或模型 |
| [shallow_w5.v](shallow_w5.v) | Verilog 电路或模型 |
| [shallow_w6.v](shallow_w6.v) | Verilog 电路或模型 |

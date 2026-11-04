# 算法补充用例

此处11个小型输入用于检查寄存器初值和嵌套运算共享的边界，独立于cases目录下的九个官方用例。

g_init_mixed、g_init_alias：混合0/1初值及相连信号不同名称的初值。variant_w6、w9、w17、lanes2、signed：不同位宽、多路及有符号运算。variant_external_arithmetic、narrow_signed：外部读取和较窄输入。variant_partial_result、indirect_result：部分位拼接与间接表达式依赖，要求保持原电路，不执行新共享。

通过 scripts/verify_algorithm_changes.py --out <新目录> 执行。检查均比较原始RTL与当前程序实际输出，记录PROVEN结果；不会修改官方用例。

## 文件位置索引（2026-11-04）

相对工程位置：`scripts/algorithm_cases/`。下表列出本层全部文件和子目录。

[返回上一层](../README.md)

| 名称与位置 | 类型及内容 |
|---|---|
| [g_init_alias.v](g_init_alias.v) | Verilog 电路或模型 |
| [g_init_mixed.v](g_init_mixed.v) | Verilog 电路或模型 |
| [README.md](README.md) | 本目录文件索引 |
| [variant_external_arithmetic.v](variant_external_arithmetic.v) | Verilog 电路或模型 |
| [variant_indirect_result.v](variant_indirect_result.v) | Verilog 电路或模型 |
| [variant_lanes2.v](variant_lanes2.v) | Verilog 电路或模型 |
| [variant_narrow_signed.v](variant_narrow_signed.v) | Verilog 电路或模型 |
| [variant_partial_result.v](variant_partial_result.v) | Verilog 电路或模型 |
| [variant_signed.v](variant_signed.v) | Verilog 电路或模型 |
| [variant_w17.v](variant_w17.v) | Verilog 电路或模型 |
| [variant_w6.v](variant_w6.v) | Verilog 电路或模型 |
| [variant_w9.v](variant_w9.v) | Verilog 电路或模型 |

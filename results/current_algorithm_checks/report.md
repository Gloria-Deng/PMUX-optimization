# 初值与嵌套运算检查

本次当前程序完成11项EQY，全部PROVEN并成功返回。

覆盖明确初值、相连名称、不同位宽、符号、外部读取、部分结果和间接结果。适用时共享，不满足条件时保留原逻辑。

| 项目 | 程序 | 结果 |
|---|---|---|
| g_init_mixed | 优化版 | PROVEN |
| g_init_alias | 优化版 | PROVEN |
| variant_w6 | 优化版 | PROVEN |
| variant_w9 | 优化版 | PROVEN |
| variant_w17 | 优化版 | PROVEN |
| variant_lanes2 | 优化版 | PROVEN |
| variant_signed | 优化版 | PROVEN |
| variant_external_arithmetic | 优化版 | PROVEN |
| variant_narrow_signed | 优化版 | PROVEN |
| variant_partial_result | 优化版 | PROVEN |
| variant_indirect_result | 优化版 | PROVEN |

[逐项结果](formal.csv)、[完成状态](status.txt)。每项实际输入、综合命令、输出及EQY配置保存在本目录。

# 参数、位宽与共享路径检查

本次当前程序完成17项EQY，全部PROVEN并成功返回。

含新增五例的参数变化、加减运算的符号与截位、连续选择依赖及共享上游结构。参数变化不计入正式九例平均值。

| 项目 | 程序 | 结果 |
|---|---|---|
| pmux_case01_balanced_w4_l2 | stock | PROVEN |
| pmux_case01_balanced_w4_l2 | delivered | PROVEN |
| pmux_case02_pipeline_w5_l1 | stock | PROVEN |
| pmux_case02_pipeline_w5_l1 | delivered | PROVEN |
| pmux_case03_crossbar_w4_l1 | stock | PROVEN |
| pmux_case03_crossbar_w4_l1 | delivered | PROVEN |
| pmux_case04_feedback_w5_l1 | stock | PROVEN |
| pmux_case04_feedback_w5_l1 | delivered | PROVEN |
| pmux_case05_nested_w4_l2 | stock | PROVEN |
| pmux_case05_nested_w4_l2 | delivered | PROVEN |
| signed_add_wide | delivered | PROVEN |
| signed_add_narrow | delivered | PROVEN |
| signed_sub_truncated | delivered | PROVEN |
| unsigned_add_extended | delivered | PROVEN |
| unsigned_sub_truncated | delivered | PROVEN |
| dependent_selections | delivered | PROVEN |
| shared_upstream_cones | delivered | PROVEN |

[逐项结果](formal.csv)、[完成状态](status.txt)。每项实际输入、综合命令、输出及EQY配置保存在本目录。

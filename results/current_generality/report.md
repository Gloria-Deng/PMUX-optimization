# 通用结构与限制条件检查

本次当前程序完成12项EQY，全部PROVEN并成功返回。

覆盖优先链位次重排、外部读取、正常连接，以及宽比较共同0位、关闭选项、浅层运算共享与限制条件。其中包含3项优先链检查，不重复计数。

| 项目 | 程序 | 结果 |
|---|---|---|
| permuted_inner | 优化版 | PROVEN |
| register_reader | 优化版 | PROVEN |
| plain_chain | 优化版 | PROVEN |
| decode_narrow | 优化版 | PROVEN |
| decode_wide | 优化版 | PROVEN |
| decode_disabled | 优化版 | PROVEN |
| shallow_w6 | 优化版 | PROVEN |
| shallow_w17_signed | 优化版 | PROVEN |
| shallow_w5 | 优化版 | PROVEN |
| shallow_constants | 优化版 | PROVEN |
| shallow_external | 优化版 | PROVEN |
| shallow_priority | 优化版 | PROVEN |

[逐项结果](formal.csv)、[完成状态](status.txt)。每项实际输入、综合命令、输出及EQY配置保存在本目录。

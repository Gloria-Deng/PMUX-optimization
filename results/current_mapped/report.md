# 最终Cyclone IV网表检查

本次当前程序完成9项EQY，全部PROVEN并成功返回。

将九例完成器件映射后的优化网表分别与源RTL比较，验证寄存器初值、控制连接及最终组合逻辑。此组补充正式ABC9后位置的18项检查。

| 项目 | 程序 | 结果 |
|---|---|---|
| test1 | delivered | PROVEN |
| test2 | delivered | PROVEN |
| test3 | delivered | PROVEN |
| test4 | delivered | PROVEN |
| pmux_case01_balanced | delivered | PROVEN |
| pmux_case02_pipeline | delivered | PROVEN |
| pmux_case03_crossbar | delivered | PROVEN |
| pmux_case04_feedback | delivered | PROVEN |
| pmux_case05_nested | delivered | PROVEN |

[逐项结果](formal.csv)、[完成状态](status.txt)。每项实际输入、综合命令、输出及EQY配置保存在本目录。

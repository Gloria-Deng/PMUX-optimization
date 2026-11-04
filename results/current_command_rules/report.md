# 独立 PMUX 命令检查

整体结果：通过。

本组单列记录，未计入九例正式十八项 EQY。test2 经过 proc 与相同补零处理后，分别执行省略和显式加入 `-no-probe` 的独立命令。

| 检查 | 结果 | ABC次数 | ABC9次数 | 是否产生after.il |
|---|---|---|---|---|
| default | PROVEN | 0 | 0 | True |
| explicit_no_probe | PROVEN | 0 | 0 | True |
| reject_probe_all | REJECTED_AS_EXPECTED | 0 | 0 | False |
| reject_counter | REJECTED_AS_EXPECTED | 0 | 0 | False |

两种正常命令的 after.il 内容逐字节一致：True。两份结果各自与原始 RTL 完成 EQY。

两个禁止选项要求程序立即返回失败，出现对应提示，不调用 ABC，不产生后续 after.il，也不进入改写完成阶段。

`formal.csv` 记录逐项结果，`program.txt` 记录使用的程序。每项目录保存实际命令、程序输出；正常项另有 after.il、EQY 配置及完整证明输出。

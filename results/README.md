# 当前测试结果

九例平均逻辑单元缩减 **21.590824805%**，逐例均减少；DFF 和顶层 IO 位数逐例相同。正式九例两版共 **18 项 EQY 通过**，连同补充项目共 **69 项 EQY 通过**。两个禁止选项按预期拒绝，另列，不计入 EQY 通过数。

当前效率数据为 2026 年 11 月 3 日的 48 次综合，包含 10 次预热、18 次初测、20 次追加测量。完整经过时间最高增加 **0.669041949%**，主程序峰值工作集最高增加 **1.825690067%**。测试时 Defender 实时保护开启，尚未按官方要求关闭安全软件并统一后台条件后复测。

| 目录 | 用途 | EQY 通过数 |
|---|---|---:|
| [current_nine](current_nine/README.md) | 正式九例资源与两版功能检查；正文见 report.md | 18 |
| [current_efficiency](current_efficiency/README.md) | 同一程序、同一输入的 48 次效率测量 | 不重复计数 |
| [current_parameters](current_parameters/README.md) | 参数、位宽与共享路径 | 17 |
| [current_algorithm_checks](current_algorithm_checks/README.md) | 初值与嵌套运算 | 11 |
| [current_generality](current_generality/README.md) | 通用结构与限制条件，包含三项优先链检查 | 12 |
| [current_command_rules](current_command_rules/README.md) | 独立命令及禁止选项 | 2 |
| [current_mapped](current_mapped/README.md) | 最终器件映射后检查 | 9 |
| [current_build](current_build/README.md) | 当前程序的编译及对应检查材料 | 不适用 |
| [video_eqy_review_vgl9s0eb](video_eqy_review_vgl9s0eb/README.md) | 视频演示的 Tcl、直接比较、原始素材及执行输出 | 不计入上述 69 项 |

本目录保存已有程序执行所得的资源、功能和效率结果；各子目录 README 列出对应报告、数据表、比较配置及输出位置。

本次已移出重复测试目录、重复保存的优先链结果和不再使用的制作文件；当前结果没有被重新测量或替换。演示视频位于工程根目录，见[演示视频](../%E6%BC%94%E7%A4%BA%E8%A7%86%E9%A2%91_%E6%8F%90%E4%BA%A4%E7%89%88.mp4)。

## 文件位置索引（2026-11-04）

相对工程位置：`results/`。下表列出本层全部文件和子目录。

[返回上一层](../README.md)

| 名称与位置 | 类型及内容 |
|---|---|
| [current_algorithm_checks/](current_algorithm_checks/README.md) | 子目录；点击查看其全部文件位置 |
| [current_build/](current_build/README.md) | 子目录；点击查看其全部文件位置 |
| [current_command_rules/](current_command_rules/README.md) | 子目录；点击查看其全部文件位置 |
| [current_efficiency/](current_efficiency/README.md) | 子目录；点击查看其全部文件位置 |
| [current_generality/](current_generality/README.md) | 子目录；点击查看其全部文件位置 |
| [current_mapped/](current_mapped/README.md) | 子目录；点击查看其全部文件位置 |
| [current_nine/](current_nine/README.md) | 子目录；点击查看其全部文件位置 |
| [current_parameters/](current_parameters/README.md) | 子目录；点击查看其全部文件位置 |
| [video_eqy_review_vgl9s0eb/](video_eqy_review_vgl9s0eb/README.md) | 子目录；点击查看其全部文件位置 |
| [README.md](README.md) | 本目录文件索引 |

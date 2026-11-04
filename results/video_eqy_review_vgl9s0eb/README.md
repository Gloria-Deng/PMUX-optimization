# 视频演示材料

本目录保留当前演示所使用的实际操作和比较材料。正式视频位于工程根目录，见[演示视频](../../%E6%BC%94%E7%A4%BA%E8%A7%86%E9%A2%91_%E6%8F%90%E4%BA%A4%E7%89%88.mp4)，为 H.264、1920×1080、30 帧/秒，163.96 秒；原音轨完整保留。目录内两段原始素材不是最终提交片。

- `example.tcl`：通过 Yosys Tcl 接口调用 PMUX 命令，nested 用例执行成功；`tcl_output.txt` 保存当时输出。
- `ports_only.eqy`、`ports_only/`、`ports_only_output.txt`：原版和优化版 nested 的 ABC9 后、器件映射前设计直接比较；以顶层端口对应，12 位输出全部通过。
- `negative_control.eqy`、`negative_control/`、`negative_control_output.txt`、`altered_output.v`：故意反转优化版输出最低位后的比较。这里的 FAIL 是预期结果，说明错误电路会被拒绝。
- `eqy_demo.py`、`live_231044_013035/`：成片中显示的直接比较入口及当次成功输出。
- `真实补录.mp4`、`直接比较补录.mp4`：当前演示相关原始操作素材。
- `record_addition.py`、`record_eqy.py`：原电脑的录像辅助脚本，依赖原有桌面位置和附加软件；它们不属于运行优化程序所需入口，也不是最终桌面视频的完整生成方法。
- `.ass` 文件与 `录屏时间.csv`：已有字幕和原始片段时间信息。

首次未完成的直接比较、未进入成片的尝试、重复检查图片及引用已不存在文件的旧合成脚本，已移出提交工程。故意制造错误的比较和当前成片所用材料均保留。

正式九例仍为两版分别与原始 RTL 比较的 18 项，见 `../current_nine/formal.csv`；本目录只覆盖 nested 的直接比较，不增加正式通过总数。

## 文件位置索引（2026-11-04）

相对工程位置：`results/video_eqy_review_vgl9s0eb/`。下表列出本层全部文件和子目录。

[返回上一层](../README.md)

| 名称与位置 | 类型及内容 |
|---|---|
| [live_231044_013035/](live_231044_013035/README.md) | 子目录；点击查看其全部文件位置 |
| [negative_control/](negative_control/README.md) | 子目录；点击查看其全部文件位置 |
| [ports_only/](ports_only/README.md) | 子目录；点击查看其全部文件位置 |
| [algorithm_ass.ass](algorithm_ass.ass) | 字幕 |
| [altered_output.v](altered_output.v) | Verilog 电路或模型 |
| [direct_ass.ass](direct_ass.ass) | 字幕 |
| [eqy_demo.py](eqy_demo.py) | Python 源码 |
| [example.tcl](example.tcl) | 文件；用途结合本目录说明 |
| [negative_control.eqy](negative_control.eqy) | EQY 比较配置 |
| [negative_control_output.txt](negative_control_output.txt) | 说明或执行输出 |
| [ports_only.eqy](ports_only.eqy) | EQY 比较配置 |
| [ports_only_output.txt](ports_only_output.txt) | 说明或执行输出 |
| [README.md](README.md) | 本目录文件索引 |
| [record_addition.py](record_addition.py) | Python 源码 |
| [record_eqy.py](record_eqy.py) | Python 源码 |
| [tcl_ass.ass](tcl_ass.ass) | 字幕 |
| [tcl_output.txt](tcl_output.txt) | 说明或执行输出 |
| [录屏时间.csv](%E5%BD%95%E5%B1%8F%E6%97%B6%E9%97%B4.csv) | 数据表 |
| [直接比较补录.mp4](%E7%9B%B4%E6%8E%A5%E6%AF%94%E8%BE%83%E8%A1%A5%E5%BD%95.mp4) | 演示视频或素材 |
| [真实补录.mp4](%E7%9C%9F%E5%AE%9E%E8%A1%A5%E5%BD%95.mp4) | 演示视频或素材 |

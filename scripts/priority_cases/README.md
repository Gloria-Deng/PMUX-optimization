# 优先选择链连接检查

三个RTLIL输入直接构造目标结构，避免前序处理提前消除这些连接。

- `plain_chain.il`：完整同序总线、无额外读取，应执行优先链转换并保持等价。
- `permuted_inner.il`：相邻总线位次重排，应保留该连接。
- `register_reader.il`：中间结果同时进入寄存器D，应保留仍被读取的结果。

从工程根目录执行 `scripts/run_python.cmd scripts/verify_priority_safety.py --out <新目录>`。当前程序应全部通过。`verify_generality.py` 已包含这三项，无须重复运行才能得到12项完整结果。

## 文件位置索引（2026-11-04）

相对工程位置：`scripts/priority_cases/`。下表列出本层全部文件和子目录。

[返回上一层](../README.md)

| 名称与位置 | 类型及内容 |
|---|---|
| [permuted_inner.il](permuted_inner.il) | RTLIL 设计文件 |
| [plain_chain.il](plain_chain.il) | RTLIL 设计文件 |
| [README.md](README.md) | 本目录文件索引 |
| [register_reader.il](register_reader.il) | RTLIL 设计文件 |

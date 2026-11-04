# 优化源码与综合修改

- `pmux_opt_rtlil.cc`：新增 PMUX 优化命令的完整实现。
- `synth_intel.cc.patched`：应用综合调用修改后的完整源码。
- `synth_intel_pass.patch`：仅在原有 proc 后加入 PMUX 调用，保留原 ABC9 命令。
- `windows_binary_output.patch`：两版共同使用的 Windows 二进制输出修正。
- `dffeas_formal.v`：形式比较采用的寄存器功能模型。


源码中的改写入口已增加统一检查：遇到不完整的模块选择，或模块、连线、单元存在 keep 属性时，跳过本次改写。原作者版权许可与综合指令保留。

## 文件位置索引（2026-11-04）

相对工程位置：`plugin/`。下表列出本层全部文件和子目录。

[返回上一层](../README.md)

| 名称与位置 | 类型及内容 |
|---|---|
| [dffeas_formal.v](dffeas_formal.v) | Verilog 电路或模型 |
| [pmux_opt_rtlil.cc](pmux_opt_rtlil.cc) | C++ 源码 |
| [README.md](README.md) | 本目录文件索引 |
| [synth_intel.cc.patched](synth_intel.cc.patched) | 应用修改后的源码 |
| [synth_intel_pass.patch](synth_intel_pass.patch) | 源码修改文件 |
| [windows_binary_output.patch](windows_binary_output.patch) | 源码修改文件 |

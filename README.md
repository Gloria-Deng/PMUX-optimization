# Yosys PMUX 结构优化

我给 Yosys 加了一个综合步骤，在技术映射前整理多路选择逻辑。比如，两条路径选的是同一组数据，就可以合并重复的选择；几个互斥分支分别做同样的加减法时，可以先选操作数，再共用运算单元。改写在 `proc` 之后执行，原有的 ABC9 调用保持一致。 [C++ 实现](plugin/pmux_opt_rtlil.cc) · [接入补丁](plugin/synth_intel_pass.patch)

## 结果

用同版本 Yosys 0.69+24 综合 9 个电路，优化版的逻辑单元数平均减少 **21.59%**。例如 `crossbar` 从 408 降到 313，`nested` 从 413 降到 278。9 个电路的触发器数量和顶层端口位数均相同。原版、优化版分别与原始 RTL 比较，**18 项 EQY 等价检查全部通过**。 [逐例数据与检查配置](results/current_nine/report.md)

同一 Windows 环境的记录中，完整综合时间最多增加 **0.67%**，主程序峰值内存最多增加 **1.83%**。 [测量条件与逐次结果](results/current_efficiency/report.md)

## 运行比较

安装 Git LFS 后克隆仓库。在 Windows PowerShell 中从仓库根目录执行：

```powershell
.\scripts\run_python.cmd scripts/evaluate_official_nine.py --out results/new_nine --phase synthesis
```

脚本为两版程序准备所需的 DLL 和器件模型，并把 9 个电路的资源对比写入 `results/new_nine`。把 `--phase synthesis` 改成 `--phase all` 可加跑 EQY，重新执行时请选择新的输出目录。 [脚本与依赖](scripts/README.md)

[`plugin/`](plugin/) 放实现和补丁，[`cases/`](cases/) 放测试电路，[`binary/`](binary/) 提供两版 Windows 程序和依赖。完整原理见 [技术说明 PDF](%E6%8A%80%E6%9C%AF%E6%96%87%E6%A1%A3%20.pdf)。

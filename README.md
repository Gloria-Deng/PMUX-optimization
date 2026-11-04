# PMUX 结构优化工程

本目录包含 PMUX 优化源码、原版与优化版 Windows 程序、九个测试电路、已有测试结果，以及技术报告和演示视频。所用 Yosys 版本为 0.69+24，公开源码版本为 d0e71cfb7，ABC 对应 1e3d9ab。

## 主要材料

技术文档和视频位于工程根目录，文件名按实际保存名称列出。授权书扫描件含个人信息，不随本仓库公开，随赛题单独提交。

| 文件位置 | 内容 |
|---|---|
| [技术文档 .pdf](%E6%8A%80%E6%9C%AF%E6%96%87%E6%A1%A3%20.pdf) | 作品说明、优化算法与结果 |
| [演示视频_提交版.mp4](%E6%BC%94%E7%A4%BA%E8%A7%86%E9%A2%91_%E6%8F%90%E4%BA%A4%E7%89%88.mp4) | 作品运行演示 |

授权书扫描件为 `参赛作品承诺及使用授权书_扫描件.pdf`，含个人信息，未随公开仓库发布。

## 目录用途

| 目录位置 | 内容 |
|---|---|
| [plugin/](plugin/README.md) | PMUX 源码、综合调用修改、Windows 输出修正和寄存器模型 |
| [binary/](binary/README.md) | 优化版程序、原版程序、运行依赖和原作者许可 |
| [cases/](cases/README.md) | 四个原始电路和五个新增电路 |
| [scripts/](scripts/README.md) | 综合、EQY、效率测量、补充检查和打包入口 |
| [results/](results/README.md) | 已保存的资源、功能、效率和视频比较结果 |

## 已有结果

已有九例结果记录的平均逻辑单元缩减率为 **21.590824805%**，逐例均减少，DFF 和顶层 IO 位数逐例相同。正式九例共 **18 项 EQY 通过**，加补充项目共 **69 项 EQY 通过**；两个禁止选项的拒绝检查另计。

已有 48 次效率测量包含 10 次预热、18 次初测和 20 次追加测量。完整经过时间最高增加 **0.669041949%**，主程序峰值工作集最高增加 **1.825690067%**。这些数据取得时 Defender 实时保护开启；具体运行条件和逐次读数见 [效率结果目录](results/current_efficiency/README.md)。

## 获取仓库

`binary/formal/sources/` 下的第三方源码包使用 Git LFS 存储，克隆前请先安装 git-lfs：

```bash
git lfs install
git clone <仓库地址>
```

未安装 git-lfs 时，这些 `.src.tar.zst` 只会检出指向 LFS 对象的指针文本，而不是源码包本身。

## 运行入口

在本目录打开 PowerShell：

```powershell
.\binary\yosys.exe -V
.\binary\baseline\yosys.exe -V
```

需要重新执行时，为输出选择新的目录：

```powershell
.\scripts\run_python.cmd scripts/evaluate_official_nine.py --out results/new_nine --phase all
.\scripts\run_python.cmd scripts/measure_official_efficiency.py --assessment results/new_nine --out results/new_efficiency
```

本地 `binary/formal/` 保存 EQY、Python 和辅助程序；使用外部 OSS CAD Suite 时按实际位置设置 `OSS_CAD_SUITE`，必要时设置 `PMUX_MAKE_DIRS`。正式九例入口是 `evaluate_official_nine.py`，其他脚本的用途见 [scripts/README.md](scripts/README.md)。

## 文件导航

本工程按当前实际目录逐层编写 README。每层索引列出本层全部文件，并通过子目录 README 继续查找。材料文件保留实际名称，包括文件名中已有的空格。

## 文件位置索引（2026-11-04）

相对工程位置：`./`。下表列出本层全部文件和子目录。

| 名称与位置 | 类型及内容 |
|---|---|
| [binary/](binary/README.md) | 子目录；点击查看其全部文件位置 |
| [cases/](cases/README.md) | 子目录；点击查看其全部文件位置 |
| [plugin/](plugin/README.md) | 子目录；点击查看其全部文件位置 |
| [results/](results/README.md) | 子目录；点击查看其全部文件位置 |
| [scripts/](scripts/README.md) | 子目录；点击查看其全部文件位置 |
| [README.md](README.md) | 本目录文件索引 |
| `参赛作品承诺及使用授权书_扫描件.pdf` | PDF 文档；含个人信息，未随公开仓库发布 |
| [技术文档 .pdf](%E6%8A%80%E6%9C%AF%E6%96%87%E6%A1%A3%20.pdf) | PDF 文档 |
| [演示视频_提交版.mp4](%E6%BC%94%E7%A4%BA%E8%A7%86%E9%A2%91_%E6%8F%90%E4%BA%A4%E7%89%88.mp4) | 演示视频或素材 |

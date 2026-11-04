# Windows 程序与依赖

- `yosys.exe`：当前优化版 Yosys 0.69+24。
- `baseline/yosys.exe`：用于同条件比较的原版程序。
- `yosys-abc.exe`：两版共同使用的 ABC。
- 本层 DLL 和 `share/`：综合程序需要的运行库与器件模型。
- `licenses/`：原作者版权和许可，不应删除。
- `MANIFEST.json`：版本、文件内容和结果目录说明。
- `formal/`：完整本地工程的 EQY、验证用 Yosys、Python 和辅助程序；正式 RAR 默认不包含该目录。

正式 RAR 依赖赛事方提供并调试 OSS CAD Suite，按实际路径设置 OSS_CAD_SUITE 和必要的 PMUX_MAKE_DIRS。

## 文件位置索引（2026-11-04）

相对工程位置：`binary/`。下表列出本层全部文件和子目录。

[返回上一层](../README.md)

| 名称与位置 | 类型及内容 |
|---|---|
| [baseline/](baseline/README.md) | 子目录；点击查看其全部文件位置 |
| [formal/](formal/README.md) | 子目录；点击查看其全部文件位置 |
| [licenses/](licenses/README.md) | 子目录；点击查看其全部文件位置 |
| [share/](share/README.md) | 子目录；点击查看其全部文件位置 |
| [libffi-8.dll](libffi-8.dll) | 程序运行依赖 |
| [libgcc_s_seh-1.dll](libgcc_s_seh-1.dll) | 程序运行依赖 |
| [libreadline8.dll](libreadline8.dll) | 程序运行依赖 |
| [libstdc++-6.dll](libstdc%2B%2B-6.dll) | 程序运行依赖 |
| [libtermcap-0.dll](libtermcap-0.dll) | 程序运行依赖 |
| [libwinpthread-1.dll](libwinpthread-1.dll) | 程序运行依赖 |
| [MANIFEST.json](MANIFEST.json) | 结果或配置文件 |
| [README.md](README.md) | 本目录文件索引 |
| [tcl86.dll](tcl86.dll) | 程序运行依赖 |
| [yosys-abc.exe](yosys-abc.exe) | 程序 |
| [yosys.exe](yosys.exe) | 程序 |
| [zlib1.dll](zlib1.dll) | 程序运行依赖 |

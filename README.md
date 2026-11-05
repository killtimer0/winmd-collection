# winmd-collection

为 Winlex 获取和生成 Windows 元数据，统一汇总来源、许可和文件哈希。

## 获取与验证

需要 Python 3.10+ 和 PowerShell 7.2+。生成 UCRT 前，先按[生成器文档](tools/ucrt-winmd/README.md#prerequisites)安装构建工具。

```powershell
pwsh tools/ucrt-winmd/build.ps1 -Check
python scripts/prepare-metadata.py --ucrt-output tools/ucrt-winmd/out
python scripts/verify-metadata.py --winlex 'D:/Tools/winlex.exe'
```

下载缓存放在 `tmp/deps/`，成品放在 `artifacts/`：

```text
artifacts/
├── Windows.Win32.winmd
├── Windows.Wdk.winmd
├── Windows.winmd
├── UCRT.winmd
├── …其余 WinUI、Win2D 的 WinMD
├── SHA256SUMS
├── SOURCES.md
└── licenses/
```

`SOURCES.md` 按来源列出文件、版本和官方链接；`licenses/` 保留许可及依赖说明；`SHA256SUMS` 汇总成品文件和说明文件的哈希。

只下载某个包时，使用 `python scripts/prepare-metadata.py --source win32`。
准备 WinUI 需要同时选择 `winui`、`winui-base`、`winui-foundation` 和 `winui-interactive`（重复传入 `--source`）。验证脚本需要全部六类来源准备齐全，并生成来源说明和哈希清单。

WinRT 从 SDK 的 `UnionMetadata/<版本>/Windows.winmd` 提取。WinRT 和 UCRT 共用 SDK 发现逻辑，默认选择最新已安装版本。固定版本时，向 UCRT 构建脚本传入 `-SdkIncludePath`，向准备脚本传入 `--sdk-include`，使用同一个 SDK Include 目录。

## 元数据来源

来源版本和文件哈希见下表；下载包还记录下载地址，并保留包内的依赖和许可说明。

| 来源 | 清单 |
| --- | --- |
| Win32 | [win32.json](sources/win32.json) |
| WDK | [wdk.json](sources/wdk.json) |
| WinRT（SDK 的 `Windows.winmd`） | [winrt.json](sources/winrt.json) |
| WinUI | [WinUI](sources/winui.json)、[Base](sources/winui-base.json)、[Foundation](sources/winui-foundation.json)、[InteractiveExperiences](sources/winui-interactive.json) |
| Win2D | [win2d.json](sources/win2d.json) |
| UCRT（从 SDK／MSVC 头文件生成） | [ucrt.json](sources/ucrt.json) |

查询涉及其他来源的类型时，需要一起加载对应元数据：WDK 引用 Win32，WinUI 引用 WinRT，Win2D 引用 WinUI 和 WinRT。验证脚本也按这些组合加载文件。

## UCRT

生成器用法见 [`tools/ucrt-winmd/`](tools/ucrt-winmd/README.md)。构建时加上 `-WinlexPath <CLI绝对路径>`，可额外检查 Winlex 查询和布局结果。

`--ucrt-output` 导入通过 `-Check` 的生成结果，并更新 `sources/ucrt.json`。详细 manifest、分架构基线和日志位于 `tools/ucrt-winmd/out/`。

## 许可与发布

工具源码采用 [GPL-3.0-only](LICENSE)。发布前见 [UPLOAD.md](UPLOAD.md)。

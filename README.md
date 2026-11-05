# winmd-collection

为 Winlex 获取和生成 Windows 元数据，统一汇总来源、许可和文件哈希。

## 获取与验证

需要 Python 3.10+ 和 PowerShell 7.2+。生成 UCRT 前，先按[生成器文档](tools/ucrt-winmd/README.md#prerequisites)安装构建工具。

```powershell
pwsh tools/ucrt-winmd/build.ps1 -Check
python scripts/prepare-metadata.py --ucrt-output tools/ucrt-winmd/out
python scripts/verify-metadata.py
```

下载缓存位于 `tmp/deps/`，成品位于 `artifacts/`。目录中的 `SOURCES.md`、`licenses/` 和 `SHA256SUMS` 分别提供来源与依赖说明、许可和文件哈希。

只下载某个包时，使用 `python scripts/prepare-metadata.py --source win32`。
`--source winui` 准备 Windows App SDK 聚合元数据。验证脚本需要全部来源准备齐全，并生成来源说明和哈希清单。
向验证脚本传入 `--winlex <CLI路径>`，可追加查询验证。

WinRT 从 SDK 的 `UnionMetadata/<版本>/Windows.winmd` 提取。WinRT 和 UCRT 共用 SDK 发现逻辑，默认选择最新已安装版本。固定版本时，向 UCRT 构建脚本传入 `-SdkIncludePath`，向准备脚本传入 `--sdk-include`，使用同一个 SDK Include 目录。

Windows App SDK 的组件合并为 `Microsoft.winmd`，WebView2 单独交付为 `Microsoft.Web.WebView2.Core.winmd`。构建来源见下方清单。

## 元数据来源

来源版本和文件哈希见下表；下载包还记录下载地址，并保留包内的依赖和许可说明。

| 来源 | 清单 |
| --- | --- |
| Win32 | [win32.json](sources/win32.json) |
| WDK | [wdk.json](sources/wdk.json) |
| WinRT（SDK 的 `Windows.winmd`） | [winrt.json](sources/winrt.json) |
| Windows App SDK（含 WinUI） | [winui.json](sources/winui.json) |
| WebView2 | [webview2.json](sources/webview2.json) |
| Win2D | [win2d.json](sources/win2d.json) |
| UCRT（从 SDK／MSVC 头文件生成） | [ucrt.json](sources/ucrt.json) |

查询时按 `artifacts/SOURCES.md` 中的依赖说明一起加载对应元数据。

## UCRT

生成器用法见 [`tools/ucrt-winmd/`](tools/ucrt-winmd/README.md)。构建时加上 `-WinlexPath <CLI绝对路径>`，可额外检查 Winlex 查询和布局结果。

`--ucrt-output` 导入通过 `-Check` 的生成结果，并更新 `sources/ucrt.json`。详细 manifest、分架构基线和日志位于 `tools/ucrt-winmd/out/`。

## 许可与发布

工具源码采用 [GPL-3.0-only](LICENSE)。发布前见 [UPLOAD.md](UPLOAD.md)。

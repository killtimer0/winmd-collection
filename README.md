# winmd-collection

独立准备 Windows 元数据的工具集合。元数据按来源分别获取、生成和验证，不合并为一个大 WinMD，也不绑定 Winlex 版本。

## 获取与验证

需要 Python 3.10+；全部六类来源还需按下文准备 UCRT 生成环境。完整准备顺序：

```powershell
pwsh tools/ucrt-winmd/build.ps1 -Check
python scripts/prepare-metadata.py --ucrt-output tools/ucrt-winmd/out
python scripts/verify-metadata.py --winlex 'D:/Tools/winlex.exe'
python scripts/package-metadata.py
```

下载缓存位于 `tmp/deps/`，成品及逐来源压缩包和 SHA-256 清单位于 `artifacts/`。可使用 `--source win32` 等选项只准备指定包；WinUI 还需 `winui-base`、`winui-foundation`、`winui-interactive`。验证显式加载 WDK + Win32、WinUI + WinRT、Win2D + WinUI + WinRT，不将所有来源默认混合。WinRT Contracts 不应与 SDK 单体 Windows.winmd 叠加。

| 来源 | 固定版本 | 记录 |
| --- | --- | --- |
| Win32 | 71.0.37-preview | [win32.json](sources/win32.json) |
| WDK | 0.13.25-experimental | [wdk.json](sources/wdk.json)，上游仅提供实验版本 |
| WinRT | Contracts 10.0.28000.2957 | [winrt.json](sources/winrt.json)，96 个独立 WinMD |
| WinUI | Windows App SDK 2.6.5 | [组件](sources/winui.json)、[Base](sources/winui-base.json)、[Foundation](sources/winui-foundation.json)、[InteractiveExperiences](sources/winui-interactive.json) |
| Win2D | 1.4.0 | [win2d.json](sources/win2d.json)，包内两个 WinMD 字节相同，仅保留一个 |
| UCRT | SDK 10.0.26100.0 / MSVC 14.51.36231 | [ucrt.json](sources/ucrt.json)，由源码生成，不是下载包 |

各记录包含包 URL、包与所选成员 SHA-256；包内 nuspec 和许可文件随成品保留。Contracts 和 Win2D 包未包含许可文件，许可 URL 和依赖约束见其 nuspec。WinUI 的 InteractiveExperiences 使用 10.0.17763.0 元数据变体，不混用另一变体。依赖约束不是对运行时兼容性的保证。

## UCRT

生成器位于 [`tools/ucrt-winmd/`](tools/ucrt-winmd/README.md)，保留独立 Cargo workspace、许可证、来源及严格布局验证。

```powershell
pwsh tools/ucrt-winmd/build.ps1 -Check
```

可用 `-WinlexPath <CLI绝对路径>` 显式启用集成验证；不要求安装 Winlex，也不依赖同级目录布局。

`--ucrt-output` 校验合并文件与生成器 manifest、一致的三架构覆盖及 `-Check` 结果后，导入 WinMD、原始 manifest 和工具许可证，并刷新 `sources/ucrt.json` 的生成版本及哈希。新环境生成的 manifest 不必与其他机器字节相同。原始 manifest 含本机路径，分享前须审查；不得将本机 SDK 头文件打包。

WDK 的 nuspec 声明 Win32Metadata 63.0.31-preview 依赖，此集合选择固定的较新 71.0.37-preview 并执行查询验证，不宣称不同版本完全等价。保留的 nuspec 还包含运行时和构建依赖；此集合仅准备元数据，不安装组件运行时，也不保证所有外部类型引用都可解析。

## 分发边界

工具源码采用根目录 GPL-3.0-only 许可证；输入包、微软头文件及生成元数据的授权独立于工具源码。来源记录与哈希不代表已获公开再分发许可，公开上传成品前需确认对应条款。

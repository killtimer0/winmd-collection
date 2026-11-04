# winmd-collection

独立准备 Windows 元数据的工具集合。元数据按来源分别获取、生成和验证，不合并为一个大 WinMD，也不绑定 Winlex 版本。

## Win32

需要 Python 3.10+：

```powershell
python scripts/prepare-metadata.py
```

固定来源、版本及输出 SHA-256 见 `sources/win32.json`。下载缓存位于 `tmp/deps/`，验证后的成品位于 `artifacts/win32/`。

## UCRT

生成器位于 [`tools/ucrt-winmd/`](tools/ucrt-winmd/README.md)，保留独立 Cargo workspace、许可证、来源及严格布局验证。

```powershell
pwsh tools/ucrt-winmd/build.ps1 -Check
```

可用 `-WinlexPath <CLI绝对路径>` 显式启用集成验证；不要求安装 Winlex，也不依赖同级目录布局。

## 分发边界

工具源码的许可证见各工具目录。输入包、微软头文件及生成元数据的授权独立于工具源码；来源记录与哈希不代表已获公开再分发许可。公开上传成品前需确认对应条款。

# 手动交付

## 源码

- 将本仓库源码上传至独立远程仓库。
- 工具源码采用 GPL-3.0-only（见 `LICENSE`）；vendored 依赖保留各自许可，见 `tools/ucrt-winmd/THIRD-PARTY-NOTICES.md`。

## 元数据成品

- 成品 WinMD 位于 `artifacts/`。
- 交付时保留 `SHA256SUMS`、`SOURCES.md` 和 `licenses/`。它们汇总文件哈希、来源版本及链接，并保留许可和依赖说明。
- UCRT 的详细生成 manifest 位于 `tools/ucrt-winmd/out/`；汇总中记录其哈希、生成器源码版本和 SDK／MSVC 版本。
- 更新来源后，重新准备并验证元数据及其依赖。

## 地址

成品公开发布后，将下载地址更新到 Winlex 的 `docs/metadata.md`。

# 发布

## GitHub Actions

推送 `v*` 标签后，工作流构建并验证元数据，创建附带 WinMD、来源说明、哈希清单和 `licenses.zip` 的草稿 Release。候选版本标签标记为预发布。

在 Actions 页面手动运行工作流，可下载 `metadata` 构建产物。工具链选择见 [release.yml](.github/workflows/release.yml)。

公开发布前，核实 SDK 元数据和生成 UCRT 元数据的再分发条款，并检查草稿附件。

## 源码

- 将本仓库源码上传至独立远程仓库。
- 工具源码采用 GPL-3.0-only（见 `LICENSE`）；vendored 依赖保留各自许可，见 `tools/ucrt-winmd/THIRD-PARTY-NOTICES.md`。

## 元数据成品

- 成品 WinMD 位于 `artifacts/`。
- 交付时保留 `SHA256SUMS`、`SOURCES.md` 和 `licenses/`。它们汇总文件哈希、来源版本及链接，并保留许可和依赖说明。
- UCRT 的详细生成 manifest 位于 `tools/ucrt-winmd/out/`；汇总中记录其哈希、生成器源码版本和 SDK／MSVC 版本。
- 更新来源后，重新准备并验证元数据及其依赖。

# 手动交付

## 源码

- 将本仓库源码上传至独立远程仓库。
- 工具源码采用 GPL-3.0-only（见 `LICENSE`）；vendored 依赖保留各自许可，见 `tools/ucrt-winmd/THIRD-PARTY-NOTICES.md`。

## 元数据成品

- 成品位于 `artifacts/<来源>/`，按来源发布，勿合并为一个大 WinMD。
- 保留来源版本和输出 SHA-256；下载包另保留官方 URL、包 SHA-256、包内许可及依赖说明。WinRT 记录 SDK 版本和文件位置，UCRT 另保留生成 manifest 和生成器源码版本。
- 这些来源不与 Winlex 版本一一绑定。更新某一来源时单独重新准备、校验并验证其依赖。
- WinRT 使用 SDK 的单个 `Windows.winmd`。

## 地址

成品公开发布后，将下载地址更新到 Winlex 的 `docs/metadata.md`。

# 手动交付

## 源码

- 将本仓库源码上传至独立远程仓库。
- 工具源码采用 GPL-3.0-only（见 `LICENSE`）；vendored 依赖保留各自许可，见 `tools/ucrt-winmd/THIRD-PARTY-NOTICES.md`。

## 元数据成品

- 成品位于 `artifacts/<来源>/`，按来源发布，勿合并为一个大 WinMD。
- 保留来源版本、官方包 URL、输出与包 SHA-256、包内许可及依赖说明；UCRT 另保留生成 manifest 和生成器源码版本。
- 这些来源不与 Winlex 版本一一绑定。更新某一来源时单独重新准备、校验并验证其依赖。
- WinRT Contracts 与 SDK 的单体 `Windows.winmd` 是替代输入，不默认叠加二者；同一组件的多架构重复 WinMD 也不应一起加载。

## 地址

成品公开发布后，将下载地址更新到 Winlex 的 `docs/metadata.md`。

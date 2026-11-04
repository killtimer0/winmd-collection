# 手动交付

## 源码

- 创建独立远程仓库后，将本仓库源码上传；不使用子模块。
- 不上传 `tmp/`、Rust `target/`、本机 SDK／MSVC 头文件、缓存或本机验证日志。
- 工具源码采用 GPL-3.0-only（见 `LICENSE`）；vendored 依赖保留各自许可，见 `tools/ucrt-winmd/THIRD-PARTY-NOTICES.md`。
- 本仓库不包含自动生成或上传 WinMD 的 CI。

## 元数据成品

- 成品位于 `artifacts/<来源>/`，按来源发布，勿合并为一个大 WinMD。
- 保留来源版本、官方包 URL、输出与包 SHA-256、包内许可及依赖说明；UCRT 另保留生成 manifest 和生成器源码版本。
- 这些来源不与 Winlex 版本一一绑定。更新某一来源时单独重新准备、校验并验证其依赖。
- WinRT Contracts 与 SDK 的单体 `Windows.winmd` 是替代输入，不默认叠加二者；同一组件的多架构重复 WinMD 也不应一起加载。
- 微软输入包与头文件派生产物的公开再分发授权尚未确认。完成相应确认之前，只提供官方获取方式，不公开上传这些成品。独立仓库或手动上传不改变授权边界。

## 地址

成品托管位置待用户确定，建议采用独立项目的 Releases。确定后更新 Winlex 的 `docs/metadata.md`；不得使用占位地址冒充可用下载链接。

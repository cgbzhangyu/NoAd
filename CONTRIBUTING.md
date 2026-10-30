# Contributing

NoAd 只接受特定 App 的精确 HTTPS 广告接口规则，不接受通用广告域名表、节点、DNS、代理策略或整套配置。

每次规则变更必须包含：

- 稳定且以 App ID 开头的规则 ID，以及范围明确的用途。
- 公开证据 URL、许可证和 `derived` / `evidence-only` 用法。
- 最小 MITM 主机列表、风险等级和关键业务影响分析。
- 脱敏的匹配示例、静态测试和真实设备回归结果。

不要提交 Cookie、Token、账号标识、带查询参数的完整 URL、请求或响应正文、HAR、CA 私钥，以及未经许可证审查的第三方脚本。规则不得强制用户流量走 `DIRECT` 或 `PROXY`。

通用广告拦截由 README 中的两个上游规则集负责，不要把它们复制到 `catalog/apps/` 或 `dist/apps/`。

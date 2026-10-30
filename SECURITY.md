# Security Policy

NoAd 不需要用户 Cookie、Token、账号标识、完整请求 URL、请求或响应正文、HAR、CA 私钥或支付信息。

请通过 GitHub 私有漏洞报告提交规则投毒、过宽 MITM 范围、外部脚本注入或凭据泄漏问题。普通误杀请使用 Issue 模板，只提供脱敏后的主机和路径信息。

生成的 App 模块不得包含通用域名表、`RULE-SET`、`DOMAIN-SET`、`DIRECT` / `PROXY`、DNS 修改或证书材料。MITM 必须限制到目标 App 的必要主机；运行脚本必须由本仓库托管并接受静态审计。

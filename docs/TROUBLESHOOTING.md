# 故障排查与回退

## 登录、支付、购物车、播放或菜谱异常

1. 在 Shadowrocket → 配置 → 模块中关闭对应 App 模块。
2. 重新连接 Shadowrocket，并完全结束目标 App 后重开。
3. 如果功能恢复，记录模块版本、规则 ID 和不含查询参数的请求路径。
4. 不要通过关闭 TLS 校验、安装第三方证书或提交敏感抓包来排查。

## 广告仍然出现

- 确认全局路由为“配置”，App 模块已启用，HTTPS 解密已打开，证书已安装并被 iOS 完全信任。
- 更新模块后重新连接 Shadowrocket；旧模块地址位于 `dist/experimental/` 时，应删除后改用 `dist/apps/` 新地址。
- 开屏素材可能已经缓存；先连续冷启动观察，再使用 App 自带缓存清理。
- 哔哩哔哩日志应出现 `/x/v2/splash/show` 或 `/x/v2/splash/list`，并命中 `NoAd_BiliBili_开屏广告清理`。
- 如果广告一直是同一张，通常说明旧素材仍在 App 本地缓存，或接口没有命中新脚本；不要扩大到整个共享业务域名。
- 新接口只有在公开来源或脱敏日志支持后，才能加入对应 App 目录。

## 通用规则未命中

确认 `[Rule]` 使用的是：

```ini
RULE-SET,<Advertising.list URL>,REJECT
DOMAIN-SET,<Advertising_Domain.list URL>,REJECT
```

不要把两个类型写反，也不要把它们作为模块导入。

## 安全日志格式

```text
time=2026-10-30T20:00:00+08:00
app=jd
app_version=<version>
host=api.m.jd.com
path=/client.action
query=<removed>
rule_id=jd.launch.client-action
result=<blocked|not-matched|business-failure>
```

## 回滚

- 紧急回退：关闭或删除对应 App 模块，不会删除现有节点和代理订阅。
- 版本回退：使用上一 commit 或 tag 的不可变 `raw.githubusercontent.com` 地址。

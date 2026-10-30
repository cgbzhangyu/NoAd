# 故障排查与回退

## 登录、支付、购物车、播放或菜谱异常

1. 在 Shadowrocket → 配置 → 模块中关闭对应 App 模块。
2. 重新连接 Shadowrocket，并完全结束目标 App 后重开。
3. 如果功能恢复，记录模块版本、规则 ID 和不含查询参数的请求路径。
4. 不要通过关闭 TLS 校验、安装第三方证书或提交敏感抓包来排查。

## 广告仍然出现

- 确认全局路由为“配置”，模块已启用且 Shadowrocket 已重新连接。
- 开屏素材可能已经缓存；先连续冷启动观察，再使用 App 自带缓存清理。
- 哔哩哔哩代理日志应出现完整的 `/x/v2/splash/show` 或 `/x/v2/splash/list` HTTPS 路径；如果仍命中旧的 `REJECT-DICT`，说明 Shadowrocket 仍在使用旧模块缓存，请更新模块并重新连接。
- 稳定版覆盖有限是设计选择，不要把共享业务域名整体加入 `REJECT`。
- 未命中的新接口只能作为候选规则，在公开来源或脱敏日志支持后进入实验层。

## 安全日志格式

```text
time=2026-10-29T20:00:00+08:00
app=jd
app_version=<version>
host=api.m.jd.com
path=/client.action
query=<removed>
rule_id=jd.launch.client-action
result=<blocked|not-matched|business-failure>
```

## 回滚

- 紧急回退：关闭或删除对应模块，不会删除现有节点和代理订阅。
- 版本回退：改用上一 GitHub Release 的不可变模块链接。
- 稳定通道回退：维护者通过回滚工作流重新发布历史 tag 的产物，禁止强推 `stable`。


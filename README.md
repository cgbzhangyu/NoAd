# NoAd

NoAd 只维护针对特定 App、需要 HTTPS 解密的精确广告接口规则。通用广告域名不在本仓库复制维护，直接引用 `blackmatrix7/ios_rule_script` 的两个上游规则集。

本项目不会修改节点、代理订阅、DNS 或证书，也不提供整套 Shadowrocket 配置。

## 通用广告规则

在 Shadowrocket 当前配置的 `[Rule]` 中加入以下两行：

```ini
RULE-SET,https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Shadowrocket/Advertising/Advertising.list,REJECT
DOMAIN-SET,https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Shadowrocket/Advertising/Advertising_Domain.list,REJECT
```

- `Advertising.list` 必须使用 `RULE-SET`。
- `Advertising_Domain.list` 必须使用 `DOMAIN-SET`。
- 这两个地址是远程规则集，不是模块地址，不要在“模块”页面下载。
- 上游更新后，在 Shadowrocket 中刷新远程规则集即可；NoAd 不保存它们的副本。

## App 专用模块

按需添加，不要一次启用不使用的 App：

| App | 模块地址 | 当前目标 |
| --- | --- | --- |
| 哔哩哔哩 | [bilibili.sgmodule](https://raw.githubusercontent.com/cgbzhangyu/NoAd/refs/heads/main/dist/apps/bilibili.sgmodule) | v2 开屏广告响应 |
| 下厨房 | [xiachufang.sgmodule](https://raw.githubusercontent.com/cgbzhangyu/NoAd/refs/heads/main/dist/apps/xiachufang.sgmodule) | 广告 API |
| 淘宝 | [taobao.sgmodule](https://raw.githubusercontent.com/cgbzhangyu/NoAd/refs/heads/main/dist/apps/taobao.sgmodule) | 广告服务接口 |
| 京东 | [jd.sgmodule](https://raw.githubusercontent.com/cgbzhangyu/NoAd/refs/heads/main/dist/apps/jd.sgmodule) | 开屏配置与广告交换路径 |
| 什么值得买 | [smzdm.sgmodule](https://raw.githubusercontent.com/cgbzhangyu/NoAd/refs/heads/main/dist/apps/smzdm.sgmodule) | 第三方广告接口 |

旧的 `dist/experimental/`、`dist/canary/` 和 `all.sgmodule` 已取消。之前安装过旧地址的模块，需要删除后用上表的新地址重新添加。

## HTTPS 解密

所有 App 模块都包含最小范围的 `[MITM]` 主机列表。使用前必须：

1. 在 Shadowrocket 中生成并安装证书。
2. 在 iOS“设置 → 通用 → 关于本机 → 证书信任设置”中完全信任该证书。
3. 打开 Shadowrocket 的 HTTPS 解密，并启用对应 App 模块。
4. 重新连接 Shadowrocket，完全结束目标 App 后再冷启动测试。

如果 App 登录、购物车、支付、播放等功能异常，立即关闭对应 App 模块。详见 [故障排查](docs/TROUBLESHOOTING.md)。

## 仓库结构

```text
catalog/apps/   App 规则源数据
dist/apps/      可直接导入的 App 模块
runtime/        本仓库拥有并审计的响应脚本
scripts/        校验与生成工具
tests/          静态测试
```

仓库不会生成或托管通用广告规则副本。`catalog/sources.json` 只记录 App 规则的公开证据来源。

## 本地校验

```powershell
python scripts/noad.py validate
python scripts/noad.py build --check
python -m unittest discover -s tests -v
```

修改目录后运行 `python scripts/noad.py build` 重新生成 `dist/apps/`。

## 许可证

本项目使用 GPL-2.0-only。派生规则的来源与许可证记录在各 App 目录和 `catalog/sources.json` 中。

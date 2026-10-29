# NoAd

NoAd 是一个安全优先、可审计、可长期维护的 iOS Shadowrocket 去广告规则库。它不会替换现有节点、机场订阅、代理组、DNS 或完整配置文件；未命中广告规则的请求继续使用你原来的分流策略。

> 当前阶段：`0.1.0-candidate`。所有规则均完成静态语法检查，但尚未完成本项目的真实 iPhone 验证，不能据此宣称开屏广告已经成功拦截。

## 安全边界

| 通道 | 默认使用 | HTTPS 解密 | 当前用途 |
| --- | --- | --- | --- |
| `stable` | 是 | 不需要 | 仅独立广告域名和低风险规则 |
| `experimental` | 否 | 需要 | 精确 URL 路径候选规则，逐 App 测试 |

- 稳定模块只允许 `DOMAIN,...,REJECT`，不包含 `DIRECT`、`PROXY`、`MITM`、脚本或 URL Rewrite。
- 实验模块绝不默认安装，不包含外部脚本，不读取或上传 Cookie、Token、请求头或响应正文。
- 淘宝、京东等共享 API 主机即使使用精确路径仍属于高风险，必须逐项回归登录、购物车、订单和支付入口。
- 请勿同时启用合集和对应的独立 App 模块。

## 当前覆盖状态

| App | Stable | Experimental | 真实设备 |
| --- | --- | --- | --- |
| 哔哩哔哩 | 独立商业广告主机 | v2 开屏配置路径 | 未验证 |
| 下厨房 | 暂无安全域名规则 | `/v*/ad/` | 未验证 |
| 淘宝 | 暂无安全域名规则 | 明确命名的广告服务路径；不宣称覆盖开屏 | 未验证 |
| 京东 | 暂无安全域名规则 | 开屏配置与广告交换路径 | 未验证 |
| 什么值得买 | 暂无安全域名规则 | `thirdAd.php` | 未验证 |

机器可读状态见 [`dist/status.json`](dist/status.json)。项目严格区分：

1. `syntax_status`：本项目的静态格式和正则校验通过。
2. `source_status`：有可追溯的公开来源支持。
3. `device_status`：在记录了 iOS、Shadowrocket 和 App 版本的真实设备上验证。

前两项不等于真实去广告成功。

## iPhone 安装

Shadowrocket 保持全局路由为“配置”。不要下载或替换完整 `.conf`。

### 安全候选版

1. 打开 Shadowrocket → 配置 → 模块。
2. 点击右上角 `+`，粘贴以下远程模块地址：

   ```text
   https://raw.githubusercontent.com/cgbzhangyu/NoAd/main/dist/canary/all.sgmodule
   ```

3. 下载并启用模块，重新连接 Shadowrocket。
4. 完全结束目标 App 后冷启动。

如需按 App 独立启停，将 `all.sgmodule` 替换为：

```text
bilibili.sgmodule
xiachufang.sgmodule
taobao.sgmodule
jd.sgmodule
smzdm.sgmodule
```

它们与合集位于同一 `dist/canary/` 目录。完成真机验收后，正式稳定地址改为 `https://raw.githubusercontent.com/cgbzhangyu/NoAd/stable/dist/stable/all.sgmodule`。

### 实验模块

实验模块位于 `dist/experimental/`，需要 Shadowrocket HTTPS 解密和系统信任 Shadowrocket 自签 CA。启用后 Shadowrocket 可以看到指定主机的 HTTPS 明文，这会扩大隐私和误杀风险。

必须满足以下条件后才可测试：

- 只安装一个目标 App 的实验模块；不要使用实验合集。
- 检查模块 `[MITM]` 列表，没有超出目标 App 所需主机。
- 不在测试时进行真实付款或输入新的高敏感信息。
- 准备好立即关闭模块，并按 [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) 回退。

默认使用者不需要安装证书。

## 本地开发

需要 Python 3.11 或以上，无第三方 Python 依赖：

```powershell
python scripts/noad.py validate
python scripts/noad.py build --check
python scripts/noad.py report
python -m unittest discover -s tests -v
```

修改 `catalog/apps/*.json` 后运行 `python scripts/noad.py build` 重新生成模块。不要直接编辑 `dist/`。

白名单通过 `catalog/allowlist.json` 中的规则 ID 在构建时排除。这里故意不生成 `DIRECT` 白名单，因为它会覆盖用户现有代理策略。

## 来源与许可证

- 实际派生规则仅使用 GPL-2.0-compatible 来源，当前主要为 [blackmatrix7/ios_rule_script](https://github.com/blackmatrix7/ios_rule_script)。
- [AWAvenue](https://github.com/TG-Twilight/AWAvenue-Ads-Rule) 与 [fmz200/wool_scripts](https://github.com/fmz200/wool_scripts) 为 GPL-3.0，只用于观察上游变化，不复制或合并。
- [Biliverse/ADBlock](https://github.com/Biliverse/ADBlock) 只用于了解 B站协议变化，不复制实现。
- 完整机器可读记录位于 `catalog/sources.json` 和每条规则的 `evidence` 字段。

NoAd 使用 GPL-2.0-only。第三方项目保留各自版权和许可证。

## 发布与回滚

- `main` 是候选通道，提交前必须通过 CI。
- `stable` 只接受人工批准的发布工作流；规则必须有真机记录才能晋级。
- 每个版本发布不可变的 GitHub Release、SHA-256 校验文件和变更日志。
- 误杀时先关闭对应 App 模块；维护者从历史 tag 重建旧产物并以新提交回滚 `stable`，不强推历史。

真机验证流程见 [`docs/DEVICE_TEST.md`](docs/DEVICE_TEST.md)。反馈规则失效或误杀时，严禁上传 Cookie、Token、完整查询参数、请求/响应正文或未经脱敏的 HAR。


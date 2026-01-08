# AstrBot CLIProxyAPI 统计插件

一个用于查询 [CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI) 使用统计和配额信息的 AstrBot 插件。

## 功能特性

- 查看 API 使用统计（请求数、Token 用量、成功率等）
- 查看今日详细使用情况（按模型统计）
- **实时查询 OAuth 账号配额**（剩余百分比、刷新时间）
- 支持多种凭证类型的配额查询：
  - 🚀 **Antigravity** - 反重力账号
  - 💎 **GeminiCLI** - Gemini CLI 账号

## 安装

1. 在 AstrBot 插件目录下克隆本仓库：
```bash
cd data/plugins
git clone https://github.com/muyouzhi6/astrbot_plugin_cliproxy_stats.git
```

2. 重启 AstrBot 或在管理面板中重载插件

## 配置

在插件配置中设置以下参数：

| 参数 | 说明 |
|------|------|
| `cpa_url` | CLIProxyAPI 服务地址，如 `https://your-cpa-server.com` |
| `cpa_password` | CLIProxyAPI 管理密钥 |

## 使用方法

### /cpa - 查看总览统计

显示总体使用统计和 OAuth 账号状态概览。

```
📊 CLIProxyAPI 统计总览

📈 总体统计
  总请求数: 1234
  成功: 1200 | 失败: 34
  成功率: 97.2%
  总 Token: 1.5M

🤖 各接口统计
  claude-sonnet-4-5
    请求: 500 | Token: 800K
  ...

🔑 OAuth 账号: 3/3 可用
  Antigravity: 3/3
```

### /cpa today 或 /cpa今日 - 查看今日统计

显示今日的详细使用情况。

```
📅 今日使用统计
日期: 2025-01-04

📊 今日总计
  请求数: 156
  Token: 250K

🤖 今日各模型详情
  claude-sonnet-4-5
    请求: 50 | Token: 100K
  gemini-3-pro
    请求: 30 | Token: 50K
  ...

⏰ 今日各时段请求
  凌晨(0-6): 10 | 上午(6-12): 45
  下午(12-18): 60 | 晚间(18-24): 41
```

### /cpa额度 - 查看配额状态

**实时**查询各 OAuth 账号的模型配额信息，支持 Antigravity 和 GeminiCLI 账号。

```
📊 OAuth 配额状态
🚀 Antigravity (2) | 💎 GeminiCLI (1)

━━━ 🚀 Antigravity ━━━

✅ example@gmail.com
   🟢 Claude/GPT: 86% | 刷新: 01/05 00:36
   🟢 Gemini 3 Pro: 99% | 刷新: 01/05 00:12
   🟢 Gemini 2.5 Flash: 100% | 刷新: 01/05 00:41
   🟢 Gemini 3 Flash: 99% | 刷新: 01/05 00:09

━━━ 💎 GeminiCLI ━━━

✅ another@gmail.com
   🟢 Claude/GPT: 92% | 刷新: 01/05 00:20
   🟢 Gemini 3 Pro: 100% | 刷新: 01/05 00:15
   🟡 Gemini 2.5 Flash: 65% | 刷新: 01/05 00:30

💡 配额每日自动刷新，百分比为剩余额度
```

#### 配额状态图标说明

| 图标 | 含义 |
|------|------|
| 🟢 | 充足 (≥80%) |
| 🟡 | 正常 (50-80%) |
| 🟠 | 偏低 (20-50%) |
| 🔴 | 紧张 (<20%) |

## 支持的凭证类型

当前支持以下凭证类型的配额查询：

| 类型 | 图标 | 说明 |
|------|------|------|
| Antigravity | 🚀 | 反重力账号（Google Cloud Code） |
| GeminiCLI | 💎 | Gemini CLI 账号（Google Cloud Code） |

## 支持的模型分组

以下模型分组可用于 Antigravity 和 GeminiCLI 账号：

- **Claude/GPT**: claude-sonnet-4-5-thinking, claude-opus-4-5-thinking, claude-sonnet-4-5, gpt-oss-120b-medium
- **Gemini 3 Pro**: gemini-3-pro-high, gemini-3-pro-low
- **Gemini 2.5 Flash**: gemini-2.5-flash, gemini-2.5-flash-thinking
- **Gemini 2.5 Flash Lite**: gemini-2.5-flash-lite
- **Gemini 2.5 CU**: rev19-uic3-1p
- **Gemini 3 Flash**: gemini-3-flash
- **Gemini 3 Pro Image**: gemini-3-pro-image

## 依赖

- AstrBot >= 3.0
- aiohttp

## 许可证

MIT License

## 作者

木有知

## 相关链接

- [CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI) - CLI Proxy API 服务端
- [AstrBot](https://github.com/Soulter/AstrBot) - 多平台 LLM 聊天机器人框架

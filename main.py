"""
CLIProxyAPI 额度与使用统计查询插件
支持查看 OAuth 模型额度和当日调用统计
"""

import aiohttp
import json
from datetime import datetime, date
from typing import Optional, Dict, Any, List

from astrbot.api.star import Star, Context
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api import logger, AstrBotConfig


# Antigravity 配额 API 配置
ANTIGRAVITY_QUOTA_URLS = [
    "https://daily-cloudcode-pa.googleapis.com/v1internal:fetchAvailableModels",
    "https://daily-cloudcode-pa.sandbox.googleapis.com/v1internal:fetchAvailableModels",
    "https://cloudcode-pa.googleapis.com/v1internal:fetchAvailableModels"
]

ANTIGRAVITY_REQUEST_HEADERS = {
    "Authorization": "Bearer $TOKEN$",
    "Content-Type": "application/json",
    "User-Agent": "antigravity/1.11.5 windows/amd64"
}

# 模型分组配置
ANTIGRAVITY_QUOTA_GROUPS = [
    {"id": "claude-gpt", "label": "Claude/GPT", "identifiers": ["claude-sonnet-4-5-thinking", "claude-opus-4-5-thinking", "claude-sonnet-4-5", "gpt-oss-120b-medium"]},
    {"id": "gemini-3-pro", "label": "Gemini 3 Pro", "identifiers": ["gemini-3-pro-high", "gemini-3-pro-low"]},
    {"id": "gemini-2-5-flash", "label": "Gemini 2.5 Flash", "identifiers": ["gemini-2.5-flash", "gemini-2.5-flash-thinking"]},
    {"id": "gemini-2-5-flash-lite", "label": "Gemini 2.5 Flash Lite", "identifiers": ["gemini-2.5-flash-lite"]},
    {"id": "gemini-2-5-cu", "label": "Gemini 2.5 CU", "identifiers": ["rev19-uic3-1p"]},
    {"id": "gemini-3-flash", "label": "Gemini 3 Flash", "identifiers": ["gemini-3-flash"]},
    {"id": "gemini-image", "label": "Gemini 3 Pro Image", "identifiers": ["gemini-3-pro-image"]}
]


class CPAClient:
    """CLIProxyAPI 客户端"""

    def __init__(self, base_url: str, password: str):
        self.base_url = base_url.rstrip('/')
        self.password = password

    def _get_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.password}",
            "Content-Type": "application/json"
        }

    async def get_usage(self) -> Optional[Dict[str, Any]]:
        """获取使用统计"""
        url = f"{self.base_url}/v0/management/usage"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self._get_headers(), timeout=30, ssl=False) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        text = await resp.text()
                        logger.error(f"获取 usage 失败: {resp.status} - {text}")
                        return None
        except Exception as e:
            logger.error(f"请求 usage 接口出错: {e}")
            return None

    async def get_auth_files(self) -> Optional[Dict[str, Any]]:
        """获取认证文件列表"""
        url = f"{self.base_url}/v0/management/auth-files"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self._get_headers(), timeout=30, ssl=False) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        text = await resp.text()
                        logger.error(f"获取 auth-files 失败: {resp.status} - {text}")
                        return None
        except Exception as e:
            logger.error(f"请求 auth-files 接口出错: {e}")
            return None

    async def api_call(self, auth_index: str, method: str, url: str,
                       header: Dict[str, str], data: str = "") -> Optional[Dict[str, Any]]:
        """通用 API 调用代理"""
        api_url = f"{self.base_url}/v0/management/api-call"
        payload = {
            "auth_index": auth_index,
            "method": method,
            "url": url,
            "header": header,
            "data": data
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(api_url, headers=self._get_headers(),
                                        json=payload, timeout=60, ssl=False) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        # 解析 body
                        if "body" in result and isinstance(result["body"], str):
                            try:
                                result["body"] = json.loads(result["body"])
                            except json.JSONDecodeError:
                                pass
                        return result
                    else:
                        text = await resp.text()
                        logger.error(f"api-call 失败: {resp.status} - {text}")
                        return None
        except Exception as e:
            logger.error(f"api-call 请求出错: {e}")
            return None

    async def get_antigravity_quota(self, auth_index: str) -> Optional[Dict[str, Any]]:
        """获取 Antigravity 账号的配额信息"""
        for quota_url in ANTIGRAVITY_QUOTA_URLS:
            result = await self.api_call(
                auth_index=auth_index,
                method="POST",
                url=quota_url,
                header=ANTIGRAVITY_REQUEST_HEADERS,
                data="{}"
            )
            if result and result.get("status_code") == 200:
                body = result.get("body", {})
                if isinstance(body, dict) and "models" in body:
                    return body
        return None


class Main(Star):
    """CLIProxyAPI 额度统计插件"""

    def __init__(self, context: Context, config: AstrBotConfig) -> None:
        super().__init__(context)
        self.config = config
        self.cpa_url = self.config.get("cpa_url", "")
        self.cpa_password = self.config.get("cpa_password", "")

    def _get_client(self) -> Optional[CPAClient]:
        """获取 CPA 客户端"""
        if not self.cpa_url or not self.cpa_password:
            return None
        return CPAClient(self.cpa_url, self.cpa_password)

    def _format_tokens(self, tokens: int) -> str:
        """格式化 token 数量"""
        if tokens >= 1_000_000:
            return f"{tokens / 1_000_000:.2f}M"
        elif tokens >= 1_000:
            return f"{tokens / 1_000:.2f}K"
        return str(tokens)

    def _get_provider_display(self, provider: str) -> str:
        """获取供应商显示名称"""
        mapping = {
            "gemini": "Gemini",
            "claude": "Claude",
            "codex": "OpenAI/Codex",
            "antigravity": "Antigravity",
            "iflow": "iFlow",
            "qwen": "Qwen"
        }
        return mapping.get(provider.lower(), provider)

    def _parse_antigravity_quota(self, models: Dict[str, Any]) -> List[Dict[str, Any]]:
        """解析 Antigravity 配额信息，返回按分组聚合的配额列表"""
        groups = []

        for group_def in ANTIGRAVITY_QUOTA_GROUPS:
            group_id = group_def["id"]
            label = group_def["label"]
            identifiers = group_def["identifiers"]

            matched_entries = []
            for identifier in identifiers:
                if identifier in models:
                    entry = models[identifier]
                    quota_info = entry.get("quotaInfo", entry.get("quota_info", {}))
                    remaining = quota_info.get("remainingFraction", quota_info.get("remaining_fraction"))
                    reset_time = quota_info.get("resetTime", quota_info.get("reset_time"))

                    if remaining is not None:
                        matched_entries.append({
                            "model": identifier,
                            "remaining": remaining,
                            "reset_time": reset_time
                        })

            if matched_entries:
                # 取最小的 remaining 作为组的配额
                min_remaining = min(e["remaining"] for e in matched_entries)
                # 取最早的 reset_time
                reset_times = [e["reset_time"] for e in matched_entries if e["reset_time"]]
                earliest_reset = None
                if reset_times:
                    try:
                        earliest_reset = min(reset_times)
                    except Exception:
                        earliest_reset = reset_times[0] if reset_times else None

                groups.append({
                    "id": group_id,
                    "label": label,
                    "remaining_percent": round(min_remaining * 100),
                    "reset_time": earliest_reset,
                    "models": [e["model"] for e in matched_entries]
                })

        return groups

    def _format_reset_time(self, reset_time: Optional[str]) -> str:
        """格式化配额刷新时间（UTC 转本地时间）"""
        if not reset_time:
            return "-"
        try:
            # 解析 UTC 时间
            dt = datetime.fromisoformat(reset_time.replace("Z", "+00:00"))
            # 转换为本地时间
            local_dt = dt.astimezone()
            return local_dt.strftime("%m/%d %H:%M")
        except Exception:
            return reset_time[:16] if len(reset_time) > 16 else reset_time

    @filter.command("cpa")
    async def cpa_stats(self, event: AstrMessageEvent):
        """
        查看 CLIProxyAPI 使用统计
        用法: /cpa [today|总览]
        - /cpa 或 /cpa 总览: 查看总体统计和账号状态
        - /cpa today: 查看今日详细统计
        """
        client = self._get_client()
        if not client:
            yield event.plain_result("❌ 未配置 CLIProxyAPI 地址或密码，请在插件配置中设置")
            return

        args = event.message_str.strip().split()[1:] if len(event.message_str.strip().split()) > 1 else []
        subcommand = args[0].lower() if args else "overview"

        if subcommand in ["today", "今日", "今天"]:
            yield event.plain_result(await self._get_today_stats(client))
        else:
            yield event.plain_result(await self._get_overview(client))

    @filter.command("cpa额度")
    async def cpa_quota(self, event: AstrMessageEvent):
        """查看 CLIProxyAPI OAuth 账号配额（实时获取）"""
        client = self._get_client()
        if not client:
            yield event.plain_result("❌ 未配置 CLIProxyAPI 地址或密码，请在插件配置中设置")
            return

        yield event.plain_result(await self._get_quota_status(client))

    @filter.command("cpa今日")
    async def cpa_today(self, event: AstrMessageEvent):
        """查看今日使用统计"""
        client = self._get_client()
        if not client:
            yield event.plain_result("❌ 未配置 CLIProxyAPI 地址或密码，请在插件配置中设置")
            return

        yield event.plain_result(await self._get_today_stats(client))

    async def _get_overview(self, client: CPAClient) -> str:
        """获取总览信息"""
        usage_data = await client.get_usage()
        auth_data = await client.get_auth_files()

        if not usage_data:
            return "❌ 获取使用统计失败，请检查配置"

        usage = usage_data.get("usage", {})

        lines = ["📊 CLIProxyAPI 统计总览", ""]

        # 总体统计
        total_requests = usage.get("total_requests", 0)
        success_count = usage.get("success_count", 0)
        failure_count = usage.get("failure_count", 0)
        total_tokens = usage.get("total_tokens", 0)

        success_rate = (success_count / total_requests * 100) if total_requests > 0 else 0

        lines.append("📈 总体统计")
        lines.append(f"  总请求数: {total_requests}")
        lines.append(f"  成功: {success_count} | 失败: {failure_count}")
        lines.append(f"  成功率: {success_rate:.1f}%")
        lines.append(f"  总 Token: {self._format_tokens(total_tokens)}")
        lines.append("")

        # 各模型统计
        apis = usage.get("apis", {})
        if apis:
            lines.append("🤖 各接口统计")
            # 按请求数排序
            sorted_apis = sorted(apis.items(), key=lambda x: x[1].get("total_requests", 0), reverse=True)
            for api_name, api_data in sorted_apis[:10]:  # 只显示前10个
                req_count = api_data.get("total_requests", 0)
                token_count = api_data.get("total_tokens", 0)
                lines.append(f"  {api_name}")
                lines.append(f"    请求: {req_count} | Token: {self._format_tokens(token_count)}")
            lines.append("")

        # OAuth 账号状态
        if auth_data and auth_data.get("files"):
            auth_files = auth_data.get("files", [])
            active_count = sum(1 for f in auth_files if not f.get("disabled", False) and not f.get("unavailable", False))
            total_auth = len(auth_files)

            lines.append(f"🔑 OAuth 账号: {active_count}/{total_auth} 可用")

            # 按类型分组统计
            type_counts: Dict[str, Dict[str, int]] = {}
            for auth in auth_files:
                provider = auth.get("provider", auth.get("type", "unknown"))
                if provider not in type_counts:
                    type_counts[provider] = {"total": 0, "active": 0}
                type_counts[provider]["total"] += 1
                if not auth.get("disabled", False) and not auth.get("unavailable", False):
                    type_counts[provider]["active"] += 1

            for provider, counts in type_counts.items():
                display_name = self._get_provider_display(provider)
                lines.append(f"  {display_name}: {counts['active']}/{counts['total']}")

        return "\n".join(lines)

    async def _get_today_stats(self, client: CPAClient) -> str:
        """获取今日统计"""
        usage_data = await client.get_usage()

        if not usage_data:
            return "❌ 获取使用统计失败，请检查配置"

        usage = usage_data.get("usage", {})
        today = date.today().isoformat()

        lines = ["📅 今日使用统计", f"日期: {today}", ""]

        # 今日请求数
        requests_by_day = usage.get("requests_by_day", {})
        tokens_by_day = usage.get("tokens_by_day", {})

        today_requests = requests_by_day.get(today, 0)
        today_tokens = tokens_by_day.get(today, 0)

        lines.append(f"📊 今日总计")
        lines.append(f"  请求数: {today_requests}")
        lines.append(f"  Token: {self._format_tokens(today_tokens)}")
        lines.append("")

        # 各模型今日统计
        apis = usage.get("apis", {})
        if apis:
            lines.append("🤖 今日各模型详情")

            model_today_stats: List[tuple] = []

            for api_name, api_data in apis.items():
                models = api_data.get("models", {})
                for model_name, model_data in models.items():
                    details = model_data.get("details", [])
                    # 筛选今日的请求
                    today_details = [d for d in details if d.get("timestamp", "").startswith(today)]
                    if today_details:
                        today_req = len(today_details)
                        today_tok = sum(d.get("tokens", {}).get("total_tokens", 0) for d in today_details)
                        today_failed = sum(1 for d in today_details if d.get("failed", False))
                        model_today_stats.append((model_name, today_req, today_tok, today_failed))

            # 按请求数排序
            model_today_stats.sort(key=lambda x: x[1], reverse=True)

            if model_today_stats:
                for model_name, req_count, tok_count, fail_count in model_today_stats[:15]:
                    fail_info = f" (失败{fail_count})" if fail_count > 0 else ""
                    lines.append(f"  {model_name}")
                    lines.append(f"    请求: {req_count}{fail_info} | Token: {self._format_tokens(tok_count)}")
            else:
                lines.append("  今日暂无使用记录")

        # 按小时分布（从 details 中按今天的 timestamp 统计）
        today_by_hour: Dict[int, int] = {h: 0 for h in range(24)}
        for api_name, api_data in apis.items():
            models = api_data.get("models", {})
            for model_name, model_data in models.items():
                details = model_data.get("details", [])
                for d in details:
                    timestamp = d.get("timestamp", "")
                    if timestamp.startswith(today):
                        try:
                            # 解析小时，timestamp 格式类似 "2026-01-04T14:30:00Z"
                            hour = int(timestamp[11:13])
                            today_by_hour[hour] += 1
                        except (ValueError, IndexError):
                            pass

        total_hourly = sum(today_by_hour.values())
        if total_hourly > 0:
            lines.append("")
            lines.append("⏰ 今日各时段请求")
            # 简化显示：分几个时段
            night = sum(today_by_hour[h] for h in range(0, 6))
            morning = sum(today_by_hour[h] for h in range(6, 12))
            afternoon = sum(today_by_hour[h] for h in range(12, 18))
            evening = sum(today_by_hour[h] for h in range(18, 24))

            lines.append(f"  凌晨(0-6): {night} | 上午(6-12): {morning}")
            lines.append(f"  下午(12-18): {afternoon} | 晚间(18-24): {evening}")

        return "\n".join(lines)

    async def _get_auth_status(self, client: CPAClient) -> str:
        """获取 OAuth 账号状态"""
        auth_data = await client.get_auth_files()

        if not auth_data:
            return "❌ 获取账号状态失败，请检查配置"

        auth_files = auth_data.get("files", [])

        if not auth_files:
            return "📭 暂无 OAuth 账号"

        lines = ["🔑 OAuth 账号状态", ""]

        # 按类型分组
        groups: Dict[str, List[Dict]] = {}
        for auth in auth_files:
            provider = auth.get("provider", auth.get("type", "unknown"))
            if provider not in groups:
                groups[provider] = []
            groups[provider].append(auth)

        for provider, auths in groups.items():
            display_name = self._get_provider_display(provider)
            active = [a for a in auths if not a.get("disabled", False) and not a.get("unavailable", False)]

            lines.append(f"【{display_name}】 {len(active)}/{len(auths)} 可用")

            for auth in auths:
                name = auth.get("name", auth.get("id", "未知"))
                email = auth.get("email", "")
                status = auth.get("status", "")
                disabled = auth.get("disabled", False)
                unavailable = auth.get("unavailable", False)

                # 状态图标
                if disabled or unavailable:
                    icon = "❌"
                elif status == "active":
                    icon = "✅"
                elif status == "disabled":
                    icon = "🚫"
                elif status == "cooling":
                    icon = "❄️"
                else:
                    icon = "⚪"

                display = email if email else name
                # 截断过长的名称
                if len(display) > 30:
                    display = display[:27] + "..."

                status_msg = auth.get("status_message", "")
                if status_msg and len(status_msg) > 40:
                    status_msg = status_msg[:37] + "..."

                line = f"  {icon} {display}"
                if status_msg:
                    line += f" ({status_msg})"
                lines.append(line)

                # 显示账号类型信息（如果有）
                account_type = auth.get("account_type", "")
                account = auth.get("account", "")
                if account_type or account:
                    extra = []
                    if account_type:
                        extra.append(account_type)
                    if account:
                        extra.append(account)
                    lines.append(f"      类型: {' | '.join(extra)}")

                # 显示 ID Token 信息（Codex）
                id_token = auth.get("id_token", {})
                if id_token:
                    plan_type = id_token.get("plan_type", "")
                    if plan_type:
                        lines.append(f"      套餐: {plan_type}")

            lines.append("")

        return "\n".join(lines).rstrip()

    async def _get_quota_status(self, client: CPAClient) -> str:
        """获取 OAuth 账号配额状态（实时从 API 获取）"""
        auth_data = await client.get_auth_files()

        if not auth_data:
            return "❌ 获取账号状态失败，请检查配置"

        auth_files = auth_data.get("files", [])

        if not auth_files:
            return "📭 暂无 OAuth 账号"

        # 筛选 Antigravity 账号
        antigravity_auths = [
            auth for auth in auth_files
            if auth.get("provider", auth.get("type", "")).lower() == "antigravity"
        ]

        if not antigravity_auths:
            return "📭 暂无 Antigravity 账号（当前仅支持 Antigravity 配额查询）"

        lines = ["📊 OAuth 账号配额状态", ""]

        for auth in antigravity_auths:
            auth_index = auth.get("auth_index", "")
            email = auth.get("email", "")
            name = auth.get("name", auth.get("id", "未知"))
            disabled = auth.get("disabled", False)
            unavailable = auth.get("unavailable", False)

            # 状态图标
            if disabled or unavailable:
                icon = "❌"
            else:
                icon = "✅"

            display = email if email else name
            if len(display) > 30:
                display = display[:27] + "..."

            lines.append(f"{icon} {display}")

            if not auth_index:
                lines.append("   ⚠️ 无法获取配额（缺少 auth_index）")
                lines.append("")
                continue

            if disabled or unavailable:
                lines.append("   ⚠️ 账号已禁用或不可用")
                lines.append("")
                continue

            # 获取配额信息
            quota_data = await client.get_antigravity_quota(auth_index)

            if not quota_data:
                lines.append("   ⚠️ 获取配额失败")
                lines.append("")
                continue

            models = quota_data.get("models", {})
            if not models:
                lines.append("   ⚠️ 无可用模型")
                lines.append("")
                continue

            # 解析配额分组
            quota_groups = self._parse_antigravity_quota(models)

            if not quota_groups:
                lines.append("   ⚠️ 无配额信息")
                lines.append("")
                continue

            for group in quota_groups:
                percent = group["remaining_percent"]
                reset_time = self._format_reset_time(group.get("reset_time"))
                label = group["label"]

                # 配额百分比颜色提示
                if percent >= 80:
                    status_icon = "🟢"
                elif percent >= 50:
                    status_icon = "🟡"
                elif percent >= 20:
                    status_icon = "🟠"
                else:
                    status_icon = "🔴"

                lines.append(f"   {status_icon} {label}: {percent}% | 刷新: {reset_time}")

            lines.append("")

        lines.append("💡 配额每日自动刷新，百分比为剩余额度")

        return "\n".join(lines).rstrip()

    async def _get_auth_status_with_usage(self, client: CPAClient) -> str:
        """获取 OAuth 账号状态，并包含各凭证的使用量统计"""
        auth_data = await client.get_auth_files()
        usage_data = await client.get_usage()

        if not auth_data:
            return "❌ 获取账号状态失败，请检查配置"

        auth_files = auth_data.get("files", [])

        if not auth_files:
            return "📭 暂无 OAuth 账号"

        # 构建凭证 ID 到使用量的映射
        auth_usage: Dict[str, Dict[str, Any]] = {}
        if usage_data:
            usage = usage_data.get("usage", {})
            apis = usage.get("apis", {})
            today = date.today().isoformat()

            for api_name, api_data in apis.items():
                models = api_data.get("models", {})
                for model_name, model_data in models.items():
                    details = model_data.get("details", [])
                    for detail in details:
                        auth_index = detail.get("auth_index", "")
                        if auth_index:
                            if auth_index not in auth_usage:
                                auth_usage[auth_index] = {
                                    "total_requests": 0,
                                    "total_tokens": 0,
                                    "today_requests": 0,
                                    "today_tokens": 0,
                                    "failed": 0
                                }
                            auth_usage[auth_index]["total_requests"] += 1
                            tokens = detail.get("tokens", {}).get("total_tokens", 0)
                            auth_usage[auth_index]["total_tokens"] += tokens

                            if detail.get("failed", False):
                                auth_usage[auth_index]["failed"] += 1

                            timestamp = detail.get("timestamp", "")
                            if timestamp.startswith(today):
                                auth_usage[auth_index]["today_requests"] += 1
                                auth_usage[auth_index]["today_tokens"] += tokens

        lines = ["🔑 OAuth 账号状态与使用量", ""]

        # 按类型分组
        groups: Dict[str, List[Dict]] = {}
        for auth in auth_files:
            provider = auth.get("provider", auth.get("type", "unknown"))
            if provider not in groups:
                groups[provider] = []
            groups[provider].append(auth)

        for provider, auths in groups.items():
            display_name = self._get_provider_display(provider)
            active = [a for a in auths if not a.get("disabled", False) and not a.get("unavailable", False)]

            lines.append(f"【{display_name}】 {len(active)}/{len(auths)} 可用")

            for auth in auths:
                auth_index = auth.get("auth_index", "")
                email = auth.get("email", "")
                name = auth.get("name", auth.get("id", "未知"))
                status = auth.get("status", "")
                disabled = auth.get("disabled", False)
                unavailable = auth.get("unavailable", False)

                # 状态图标
                if disabled or unavailable:
                    icon = "❌"
                elif status == "active":
                    icon = "✅"
                elif status == "disabled":
                    icon = "🚫"
                elif status == "cooling":
                    icon = "❄️"
                else:
                    icon = "⚪"

                display = email if email else name
                # 截断过长的名称
                if len(display) > 25:
                    display = display[:22] + "..."

                status_msg = auth.get("status_message", "")

                line = f"  {icon} {display}"
                if status_msg:
                    if len(status_msg) > 30:
                        status_msg = status_msg[:27] + "..."
                    line += f" ({status_msg})"
                lines.append(line)

                # 显示使用量（如果有）
                if auth_index and auth_index in auth_usage:
                    u = auth_usage[auth_index]
                    today_info = ""
                    if u["today_requests"] > 0:
                        today_info = f" | 今日: {u['today_requests']}次/{self._format_tokens(u['today_tokens'])}"
                    fail_info = f" | 失败: {u['failed']}" if u["failed"] > 0 else ""
                    lines.append(f"      用量: {u['total_requests']}次/{self._format_tokens(u['total_tokens'])}{today_info}{fail_info}")

                # 显示账号类型信息
                account_type = auth.get("account_type", "")
                id_token = auth.get("id_token", {})
                if id_token:
                    plan_type = id_token.get("plan_type", "")
                    if plan_type:
                        lines.append(f"      套餐: {plan_type}")

                # 显示最后刷新时间
                last_refresh = auth.get("last_refresh", "")
                if last_refresh:
                    try:
                        # 解析 ISO 格式时间
                        if "T" in last_refresh:
                            dt = datetime.fromisoformat(last_refresh.replace("Z", "+00:00"))
                            lines.append(f"      刷新: {dt.strftime('%m-%d %H:%M')}")
                    except Exception:
                        pass

            lines.append("")

        # 添加说明
        lines.append("💡 说明: CPA 使用被动式额度管理，状态在请求触发限流后更新")

        return "\n".join(lines).rstrip()

    async def terminate(self):
        """插件终止"""
        logger.info("CLIProxyAPI 统计插件已终止")

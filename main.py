"""
CLIProxyAPI 额度与使用统计查询插件
支持查看 OAuth 模型额度和当日调用统计
输出渲染为现代卡片风格图片
支持 LLM 智能分析使用情况
"""

import aiohttp
from aiohttp import ClientTimeout
import asyncio
import json
import os
import re
from datetime import datetime, date
from typing import Optional, Dict, Any, List, Tuple

from astrbot.api.star import Star, Context
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api import logger, AstrBotConfig
from astrbot.api.message_components import Plain, Image
from astrbot.core.provider.provider import Provider

# 导入自定义统计卡片渲染器
from .stats_renderer import StatsCardRenderer

# 导入图片保存工具
from astrbot.core.utils.io import save_temp_img


# Antigravity 配额 API (使用 fetchAvailableModels)
ANTIGRAVITY_QUOTA_URLS = [
    "https://daily-cloudcode-pa.googleapis.com/v1internal:fetchAvailableModels",
    "https://daily-cloudcode-pa.sandbox.googleapis.com/v1internal:fetchAvailableModels",
    "https://cloudcode-pa.googleapis.com/v1internal:fetchAvailableModels"
]

# GeminiCLI 配额 API (使用 retrieveUserQuota，需要传递 project 参数)
GEMINI_CLI_QUOTA_URL = "https://cloudcode-pa.googleapis.com/v1internal:retrieveUserQuota"

# GeminiCLI 简化请求头 (WebUI 只使用 Authorization 和 Content-Type)
GEMINI_CLI_QUOTA_HEADERS = {
    "Authorization": "Bearer $TOKEN$",
    "Content-Type": "application/json"
}


def extract_project_from_filename(filename: str) -> Optional[str]:
    """从 GeminiCLI 凭证文件名中提取 project 名称

    文件名格式: gemini-{email}-{project}.json
    例如: gemini-user@gmail.com-focused-brace-480503-c1.json -> focused-brace-480503-c1
    """
    import re
    if not filename:
        return None

    # 移除 .json 后缀
    name = filename.rstrip('.json') if filename.endswith('.json') else filename

    # 匹配 gemini-{email}-{project} 格式
    # email 包含 @ 符号，project 是最后一个 @ 后面的部分去掉 email 域名
    match = re.match(r'^gemini-[^@]+@[^-]+-(.+)$', name)
    if match:
        return match.group(1)

    # 备用方案：找最后一个 @ 后面的部分，然后取第一个 - 之后的所有内容
    if '@' in name and '-' in name:
        at_pos = name.rfind('@')
        after_at = name[at_pos+1:]
        dash_pos = after_at.find('-')
        if dash_pos != -1:
            return after_at[dash_pos+1:]

    return None

# Antigravity 请求头
ANTIGRAVITY_REQUEST_HEADERS = {
    "Authorization": "Bearer $TOKEN$",
    "Content-Type": "application/json",
    "User-Agent": "antigravity/1.11.5 windows/amd64"
}

# GeminiCLI 请求头
GEMINI_CLI_REQUEST_HEADERS = {
    "Authorization": "Bearer $TOKEN$",
    "Content-Type": "application/json",
    "User-Agent": "google-api-nodejs-client/9.15.1",
    "X-Goog-Api-Client": "gl-node/22.17.0",
    "Client-Metadata": "ideType=IDE_UNSPECIFIED,platform=PLATFORM_UNSPECIFIED,pluginType=GEMINI"
}

# Codex (OpenAI) 配额查询 API
CODEX_QUOTA_URL = "https://chatgpt.com/backend-api/wham/usage"
CODEX_QUOTA_HEADERS = {
    "Authorization": "Bearer $TOKEN$",
    "Content-Type": "application/json"
}

# 支持配额查询的凭证类型 (gemini-cli 是 CPA 内部转换后的名称)
QUOTA_SUPPORTED_PROVIDERS = ["antigravity", "gemini", "gemini-cli", "codex"]

# 模型分组配置 (Antigravity 格式)
QUOTA_GROUPS = [
    {"id": "claude-gpt", "label": "Claude/GPT", "identifiers": ["claude-sonnet-4-5-thinking", "claude-opus-4-5-thinking", "claude-sonnet-4-5", "gpt-oss-120b-medium"]},
    {"id": "gemini-3-pro", "label": "Gemini 3 Pro", "identifiers": ["gemini-3-pro-high", "gemini-3-pro-low"]},
    {"id": "gemini-2-5-flash", "label": "Gemini 2.5 Flash", "identifiers": ["gemini-2.5-flash", "gemini-2.5-flash-thinking"]},
    {"id": "gemini-2-5-flash-lite", "label": "Gemini 2.5 Flash Lite", "identifiers": ["gemini-2.5-flash-lite"]},
    {"id": "gemini-2-5-cu", "label": "Gemini 2.5 CU", "identifiers": ["rev19-uic3-1p"]},
    {"id": "gemini-3-flash", "label": "Gemini 3 Flash", "identifiers": ["gemini-3-flash"]},
    {"id": "gemini-image", "label": "Gemini 3 Pro Image", "identifiers": ["gemini-3-pro-image"]}
]

# GeminiCLI 模型分组配置 (buckets 格式, 使用 retrieveUserQuota API)
GEMINI_CLI_QUOTA_GROUPS = [
    {"id": "gemini-2-5-flash-series", "label": "Gemini 2.5 Flash Series", "identifiers": ["gemini-2.5-flash", "gemini-2.5-flash-lite"]},
    {"id": "gemini-2-5-pro", "label": "Gemini 2.5 Pro", "identifiers": ["gemini-2.5-pro"]},
    {"id": "gemini-3-flash-preview", "label": "Gemini 3 Flash Preview", "identifiers": ["gemini-3-flash-preview"]},
    {"id": "gemini-3-pro-preview", "label": "Gemini 3 Pro Preview", "identifiers": ["gemini-3-pro-preview"]},
    {"id": "gemini-2-0-flash", "label": "Gemini 2.0 Flash", "identifiers": ["gemini-2.0-flash"]},
]

# 凭证类型显示名称和图标
PROVIDER_INFO = {
    "antigravity": {"name": "Antigravity", "icon": "🚀", "color": "#8b5cf6", "supports_quota": True},
    "gemini": {"name": "GeminiCLI", "icon": "💎", "color": "#3b82f6", "supports_quota": True},
    "gemini-cli": {"name": "GeminiCLI", "icon": "💎", "color": "#3b82f6", "supports_quota": True},
    "claude": {"name": "Claude", "icon": "🤖", "color": "#f59e0b", "supports_quota": False},
    "codex": {"name": "Codex", "icon": "🔮", "color": "#10b981", "supports_quota": True},
    "iflow": {"name": "iFlow", "icon": "🌊", "color": "#06b6d4", "supports_quota": False},
    "qwen": {"name": "Qwen", "icon": "🌙", "color": "#ec4899", "supports_quota": False}
}

# LLM 分析 prompt 模板
LLM_ANALYSIS_PROMPT = """你是一个 API 使用分析专家。请根据以下 CLIProxyAPI 使用数据，提供精准的分析报告。

## 当前时间
{current_time}

## 今日使用数据
- 日期: {date}
- 总请求数: {total_requests}
- 总 Token: {total_tokens}
- 成功率: {success_rate}%
- 已运行时长: 从 00:00 到现在约 {hours_elapsed} 小时

## 各模型使用详情
{model_stats}

## 配额状态（含刷新时间）
{quota_stats}

## 小时级使用分布
{hourly_distribution}

请提供以下分析：

### 1. 配额安全评估（最重要）
对于每个配额紧张的模型（剩余 < 80%）：
- 计算：当前消耗速率 = 已用配额 / 已运行小时数
- 计算：预计耗尽时间 = 剩余配额 / 消耗速率
- **关键判断**：在该模型的刷新时间之前，配额是否会耗尽？
  - 如果刷新时间在耗尽之前 → ✅ 安全，无需担心
  - 如果耗尽在刷新之前 → ⚠️ 预警，给出预计耗尽时间
- 配额充足（> 80%）的模型不需要预警

### 2. 模型使用分析
- 哪个模型是主力？占比多少？
- 各模型的平均单次 Token 消耗
- 是否有异常高消耗的模型？

### 3. 优化建议（仅在必要时给出）
- **只有当配额确实会在刷新前耗尽时**，才建议切换模型
- 如果配额安全，明确说"当前使用模式可持续，无需调整"
- 不要为了建议而建议

请用中文回答，数据要准确，结论要明确。"""


class CPAClient:
    """CLIProxyAPI 客户端"""

    def __init__(self, base_url: str, password: str, verify_ssl: bool = False):
        self.base_url = base_url.rstrip('/')
        self.password = password
        self.verify_ssl = verify_ssl
        self._session: Optional[aiohttp.ClientSession] = None

    def _get_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.password}",
            "Content-Type": "application/json"
        }

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建复用的 Session"""
        if self._session is None or self._session.closed:
            # 根据配置决定是否验证 SSL
            if self.verify_ssl:
                connector = aiohttp.TCPConnector()
            else:
                connector = aiohttp.TCPConnector(ssl=False)
            self._session = aiohttp.ClientSession(connector=connector)
        return self._session

    async def close(self):
        """关闭 Session 及其 Connector"""
        if self._session and not self._session.closed:
            await self._session.close()
            # 等待 connector 完全关闭，避免资源泄漏
            await asyncio.sleep(0.25)
        self._session = None

    async def get_usage(self) -> Optional[Dict[str, Any]]:
        """获取使用统计"""
        url = f"{self.base_url}/v0/management/usage"
        try:
            session = await self._get_session()
            async with session.get(url, headers=self._get_headers(), timeout=ClientTimeout(total=30)) as resp:
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
            session = await self._get_session()
            async with session.get(url, headers=self._get_headers(), timeout=ClientTimeout(total=30)) as resp:
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
            session = await self._get_session()
            async with session.post(api_url, headers=self._get_headers(),
                                    json=payload, timeout=ClientTimeout(total=60)) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    # 解析 body（先检查类型）
                    if "body" in result and isinstance(result["body"], str):
                        try:
                            result["body"] = json.loads(result["body"])
                        except (json.JSONDecodeError, TypeError):
                            pass
                    return result
                else:
                    text = await resp.text()
                    logger.error(f"api-call 失败: {resp.status} - {text}")
                    return None
        except Exception as e:
            logger.error(f"api-call 请求出错: {e}")
            return None

    async def get_antigravity_quota(self, auth_index: str) -> Dict[str, Any]:
        """获取 Antigravity 账号的配额信息"""
        return await self.get_google_quota(auth_index, "antigravity")

    async def get_gemini_cli_quota(self, auth_index: str, project: str) -> Dict[str, Any]:
        """获取 GeminiCLI 账号的配额信息

        Args:
            auth_index: 凭证索引
            project: 项目名称（从文件名中提取）

        Returns:
            Dict with keys:
                - "success": bool - 是否成功
                - "buckets": List - 配额桶列表（仅在成功时存在）
                - "error": str - 错误信息（仅在失败时存在）
                - "error_code": int - HTTP 错误码（仅在失败时存在）
        """
        if not project:
            return {
                "success": False,
                "error": "无法提取项目名称",
                "error_code": 0
            }

        result = await self.api_call(
            auth_index=auth_index,
            method="POST",
            url=GEMINI_CLI_QUOTA_URL,
            header=GEMINI_CLI_QUOTA_HEADERS,
            data=json.dumps({"project": project})
        )

        if result:
            status_code = result.get("status_code", 0)
            if status_code == 200:
                body = result.get("body", {})
                # body 可能是字符串，需要解析
                if isinstance(body, str):
                    try:
                        body = json.loads(body)
                    except json.JSONDecodeError:
                        body = {}
                # GeminiCLI API 返回 buckets 数组
                if isinstance(body, dict) and "buckets" in body:
                    return {"success": True, "buckets": body.get("buckets", [])}
                return {"success": True, "buckets": []}
            elif status_code == 403:
                return {
                    "success": False,
                    "error": "权限不足",
                    "error_code": 403
                }
            else:
                body = result.get("body", {})
                if isinstance(body, str):
                    try:
                        body = json.loads(body)
                    except json.JSONDecodeError:
                        body = {}
                error_msg = f"HTTP {status_code}"
                if isinstance(body, dict) and "error" in body:
                    error_msg = body.get("error", {}).get("message", error_msg)
                return {
                    "success": False,
                    "error": error_msg,
                    "error_code": status_code
                }

        return {
            "success": False,
            "error": "获取配额失败",
            "error_code": 0
        }

    async def get_google_quota(self, auth_index: str, provider: str = "antigravity",
                               filename: str = "") -> Dict[str, Any]:
        """获取 Google Cloud Code 账号的配额信息 (支持 Antigravity 和 GeminiCLI)

        Args:
            auth_index: 凭证索引
            provider: 凭证类型 (antigravity, gemini, gemini-cli)
            filename: 凭证文件名（GeminiCLI 需要从中提取 project）

        Returns:
            Dict with keys:
                - "success": bool - 是否成功
                - "models": Dict - 配额模型数据（Antigravity 格式，仅在成功时存在）
                - "buckets": List - 配额桶列表（GeminiCLI 格式，仅在成功时存在）
                - "error": str - 错误信息（仅在失败时存在）
                - "error_code": int - HTTP 错误码（仅在失败时存在）
        """
        # GeminiCLI 使用 retrieveUserQuota 端点
        if provider.lower() in ("gemini", "gemini-cli"):
            project = extract_project_from_filename(filename)
            if not project:
                return {
                    "success": False,
                    "error": "无法从文件名提取项目名称",
                    "error_code": 0
                }
            return await self.get_gemini_cli_quota(auth_index, project)

        # Antigravity 使用 fetchAvailableModels 端点
        last_error = None
        last_status_code = None

        for quota_url in ANTIGRAVITY_QUOTA_URLS:
            result = await self.api_call(
                auth_index=auth_index,
                method="POST",
                url=quota_url,
                header=ANTIGRAVITY_REQUEST_HEADERS,
                data="{}"
            )
            if result:
                status_code = result.get("status_code", 0)
                if status_code == 200:
                    body = result.get("body", {})
                    if isinstance(body, dict) and "models" in body:
                        return {"success": True, "models": body.get("models", {})}
                elif status_code == 403:
                    return {
                        "success": False,
                        "error": "权限不足",
                        "error_code": 403
                    }
                else:
                    last_status_code = status_code
                    body = result.get("body", {})
                    if isinstance(body, dict):
                        last_error = body.get("error", {}).get("message", f"HTTP {status_code}")
                    else:
                        last_error = f"HTTP {status_code}"

        return {
            "success": False,
            "error": last_error or "获取配额失败",
            "error_code": last_status_code or 0
        }

    async def get_codex_quota(self, auth_index: str) -> Dict[str, Any]:
        """获取 Codex (OpenAI) 账号的配额信息

        Args:
            auth_index: 凭证索引

        Returns:
            Dict with keys:
                - "success": bool - 是否成功
                - "rate_limit": Dict - 配额信息（仅在成功时存在）
                    - "primary_window": Dict - 日限额（5小时窗口）
                    - "secondary_window": Dict - 周限额（7天窗口）
                - "plan_type": str - 计划类型（如 "team"）
                - "error": str - 错误信息（仅在失败时存在）
                - "error_code": int - HTTP 错误码（仅在失败时存在）
        """
        result = await self.api_call(
            auth_index=auth_index,
            method="GET",
            url=CODEX_QUOTA_URL,
            header=CODEX_QUOTA_HEADERS,
            data=""
        )

        if result:
            status_code = result.get("status_code", 0)
            if status_code == 200:
                body = result.get("body", {})
                # body 可能是字符串，需要解析
                if isinstance(body, str):
                    try:
                        body = json.loads(body)
                    except json.JSONDecodeError:
                        body = {}
                
                if isinstance(body, dict) and "rate_limit" in body:
                    return {
                        "success": True,
                        "rate_limit": body.get("rate_limit", {}),
                        "plan_type": body.get("plan_type", "unknown"),
                        "code_review_rate_limit": body.get("code_review_rate_limit"),
                        "credits": body.get("credits")
                    }
                return {
                    "success": False,
                    "error": "响应格式无效",
                    "error_code": 0
                }
            elif status_code == 401:
                return {
                    "success": False,
                    "error": "认证失败，Token 可能已过期",
                    "error_code": 401
                }
            elif status_code == 403:
                return {
                    "success": False,
                    "error": "权限不足",
                    "error_code": 403
                }
            else:
                body = result.get("body", {})
                if isinstance(body, str):
                    try:
                        body = json.loads(body)
                    except json.JSONDecodeError:
                        body = {}
                error_msg = f"HTTP {status_code}"
                if isinstance(body, dict) and "error" in body:
                    error_msg = body.get("error", {}).get("message", error_msg) if isinstance(body.get("error"), dict) else str(body.get("error", error_msg))
                return {
                    "success": False,
                    "error": error_msg,
                    "error_code": status_code
                }

        return {
            "success": False,
            "error": "获取配额失败",
            "error_code": 0
        }


class Main(Star):
    """CLIProxyAPI 额度统计插件"""

    def __init__(self, context: Context, config: AstrBotConfig) -> None:
        super().__init__(context)
        self.config = config
        self.cpa_url = self.config.get("cpa_url", "")
        self.cpa_password = self.config.get("cpa_password", "")
        self.verify_ssl = self.config.get("verify_ssl", False)
        self.enable_llm_analysis = self.config.get("enable_llm_analysis", False)
        self.llm_provider_id = self.config.get("llm_provider_id", "")
        self.high_res_render = self.config.get("high_res_render", True)
        
        # 各凭证类型最大渲染数量配置（0 表示不限制）
        self.max_render_count: Dict[str, int] = {
            "antigravity": int(self.config.get("max_render_antigravity", 10) or 10),
            "gemini-cli": int(self.config.get("max_render_gemini_cli", 10) or 10),
            "codex": int(self.config.get("max_render_codex", 10) or 10)
        }
        logger.info(f"max_render_count 配置: {self.max_render_count}")
        
        self._client: Optional[CPAClient] = None
        self._renderer: Optional[StatsCardRenderer] = None

    def _get_llm_provider(self) -> Optional[Provider]:
        """获取用于 LLM 分析的 Provider"""
        if not self.enable_llm_analysis:
            return None
        
        try:
            if self.llm_provider_id:
                # 使用指定的 Provider ID
                provider = self.context.get_provider_by_id(self.llm_provider_id)
                if provider:
                    return provider
                logger.warning(f"未找到指定的 Provider: {self.llm_provider_id}，将使用当前对话模型")
            
            # 使用当前对话模型
            return self.context.get_using_provider()
        except Exception as e:
            logger.error(f"获取 LLM Provider 失败: {e}")
            return None

    def _get_available_providers(self) -> List[Dict[str, str]]:
        """获取所有可用的 LLM Provider 列表（用于配置面板下拉选择）"""
        try:
            providers = self.context.get_all_providers()
            result = []
            for p in providers:
                try:
                    meta = p.meta()
                    result.append({"id": meta.id, "name": f"{meta.id} ({meta.model})"})
                except Exception:
                    pass
            return result
        except Exception as e:
            logger.error(f"获取 Provider 列表失败: {e}")
            return []

    async def _render_image(self, data: dict) -> Optional[str]:
        """使用自定义渲染器将统计数据转换为美观的卡片图片"""
        try:
            # 复用渲染器实例（配置变更时重建）
            if self._renderer is None:
                self._renderer = StatsCardRenderer(high_res=self.high_res_render)
            img = self._renderer.render(data)

            if img is None:
                logger.warning("渲染器返回空图片")
                return None

            # 保存图片到临时目录
            result = save_temp_img(img)

            if result and os.path.exists(result):
                file_size = os.path.getsize(result)
                if file_size > 1024:
                    logger.info(f"统计卡片渲染成功，路径: {result}，大小: {file_size} 字节")
                    return result
                else:
                    logger.warning(f"渲染图片太小 ({file_size} 字节)")
            else:
                logger.warning(f"渲染图片保存失败: {result}")
        except Exception as e:
            logger.error(f"统计卡片渲染失败: {e}", exc_info=True)

        return None

    def _build_text_from_data(self, data: dict) -> Optional[str]:
        """从数据构建纯文本（用于回退渲染）"""
        stats_type = data.get("stats_type", "")
        lines = []

        if stats_type == "overview":
            lines.append(f"# {data.get('title', 'CLIProxyAPI 统计')}")
            lines.append("")
            lines.append("## 总体统计")
            lines.append(f"- 总请求数: **{data.get('total_requests', 0)}**")
            lines.append(f"- 成功率: **{data.get('success_rate', 0)}%**")
            lines.append(f"- 成功/失败: {data.get('success_count', 0)} / {data.get('failure_count', 0)}")
            lines.append(f"- 总 Token: **{data.get('total_tokens', '0')}**")

            apis = data.get("apis", [])
            if apis:
                lines.append("")
                lines.append("## 各接口统计")
                for api in apis[:8]:
                    lines.append(f"- {api['name']}: {api['requests']} 次 / {api['tokens']}")

            auth_info = data.get("auth_info")
            if auth_info:
                lines.append("")
                lines.append(f"## OAuth 账号: {auth_info['active']}/{auth_info['total']} 可用")
                for p in auth_info.get("providers", []):
                    lines.append(f"- {p['name']}: {p['active']}/{p['total']}")

        elif stats_type == "today":
            lines.append(f"# {data.get('title', '今日统计')}")
            lines.append(f"日期: {data.get('subtitle', '')}")
            lines.append("")
            lines.append(f"- 请求数: **{data.get('today_requests', 0)}**")
            lines.append(f"- Token: **{data.get('today_tokens', '0')}**")

            model_stats = data.get("model_stats")
            if model_stats:
                lines.append("")
                lines.append("## 各模型详情")
                for m in model_stats[:10]:
                    fail_info = f" (失败{m['failed']})" if m.get('failed', 0) > 0 else ""
                    lines.append(f"- {m['name']}: {m['requests']} 次{fail_info} / {m['tokens']}")

            time_slots = data.get("time_slots")
            if time_slots:
                lines.append("")
                lines.append("## 时段分布")
                for slot in time_slots:
                    lines.append(f"- {slot['label']}: {slot['count']}")

        elif stats_type == "quota":
            lines.append(f"# {data.get('title', 'OAuth 配额状态')}")
            lines.append("")

            for account in data.get("accounts", []):
                lines.append(f"### {account['icon']} {account['email']}")
                if account.get("error"):
                    lines.append(f"  ⚠️ {account['error']}")
                else:
                    for q in account.get("quotas", []):
                        lines.append(f"  - {q['icon']} {q['label']}: **{q['percent']}%** | 刷新: {q['reset_time']}")
                lines.append("")

            lines.append("> 💡 配额每日自动刷新，百分比为剩余额度")

        return "\n".join(lines) if lines else None

    def _get_client(self) -> Optional[CPAClient]:
        """获取 CPA 客户端（复用同一个实例）"""
        if not self.cpa_url or not self.cpa_password:
            return None
        if self._client is None:
            self._client = CPAClient(self.cpa_url, self.cpa_password, self.verify_ssl)
        return self._client

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

    def _parse_quota_dynamic(self, models: Dict[str, Any]) -> List[Dict[str, Any]]:
        """动态解析配额信息，显示所有可用模型（不限于预设列表）"""
        quotas = []
        
        for model_id, entry in models.items():
            quota_info = entry.get("quotaInfo", entry.get("quota_info", {}))
            remaining = quota_info.get("remainingFraction", quota_info.get("remaining_fraction"))
            reset_time = quota_info.get("resetTime", quota_info.get("reset_time"))
            
            if remaining is not None:
                quotas.append({
                    "id": model_id,
                    "label": model_id,
                    "remaining_percent": round(remaining * 100),
                    "reset_time": reset_time,
                    "models": [model_id]
                })
        
        # 按剩余配额排序（低的在前，便于关注）
        quotas.sort(key=lambda x: x["remaining_percent"])
        return quotas

    def _parse_gemini_cli_quota_dynamic(self, buckets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """动态解析 GeminiCLI 配额信息（显示所有模型）"""
        quotas = []
        
        for bucket in buckets:
            model_id = bucket.get("modelId", "")
            remaining = bucket.get("remainingFraction")
            reset_time = bucket.get("resetTime")
            
            if model_id and remaining is not None:
                quotas.append({
                    "id": model_id,
                    "label": model_id,
                    "remaining_percent": round(remaining * 100),
                    "reset_time": reset_time,
                    "models": [model_id]
                })
        
        # 按剩余配额排序
        quotas.sort(key=lambda x: x["remaining_percent"])
        return quotas

    def _parse_quota(self, models: Dict[str, Any]) -> List[Dict[str, Any]]:
        """解析配额信息，返回按分组聚合的配额列表 (通用方法，支持所有 Google Cloud Code 凭证)"""
        groups = []

        for group_def in QUOTA_GROUPS:
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

    def _parse_antigravity_quota(self, models: Dict[str, Any]) -> List[Dict[str, Any]]:
        """解析 Antigravity 配额信息 (保留向后兼容)"""
        return self._parse_quota(models)

    def _parse_gemini_cli_quota(self, buckets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """解析 GeminiCLI 配额信息 (buckets 格式)

        Args:
            buckets: API 返回的 buckets 数组，格式如：
                [{"modelId": "gemini-2.5-flash", "remainingFraction": 1, "resetTime": "...", "tokenType": "REQUESTS"}]

        Returns:
            配额分组列表，格式与 _parse_quota 一致
        """
        groups = []

        # 将 buckets 转换为按 modelId 索引的字典
        model_map = {}
        for bucket in buckets:
            model_id = bucket.get("modelId", "")
            if model_id:
                model_map[model_id] = bucket

        for group_def in GEMINI_CLI_QUOTA_GROUPS:
            group_id = group_def["id"]
            label = group_def["label"]
            identifiers = group_def["identifiers"]

            matched_entries = []
            for identifier in identifiers:
                if identifier in model_map:
                    bucket = model_map[identifier]
                    remaining = bucket.get("remainingFraction")
                    reset_time = bucket.get("resetTime")

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

    def _format_codex_reset_time(self, reset_at: Optional[int]) -> str:
        """格式化 Codex 配额刷新时间（Unix 时间戳转本地时间）"""
        if not reset_at:
            return "-"
        try:
            dt = datetime.fromtimestamp(reset_at)
            return dt.strftime("%m/%d %H:%M")
        except Exception:
            return str(reset_at)

    def _parse_codex_quota(self, rate_limit: Dict[str, Any], plan_type: str = "unknown") -> List[Dict[str, Any]]:
        """解析 Codex (OpenAI) 配额信息

        Args:
            rate_limit: API 返回的 rate_limit 对象，包含 primary_window 和 secondary_window
            plan_type: 计划类型（如 "team"）

        Returns:
            配额分组列表，格式与其他 provider 一致
        """
        quotas = []

        # 处理 primary_window（日限额/5小时窗口）
        primary = rate_limit.get("primary_window")
        if primary:
            used_percent = primary.get("used_percent", 0)
            remaining_percent = 100 - used_percent
            reset_at = primary.get("reset_at")
            window_seconds = primary.get("limit_window_seconds", 0)
            
            # 根据窗口时间确定标签
            if window_seconds <= 21600:  # 6小时以内
                label = "日限额"
            else:
                label = "主限额"
            
            quotas.append({
                "id": "codex-primary",
                "label": label,
                "remaining_percent": remaining_percent,
                "reset_time": reset_at,
                "reset_time_formatted": self._format_codex_reset_time(reset_at),
                "window_seconds": window_seconds,
                "models": ["codex"],
                "is_codex": True
            })

        # 处理 secondary_window（周限额）
        secondary = rate_limit.get("secondary_window")
        if secondary:
            used_percent = secondary.get("used_percent", 0)
            remaining_percent = 100 - used_percent
            reset_at = secondary.get("reset_at")
            window_seconds = secondary.get("limit_window_seconds", 0)
            
            # 根据窗口时间确定标签
            if window_seconds >= 604800:  # 7天
                label = "周限额"
            else:
                label = "次限额"
            
            quotas.append({
                "id": "codex-secondary",
                "label": label,
                "remaining_percent": remaining_percent,
                "reset_time": reset_at,
                "reset_time_formatted": self._format_codex_reset_time(reset_at),
                "window_seconds": window_seconds,
                "models": ["codex"],
                "is_codex": True
            })

        # 按剩余配额排序（低的在前，便于关注）
        quotas.sort(key=lambda x: x["remaining_percent"])
        return quotas

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
            # 构建今日统计数据
            data = await self._build_today_data(client)
            if data:
                image_path = await self._render_image(data)
                if image_path:
                    yield event.image_result(image_path)
                    return
            # 后备：纯文本
            yield event.plain_result(await self._get_today_stats(client))
        else:
            # 构建总览数据
            data = await self._build_overview_data(client)
            if data:
                image_path = await self._render_image(data)
                if image_path:
                    yield event.image_result(image_path)
                    return
            # 后备：纯文本
            yield event.plain_result(await self._get_overview(client))

    @filter.command("cpa额度")
    async def cpa_quota(self, event: AstrMessageEvent):
        """查看 CLIProxyAPI OAuth 账号配额（实时获取）"""
        client = self._get_client()
        if not client:
            yield event.plain_result("❌ 未配置 CLIProxyAPI 地址或密码，请在插件配置中设置")
            return

        # 构建配额数据
        data = await self._build_quota_data(client)
        if data:
            image_path = await self._render_image(data)
            if image_path:
                yield event.image_result(image_path)
                return
        # 后备：纯文本
        yield event.plain_result(await self._get_quota_status(client))

    @filter.command("cpa今日")
    async def cpa_today(self, event: AstrMessageEvent):
        """查看今日使用统计"""
        client = self._get_client()
        if not client:
            yield event.plain_result("❌ 未配置 CLIProxyAPI 地址或密码，请在插件配置中设置")
            return

        # 构建今日统计数据
        data = await self._build_today_data(client)
        if data:
            image_path = await self._render_image(data)
            if image_path:
                yield event.image_result(image_path)
                return
        # 后备：纯文本
        yield event.plain_result(await self._get_today_stats(client))

    @filter.command("cpa总览")
    async def cpa_dashboard(self, event: AstrMessageEvent):
        """查看综合仪表盘（整合今日统计 + 配额状态 + AI分析）"""
        client = self._get_client()
        if not client:
            yield event.plain_result("❌ 未配置 CLIProxyAPI 地址或密码，请在插件配置中设置")
            return

        yield event.plain_result("📊 正在生成综合仪表盘，请稍候...")

        # 并行获取所有数据
        today_data = await self._build_today_data(client)
        quota_data = await self._build_quota_data(client)
        
        # 获取 LLM 分析（如果启用）
        analysis_text = ""
        if self.enable_llm_analysis and today_data:
            analysis_text = await self._generate_llm_analysis(today_data, quota_data) or ""

        if not today_data:
            yield event.plain_result("❌ 获取使用数据失败")
            return

        # 构建仪表盘数据
        dashboard_data = {
            "stats_type": "dashboard",
            "today": today_data,
            "quota": quota_data or {},
            "analysis": analysis_text,
            "query_time": datetime.now().strftime("%H:%M:%S")
        }

        # 渲染图片
        image_path = await self._render_image(dashboard_data)
        if image_path:
            yield event.image_result(image_path)
        else:
            # 后备：纯文本
            yield event.plain_result("❌ 仪表盘渲染失败，请查看日志")

    async def _build_overview_data(self, client: CPAClient) -> Optional[Dict[str, Any]]:
        """构建总览页面的模板数据"""
        usage_data = await client.get_usage()
        auth_data = await client.get_auth_files()

        if not usage_data:
            return None

        usage = usage_data.get("usage", {})

        total_requests = usage.get("total_requests", 0)
        success_count = usage.get("success_count", 0)
        failure_count = usage.get("failure_count", 0)
        total_tokens = usage.get("total_tokens", 0)
        success_rate = round((success_count / total_requests * 100), 1) if total_requests > 0 else 0

        # 构建 API 列表
        apis = usage.get("apis", {})
        api_list = []
        if apis:
            sorted_apis = sorted(apis.items(), key=lambda x: x[1].get("total_requests", 0), reverse=True)
            for api_name, api_data in sorted_apis[:8]:  # 只显示前8个
                api_list.append({
                    "name": api_name,
                    "requests": api_data.get("total_requests", 0),
                    "tokens": self._format_tokens(api_data.get("total_tokens", 0))
                })

        # 构建认证信息
        auth_info = None
        if auth_data and auth_data.get("files"):
            auth_files = auth_data.get("files", [])
            active_count = sum(1 for f in auth_files if not f.get("disabled", False) and not f.get("unavailable", False))
            total_auth = len(auth_files)

            # 按类型分组
            type_counts: Dict[str, Dict[str, int]] = {}
            for auth in auth_files:
                provider = auth.get("provider", auth.get("type", "unknown"))
                if provider not in type_counts:
                    type_counts[provider] = {"total": 0, "active": 0}
                type_counts[provider]["total"] += 1
                if not auth.get("disabled", False) and not auth.get("unavailable", False):
                    type_counts[provider]["active"] += 1

            providers = []
            for provider, counts in type_counts.items():
                providers.append({
                    "name": self._get_provider_display(provider),
                    "active": counts["active"],
                    "total": counts["total"]
                })

            auth_info = {
                "active": active_count,
                "total": total_auth,
                "providers": providers
            }

        return {
            "stats_type": "overview",
            "title": "📊 CLIProxyAPI 统计",
            "subtitle": "总览",
            "total_requests": total_requests,
            "success_count": success_count,
            "failure_count": failure_count,
            "success_rate": success_rate,
            "total_tokens": self._format_tokens(total_tokens),
            "apis": api_list,
            "auth_info": auth_info,
            "query_time": datetime.now().strftime("%H:%M:%S")
        }

    async def _build_today_data(self, client: CPAClient) -> Optional[Dict[str, Any]]:
        """构建今日统计的模板数据（增强版：包含 Token 分解和凭证统计）"""
        usage_data = await client.get_usage()

        if not usage_data:
            return None

        usage = usage_data.get("usage", {})
        today = date.today().isoformat()

        requests_by_day = usage.get("requests_by_day", {})
        tokens_by_day = usage.get("tokens_by_day", {})

        today_requests = requests_by_day.get(today, 0)
        today_tokens = tokens_by_day.get(today, 0)

        # 各模型今日统计 + Token 分解 + 凭证统计
        apis = usage.get("apis", {})
        model_stats = []
        today_by_hour: Dict[int, int] = {h: 0 for h in range(24)}
        
        # 凭证使用统计
        auth_usage: Dict[str, Dict[str, Any]] = {}
        
        # Token 分解统计
        total_input_tokens = 0
        total_output_tokens = 0
        total_reasoning_tokens = 0
        total_cached_tokens = 0

        if apis:
            # 聚合所有模型的今日统计
            model_aggregated: Dict[str, Dict[str, Any]] = {}
            
            for api_name, api_data in apis.items():
                models = api_data.get("models", {})
                for model_name, model_data in models.items():
                    details = model_data.get("details", [])
                    today_details = [d for d in details if str(d.get("timestamp", "")).startswith(today)]
                    
                    if today_details:
                        # 聚合模型统计
                        if model_name not in model_aggregated:
                            model_aggregated[model_name] = {
                                "requests": 0,
                                "tokens": 0,
                                "failed": 0,
                                "input_tokens": 0,
                                "output_tokens": 0,
                                "reasoning_tokens": 0,
                                "cached_tokens": 0
                            }
                        
                        for d in today_details:
                            model_aggregated[model_name]["requests"] += 1
                            tokens_info = d.get("tokens", {})
                            
                            # Token 分解
                            input_tok = tokens_info.get("input_tokens", 0)
                            output_tok = tokens_info.get("output_tokens", 0)
                            reasoning_tok = tokens_info.get("reasoning_tokens", 0)
                            cached_tok = tokens_info.get("cached_tokens", 0)
                            total_tok = tokens_info.get("total_tokens", 0)
                            
                            model_aggregated[model_name]["tokens"] += total_tok
                            model_aggregated[model_name]["input_tokens"] += input_tok
                            model_aggregated[model_name]["output_tokens"] += output_tok
                            model_aggregated[model_name]["reasoning_tokens"] += reasoning_tok
                            model_aggregated[model_name]["cached_tokens"] += cached_tok
                            
                            # 全局 Token 统计
                            total_input_tokens += input_tok
                            total_output_tokens += output_tok
                            total_reasoning_tokens += reasoning_tok
                            total_cached_tokens += cached_tok
                            
                            if d.get("failed", False):
                                model_aggregated[model_name]["failed"] += 1
                            
                            # 凭证使用统计
                            auth_index = d.get("auth_index", "unknown")
                            if auth_index not in auth_usage:
                                auth_usage[auth_index] = {"requests": 0, "tokens": 0, "failed": 0}
                            auth_usage[auth_index]["requests"] += 1
                            auth_usage[auth_index]["tokens"] += total_tok
                            if d.get("failed", False):
                                auth_usage[auth_index]["failed"] += 1
                            
                            # 小时分布
                            timestamp = str(d.get("timestamp", ""))
                            try:
                                hour = int(timestamp[11:13])
                                today_by_hour[hour] += 1
                            except (ValueError, IndexError):
                                pass

            # 转换为列表并排序
            model_list = [
                (name, data["requests"], data["tokens"], data["failed"],
                 data["input_tokens"], data["output_tokens"], data["reasoning_tokens"], data["cached_tokens"])
                for name, data in model_aggregated.items()
            ]
            model_list.sort(key=lambda x: x[1], reverse=True)
            
            for item in model_list[:15]:  # 显示前15个模型
                model_name, req_count, tok_count, fail_count, in_tok, out_tok, reason_tok, cache_tok = item
                model_stats.append({
                    "name": model_name,
                    "requests": req_count,
                    "tokens": self._format_tokens(tok_count),
                    "failed": fail_count,
                    "input_tokens": in_tok,
                    "output_tokens": out_tok,
                    "reasoning_tokens": reason_tok,
                    "cached_tokens": cache_tok
                })

        # 时段统计
        time_slots = [
            {"label": "凌晨 0-6", "count": sum(today_by_hour[h] for h in range(0, 6))},
            {"label": "上午 6-12", "count": sum(today_by_hour[h] for h in range(6, 12))},
            {"label": "下午 12-18", "count": sum(today_by_hour[h] for h in range(12, 18))},
            {"label": "晚间 18-24", "count": sum(today_by_hour[h] for h in range(18, 24))}
        ]
        
        # 凭证使用统计列表
        auth_stats = []
        for auth_id, stats in sorted(auth_usage.items(), key=lambda x: x[1]["requests"], reverse=True)[:10]:
            auth_stats.append({
                "auth_index": auth_id,
                "requests": stats["requests"],
                "tokens": self._format_tokens(stats["tokens"]),
                "failed": stats["failed"]
            })

        # 计算成功率
        total_failed = sum(m.get("failed", 0) for m in model_stats)
        success_rate = round((today_requests - total_failed) / today_requests * 100, 1) if today_requests > 0 else 100

        return {
            "stats_type": "today",
            "title": "📅 今日使用统计",
            "subtitle": today,
            "today_requests": today_requests,
            "today_tokens": self._format_tokens(today_tokens),
            "success_rate": success_rate,
            "model_stats": model_stats if model_stats else None,
            "time_slots": time_slots if sum(s["count"] for s in time_slots) > 0 else None,
            "auth_stats": auth_stats if auth_stats else None,
            "token_breakdown": {
                "input": self._format_tokens(total_input_tokens),
                "output": self._format_tokens(total_output_tokens),
                "reasoning": self._format_tokens(total_reasoning_tokens),
                "cached": self._format_tokens(total_cached_tokens)
            },
            "query_time": datetime.now().strftime("%H:%M:%S")
        }

    async def _build_quota_data(self, client: CPAClient) -> Optional[Dict[str, Any]]:
        """构建配额页面的模板数据（支持多凭证类型）"""
        auth_data = await client.get_auth_files()

        if not auth_data:
            return None

        auth_files = auth_data.get("files", [])
        if not auth_files:
            return None

        # 筛选支持配额查询的账号 (Antigravity 和 GeminiCLI)
        quota_auths = [
            auth for auth in auth_files
            if auth.get("provider", auth.get("type", "")).lower() in QUOTA_SUPPORTED_PROVIDERS
        ]

        if not quota_auths:
            return None

        # 按凭证类型分组 (将 gemini-cli 归类为 gemini)
        provider_groups: Dict[str, List[Dict[str, Any]]] = {}
        for auth in quota_auths:
            provider = auth.get("provider", auth.get("type", "unknown")).lower()
            # 标准化 provider 名称：gemini-cli -> gemini
            display_provider = "gemini" if provider == "gemini-cli" else provider
            if display_provider not in provider_groups:
                provider_groups[display_provider] = []
            provider_groups[display_provider].append(auth)

        accounts = []
        for provider, auths in provider_groups.items():
            provider_info = PROVIDER_INFO.get(provider, {"name": provider.title(), "icon": "📦", "color": "#6b7280"})

            for auth in auths:
                auth_index = auth.get("auth_index", "")
                email = auth.get("email", "")
                name = auth.get("name", auth.get("id", "未知"))
                disabled = auth.get("disabled", False)
                unavailable = auth.get("unavailable", False)
                # 获取原始的 provider 类型（用于 API 调用）
                original_provider = auth.get("provider", auth.get("type", "unknown")).lower()

                icon = "❌" if (disabled or unavailable) else "✅"
                display = email if email else name
                if len(display) > 30:
                    display = display[:27] + "..."

                account_data = {
                    "icon": icon,
                    "email": display,
                    "provider": provider,
                    "provider_name": provider_info["name"],
                    "provider_icon": provider_info["icon"],
                    "provider_color": provider_info["color"],
                    "error": None,
                    "quotas": []
                }

                if not auth_index:
                    account_data["error"] = "无法获取配额（缺少 auth_index）"
                    accounts.append(account_data)
                    continue

                if disabled or unavailable:
                    account_data["error"] = "账号已禁用或不可用"
                    accounts.append(account_data)
                    continue

                # 获取配额信息（根据 provider 类型选择不同的 API）
                logger.debug(f"正在获取配额: provider={original_provider}, name={name}, auth_index={auth_index}")
                
                if original_provider == "codex":
                    # Codex 使用专用的配额查询 API
                    quota_result = await client.get_codex_quota(auth_index)
                    logger.debug(f"Codex 配额获取结果: success={quota_result.get('success')}, rate_limit={quota_result.get('rate_limit') is not None}")
                else:
                    # Antigravity/GeminiCLI 使用 Google Cloud Code API
                    quota_result = await client.get_google_quota(auth_index, original_provider, name)
                    logger.debug(f"配额获取结果: success={quota_result.get('success')}, buckets={len(quota_result.get('buckets', []))}, models={len(quota_result.get('models', {}))}")

                if not quota_result.get("success"):
                    # 根据错误码显示不同的错误信息
                    error_code = quota_result.get("error_code", 0)
                    if error_code == 403:
                        account_data["error"] = "不支持配额查询"
                        account_data["error_detail"] = "此凭证类型暂不支持配额查询"
                    else:
                        account_data["error"] = quota_result.get("error", "获取配额失败")
                    accounts.append(account_data)
                    continue

                # 根据凭证类型选择解析方法（使用动态解析，显示所有模型）
                if original_provider == "codex":
                    # Codex 使用 rate_limit 格式
                    rate_limit = quota_result.get("rate_limit", {})
                    if not rate_limit:
                        account_data["error"] = "无配额信息"
                        accounts.append(account_data)
                        continue
                    plan_type = quota_result.get("plan_type", "unknown")
                    quota_groups = self._parse_codex_quota(rate_limit, plan_type)
                elif original_provider in ("gemini", "gemini-cli"):
                    # GeminiCLI 使用 buckets 格式
                    buckets = quota_result.get("buckets", [])
                    if not buckets:
                        account_data["error"] = "无配额信息"
                        accounts.append(account_data)
                        continue
                    quota_groups = self._parse_gemini_cli_quota_dynamic(buckets)
                else:
                    # Antigravity 使用 models 格式
                    models = quota_result.get("models", {})
                    if not models:
                        account_data["error"] = "无可用模型"
                        accounts.append(account_data)
                        continue
                    quota_groups = self._parse_quota_dynamic(models)

                if not quota_groups:
                    account_data["error"] = "无配额信息"
                    accounts.append(account_data)
                    continue

                for group in quota_groups:
                    percent = group["remaining_percent"]
                    label = group["label"]
                    
                    # 根据是否为 Codex 选择不同的时间格式化方法
                    if group.get("is_codex"):
                        reset_time = group.get("reset_time_formatted", "-")
                    else:
                        reset_time = self._format_reset_time(group.get("reset_time"))

                    # 配额状态
                    if percent >= 80:
                        status_icon = "🟢"
                        color = "#10b981"
                        level = "high"
                    elif percent >= 50:
                        status_icon = "🟡"
                        color = "#f59e0b"
                        level = "medium"
                    elif percent >= 20:
                        status_icon = "🟠"
                        color = "#f97316"
                        level = "medium"
                    else:
                        status_icon = "🔴"
                        color = "#ef4444"
                        level = "low"

                    account_data["quotas"].append({
                        "label": label,
                        "icon": status_icon,
                        "percent": percent,
                        "color": color,
                        "level": level,
                        "reset_time": reset_time
                    })

                accounts.append(account_data)

        # 构建支持的凭证类型摘要
        provider_summary = []
        for provider in provider_groups.keys():
            info = PROVIDER_INFO.get(provider, {"name": provider.title(), "icon": "📦"})
            count = len([a for a in accounts if a.get("provider") == provider])
            provider_summary.append(f"{info['icon']} {info['name']} ({count})")

        return {
            "stats_type": "quota",
            "title": "📊 OAuth 配额状态",
            "subtitle": " | ".join(provider_summary) if provider_summary else "无账号",
            "accounts": accounts,
            "provider_groups": list(provider_groups.keys()),
            "query_time": datetime.now().strftime("%H:%M:%S"),  # 添加查询时间用于调试
            "max_render_count": self.max_render_count  # 传递给渲染器的截断配置
        }

    async def _get_overview(self, client: CPAClient) -> str:
        """获取总览信息（复用数据构建逻辑）"""
        data = await self._build_overview_data(client)
        if not data:
            return "❌ 获取使用统计失败，请检查配置"
        return self._build_text_from_data(data) or "❌ 数据格式化失败"

    async def _get_today_stats(self, client: CPAClient) -> str:
        """获取今日统计（复用数据构建逻辑）"""
        data = await self._build_today_data(client)
        if not data:
            return "❌ 获取使用统计失败，请检查配置"
        return self._build_text_from_data(data) or "❌ 数据格式化失败"

    async def _get_quota_status(self, client: CPAClient) -> str:
        """获取 OAuth 账号配额状态（实时从 API 获取，支持多凭证类型）"""
        auth_data = await client.get_auth_files()

        if not auth_data:
            return "❌ 获取账号状态失败，请检查配置"

        auth_files = auth_data.get("files", [])

        if not auth_files:
            return "📭 暂无 OAuth 账号"

        # 筛选支持配额查询的账号
        quota_auths = [
            auth for auth in auth_files
            if auth.get("provider", auth.get("type", "")).lower() in QUOTA_SUPPORTED_PROVIDERS
        ]

        if not quota_auths:
            supported_names = ", ".join([PROVIDER_INFO.get(p, {}).get("name", p) for p in QUOTA_SUPPORTED_PROVIDERS])
            return f"📭 暂无支持配额查询的账号（支持: {supported_names}）"

        lines = ["📊 OAuth 账号配额状态", ""]

        # 按凭证类型分组 (将 gemini-cli 归类为 gemini)
        provider_groups: Dict[str, list] = {}
        for auth in quota_auths:
            provider = auth.get("provider", auth.get("type", "unknown")).lower()
            # 标准化 provider 名称：gemini-cli -> gemini
            display_provider = "gemini" if provider == "gemini-cli" else provider
            if display_provider not in provider_groups:
                provider_groups[display_provider] = []
            provider_groups[display_provider].append(auth)

        for provider, auths in provider_groups.items():
            provider_info = PROVIDER_INFO.get(provider, {"name": provider.title(), "icon": "📦"})
            lines.append(f"━━━ {provider_info['icon']} {provider_info['name']} ━━━")
            lines.append("")
            
            # 应用截断限制
            config_key = "gemini-cli" if provider == "gemini" else provider
            max_count = self.max_render_count.get(config_key, 0)
            truncated_count = 0
            if max_count > 0 and len(auths) > max_count:
                truncated_count = len(auths) - max_count
                auths_to_show = auths[:max_count]
            else:
                auths_to_show = auths

            for auth in auths_to_show:
                auth_index = auth.get("auth_index", "")
                email = auth.get("email", "")
                name = auth.get("name", auth.get("id", "未知"))
                disabled = auth.get("disabled", False)
                unavailable = auth.get("unavailable", False)
                # 获取原始的 provider 类型（用于 API 调用）
                original_provider = auth.get("provider", auth.get("type", "unknown")).lower()

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

                # 获取配额信息（根据 provider 类型选择不同的 API）
                if original_provider == "codex":
                    quota_result = await client.get_codex_quota(auth_index)
                else:
                    quota_result = await client.get_google_quota(auth_index, original_provider, name)

                if not quota_result.get("success"):
                    error_code = quota_result.get("error_code", 0)
                    if error_code == 403:
                        lines.append("   ⚠️ 不支持配额查询")
                    else:
                        lines.append(f"   ⚠️ {quota_result.get('error', '获取配额失败')}")
                    lines.append("")
                    continue

                # 根据凭证类型选择解析方法（使用动态解析，显示所有模型）
                if original_provider == "codex":
                    # Codex 使用 rate_limit 格式
                    rate_limit = quota_result.get("rate_limit", {})
                    if not rate_limit:
                        lines.append("   ⚠️ 无配额信息")
                        lines.append("")
                        continue
                    plan_type = quota_result.get("plan_type", "unknown")
                    quota_groups = self._parse_codex_quota(rate_limit, plan_type)
                elif original_provider in ("gemini", "gemini-cli"):
                    # GeminiCLI 使用 buckets 格式
                    buckets = quota_result.get("buckets", [])
                    if not buckets:
                        lines.append("   ⚠️ 无配额信息")
                        lines.append("")
                        continue
                    quota_groups = self._parse_gemini_cli_quota_dynamic(buckets)
                else:
                    # Antigravity 使用 models 格式
                    models = quota_result.get("models", {})
                    if not models:
                        lines.append("   ⚠️ 无可用模型")
                        lines.append("")
                        continue
                    quota_groups = self._parse_quota_dynamic(models)

                if not quota_groups:
                    lines.append("   ⚠️ 无配额信息")
                    lines.append("")
                    continue

                for group in quota_groups:
                    percent = group["remaining_percent"]
                    label = group["label"]
                    
                    # 根据是否为 Codex 选择不同的时间格式化方法
                    if group.get("is_codex"):
                        reset_time = group.get("reset_time_formatted", "-")
                    else:
                        reset_time = self._format_reset_time(group.get("reset_time"))

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

            # 显示截断提示
            if truncated_count > 0:
                lines.append(f"   ⋯ 还有 {truncated_count} 个 {provider_info['name']} 账号未显示")
                lines.append("")

        lines.append("💡 配额每日自动刷新，百分比为剩余额度")

        return "\n".join(lines).rstrip()

    async def terminate(self):
        """插件终止，关闭 HTTP 连接"""
        if self._client:
            await self._client.close()
            self._client = None
        logger.info("CLIProxyAPI 统计插件已终止")

    async def _generate_llm_analysis(self, today_data: Dict[str, Any], 
                                     quota_data: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """使用 LLM 生成使用情况分析"""
        if not self.enable_llm_analysis:
            return None
        
        provider = self._get_llm_provider()
        if not provider:
            logger.warning("无法获取 LLM Provider，跳过智能分析")
            return None
        
        try:
            now = datetime.now()
            hours_elapsed = now.hour + now.minute / 60
            
            # 构建模型统计文本（更详细）
            model_stats_text = ""
            total_requests = today_data.get("today_requests", 0)
            if today_data.get("model_stats"):
                for m in today_data["model_stats"][:15]:
                    req_count = m.get('requests', 0)
                    tokens = m.get('tokens', '0')
                    failed = m.get('failed', 0)
                    
                    # 计算占比
                    pct = round(req_count / total_requests * 100, 1) if total_requests > 0 else 0
                    
                    # 计算平均 Token（如果可能）
                    avg_tokens = ""
                    if req_count > 0:
                        # 尝试解析 tokens 字符串
                        try:
                            if 'M' in str(tokens):
                                tok_num = float(str(tokens).replace('M', '')) * 1_000_000
                            elif 'K' in str(tokens):
                                tok_num = float(str(tokens).replace('K', '')) * 1_000
                            else:
                                tok_num = float(tokens)
                            avg = tok_num / req_count
                            if avg >= 1000:
                                avg_tokens = f", 平均 {avg/1000:.1f}K/次"
                            else:
                                avg_tokens = f", 平均 {int(avg)}/次"
                        except (ValueError, TypeError):
                            pass
                    
                    fail_info = f", 失败 {failed}" if failed > 0 else ""
                    model_stats_text += f"- {m['name']}: {req_count} 次 ({pct}%), {tokens} tokens{avg_tokens}{fail_info}\n"
            else:
                model_stats_text = "暂无模型使用数据"
            
            # 构建配额统计文本（包含刷新时间，更易于分析）
            quota_stats_text = ""
            if quota_data and quota_data.get("accounts"):
                for account in quota_data["accounts"][:8]:
                    if account.get("quotas"):
                        email = account.get('email', '未知账号')
                        quota_stats_text += f"\n账号 {email}:\n"
                        for q in account["quotas"][:8]:
                            label = q.get('label', '')
                            percent = q.get('percent', 0)
                            reset_time = q.get('reset_time', '未知')
                            used = 100 - percent
                            quota_stats_text += f"  - {label}: 剩余 {percent}% (已用 {used}%), 刷新时间: {reset_time}\n"
            if not quota_stats_text:
                quota_stats_text = "暂无配额数据"
            
            # 构建小时级分布（更精细）
            hourly_text = ""
            if today_data.get("time_slots"):
                for slot in today_data["time_slots"]:
                    hourly_text += f"- {slot['label']}: {slot['count']} 次\n"
            else:
                hourly_text = "暂无时段数据"
            
            # 构建 prompt
            prompt = LLM_ANALYSIS_PROMPT.format(
                current_time=now.strftime("%Y-%m-%d %H:%M"),
                date=today_data.get("subtitle", date.today().isoformat()),
                total_requests=today_data.get("today_requests", 0),
                total_tokens=today_data.get("today_tokens", "0"),
                success_rate=today_data.get("success_rate", 100),
                hours_elapsed=f"{hours_elapsed:.1f}",
                model_stats=model_stats_text,
                quota_stats=quota_stats_text,
                hourly_distribution=hourly_text
            )
            
            # 调用 LLM
            response = await provider.text_chat(prompt=prompt)
            if response and response.completion_text:
                return response.completion_text
            
        except Exception as e:
            logger.error(f"LLM 分析生成失败: {e}")
        
        return None

    @filter.command("cpa分析")
    async def cpa_analysis(self, event: AstrMessageEvent):
        """查看今日使用情况的 LLM 智能分析"""
        if not self.enable_llm_analysis:
            yield event.plain_result("❌ LLM 分析功能未启用，请在插件配置中开启 'enable_llm_analysis'")
            return
        
        client = self._get_client()
        if not client:
            yield event.plain_result("❌ 未配置 CLIProxyAPI 地址或密码，请在插件配置中设置")
            return
        
        yield event.plain_result("🔍 正在分析今日使用情况，请稍候...")
        
        # 获取今日数据和配额数据
        today_data = await self._build_today_data(client)
        quota_data = await self._build_quota_data(client)
        
        if not today_data:
            yield event.plain_result("❌ 获取使用数据失败")
            return
        
        # 生成 LLM 分析
        analysis = await self._generate_llm_analysis(today_data, quota_data)
        
        if analysis:
            # 构建完整的分析报告
            report = f"📊 **CLIProxyAPI 今日使用分析**\n"
            report += f"📅 日期: {today_data.get('subtitle', '')}\n"
            report += f"📈 请求: {today_data.get('today_requests', 0)} 次 | Token: {today_data.get('today_tokens', '0')}\n"
            report += f"\n{analysis}"
            yield event.plain_result(report)
        else:
            yield event.plain_result("❌ LLM 分析生成失败，请检查 Provider 配置")

    @filter.command("cpa服务商")
    async def cpa_providers(self, event: AstrMessageEvent):
        """列出可用的 LLM 服务商（用于配置 llm_provider_id）"""
        providers = self._get_available_providers()
        
        if not providers:
            yield event.plain_result("❌ 未找到可用的 LLM 服务商，请先在 AstrBot 中配置提供商")
            return
        
        lines = ["📋 **可用的 LLM 服务商**", ""]
        lines.append("将以下 ID 填入插件配置的 `llm_provider_id` 字段：")
        lines.append("")
        
        for i, p in enumerate(providers, 1):
            lines.append(f"  {i}. `{p['id']}`")
            if p.get('name') and p['name'] != p['id']:
                lines.append(f"     └─ {p['name']}")
        
        lines.append("")
        lines.append("💡 留空则使用当前对话模型")
        
        yield event.plain_result("\n".join(lines))

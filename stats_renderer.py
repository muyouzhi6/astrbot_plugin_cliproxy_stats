"""
美观的统计卡片渲染器
使用 Pillow 绘制现代卡片风格的统计图片
"""

import os
from typing import Optional, Dict, Any, List, Tuple
from PIL import Image, ImageDraw, ImageFont
from functools import lru_cache

# 字体路径缓存（避免重复文件系统检查）
_font_path_cache: Optional[str] = None


def _find_font_path() -> Optional[str]:
    """查找可用的字体路径（带缓存）"""
    global _font_path_cache
    if _font_path_cache is not None:
        return _font_path_cache if _font_path_cache else None

    # 获取当前插件目录，用于构建相对路径
    current_dir = os.path.dirname(os.path.abspath(__file__))
    plugins_dir = os.path.dirname(current_dir)  # data/plugins 目录

    font_paths = [
        # AstrBot 自带字体（astrbot_plugin_parser 插件中的中文字体）
        os.path.join(plugins_dir, "astrbot_plugin_parser", "core", "resources", "HYSongYunLangHeiW-1.ttf"),
        # Windows 字体
        "C:/Windows/Fonts/msyh.ttc",      # 微软雅黑
        "C:/Windows/Fonts/msyhbd.ttc",    # 微软雅黑粗体
        "C:/Windows/Fonts/simhei.ttf",    # 黑体
        "C:/Windows/Fonts/simsun.ttc",    # 宋体
        # Linux 字体
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        # macOS 字体
        "/System/Library/Fonts/PingFang.ttc",
    ]

    for path in font_paths:
        if os.path.exists(path):
            _font_path_cache = path
            return path

    _font_path_cache = ""  # 空字符串表示未找到
    return None


@lru_cache(maxsize=32)
def get_font(size: int) -> ImageFont.FreeTypeFont:
    """获取字体，优先使用系统中文字体（带缓存）"""
    font_path = _find_font_path()

    if font_path:
        try:
            return ImageFont.truetype(font_path, size)
        except Exception:
            pass

    # 回退到默认字体
    try:
        return ImageFont.truetype("arial.ttf", size)
    except Exception:
        return ImageFont.load_default()


class StatsCardRenderer:
    """统计卡片渲染器"""

    # 颜色主题
    COLORS = {
        "bg_gradient_start": (30, 41, 59),      # 深蓝灰背景
        "bg_gradient_end": (15, 23, 42),        # 更深的蓝灰
        "card_bg": (51, 65, 85),                # 卡片背景
        "card_border": (71, 85, 105),           # 卡片边框
        "text_primary": (248, 250, 252),        # 主文字 - 亮白
        "text_secondary": (148, 163, 184),      # 次要文字 - 灰白
        "text_muted": (100, 116, 139),          # 更淡的文字
        "accent_blue": (59, 130, 246),          # 强调色 - 蓝
        "accent_green": (34, 197, 94),          # 成功 - 绿
        "accent_yellow": (234, 179, 8),         # 警告 - 黄
        "accent_orange": (249, 115, 22),        # 橙色
        "accent_red": (239, 68, 68),            # 错误 - 红
        "accent_purple": (168, 85, 247),        # 紫色 - Antigravity
        "accent_cyan": (34, 211, 238),          # 青色
        "accent_indigo": (99, 102, 241),        # 靛蓝色 - GeminiCLI
        "progress_bg": (30, 41, 59),            # 进度条背景
        "divider": (71, 85, 105),               # 分割线
    }

    # 凭证类型颜色映射
    PROVIDER_COLORS = {
        "antigravity": (168, 85, 247),   # 紫色
        "gemini": (99, 102, 241),        # 靛蓝色
        "gemini-cli": (99, 102, 241),    # 靛蓝色 (CPA 内部使用的名称)
        "claude": (249, 115, 22),        # 橙色
        "codex": (16, 185, 129),         # 翠绿色
        "iflow": (6, 182, 212),          # 青色
        "qwen": (236, 72, 153),          # 粉色
    }

    # 高清渲染缩放倍数（2x 渲染后缩小，提高清晰度）
    SCALE_FACTOR = 2

    def __init__(self):
        self.padding = 24
        self.card_radius = 16
        self.card_padding = 20

    def _scale(self, value: int) -> int:
        """根据缩放因子调整数值"""
        return value * self.SCALE_FACTOR

    def _downscale_image(self, img: Image.Image) -> Image.Image:
        """将高分辨率图像缩小到目标尺寸，使用高质量抗锯齿"""
        target_width = img.width // self.SCALE_FACTOR
        target_height = img.height // self.SCALE_FACTOR
        return img.resize((target_width, target_height), Image.Resampling.LANCZOS)

    def _create_gradient_bg(self, width: int, height: int) -> Image.Image:
        """创建渐变背景"""
        img = Image.new("RGB", (width, height))
        draw = ImageDraw.Draw(img)

        start = self.COLORS["bg_gradient_start"]
        end = self.COLORS["bg_gradient_end"]

        for y in range(height):
            ratio = y / height
            r = int(start[0] + (end[0] - start[0]) * ratio)
            g = int(start[1] + (end[1] - start[1]) * ratio)
            b = int(start[2] + (end[2] - start[2]) * ratio)
            draw.line([(0, y), (width, y)], fill=(r, g, b))

        return img

    def _draw_rounded_rect(self, draw: ImageDraw.Draw, xy: Tuple[int, int, int, int],
                           radius: int, fill: Tuple[int, int, int],
                           outline: Optional[Tuple[int, int, int]] = None):
        """绘制圆角矩形"""
        x1, y1, x2, y2 = xy

        # 绘制填充
        draw.rectangle([x1 + radius, y1, x2 - radius, y2], fill=fill)
        draw.rectangle([x1, y1 + radius, x2, y2 - radius], fill=fill)
        draw.pieslice([x1, y1, x1 + radius * 2, y1 + radius * 2], 180, 270, fill=fill)
        draw.pieslice([x2 - radius * 2, y1, x2, y1 + radius * 2], 270, 360, fill=fill)
        draw.pieslice([x1, y2 - radius * 2, x1 + radius * 2, y2], 90, 180, fill=fill)
        draw.pieslice([x2 - radius * 2, y2 - radius * 2, x2, y2], 0, 90, fill=fill)

        # 绘制边框
        if outline:
            draw.arc([x1, y1, x1 + radius * 2, y1 + radius * 2], 180, 270, fill=outline)
            draw.arc([x2 - radius * 2, y1, x2, y1 + radius * 2], 270, 360, fill=outline)
            draw.arc([x1, y2 - radius * 2, x1 + radius * 2, y2], 90, 180, fill=outline)
            draw.arc([x2 - radius * 2, y2 - radius * 2, x2, y2], 0, 90, fill=outline)
            draw.line([x1 + radius, y1, x2 - radius, y1], fill=outline)
            draw.line([x1 + radius, y2, x2 - radius, y2], fill=outline)
            draw.line([x1, y1 + radius, x1, y2 - radius], fill=outline)
            draw.line([x2, y1 + radius, x2, y2 - radius], fill=outline)

    def _draw_progress_bar(self, draw: ImageDraw.Draw, x: int, y: int,
                           width: int, height: int, percent: int,
                           color: Tuple[int, int, int]):
        """绘制进度条"""
        # 背景
        radius = height // 2
        self._draw_rounded_rect(draw, (x, y, x + width, y + height),
                                radius, self.COLORS["progress_bg"])

        # 进度
        if percent > 0:
            prog_width = max(height, int(width * percent / 100))
            self._draw_rounded_rect(draw, (x, y, x + prog_width, y + height),
                                    radius, color)

    def _get_text_size(self, draw: ImageDraw.Draw, text: str, font: ImageFont.FreeTypeFont) -> Tuple[int, int]:
        """获取文本尺寸"""
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]

    def render_overview(self, data: Dict[str, Any]) -> Image.Image:
        """渲染总览统计卡片"""
        # 基础尺寸（逻辑像素）
        base_width = 520
        scale = self.SCALE_FACTOR

        # 计算高度
        apis = data.get("apis", [])
        auth_info = data.get("auth_info")

        base_height = 320
        if apis:
            base_height += 40 + len(apis[:8]) * 36
        if auth_info:
            base_height += 60 + len(auth_info.get("providers", [])) * 28
        base_height += 40

        # 实际渲染尺寸（2x）
        width = base_width * scale
        height = base_height * scale
        padding = self.padding * scale

        # 创建背景
        img = self._create_gradient_bg(width, height)
        draw = ImageDraw.Draw(img)

        # 字体（缩放后的尺寸）
        font_title = get_font(24 * scale)
        font_large = get_font(28 * scale)
        font_medium = get_font(16 * scale)
        font_small = get_font(14 * scale)
        font_tiny = get_font(12 * scale)

        y = padding

        # 标题
        title = data.get("title", "CLIProxyAPI 统计")
        draw.text((padding, y), title, fill=self.COLORS["text_primary"], font=font_title)
        y += 40 * scale

        # 统计卡片区域
        card_width = (width - padding * 3) // 2
        card_height = 90 * scale

        # 总请求卡片
        self._draw_rounded_rect(draw,
            (padding, y, padding + card_width, y + card_height),
            12 * scale, self.COLORS["card_bg"], self.COLORS["card_border"])

        draw.text((padding + 16 * scale, y + 12 * scale), "总请求",
                  fill=self.COLORS["text_secondary"], font=font_small)
        draw.text((padding + 16 * scale, y + 34 * scale), str(data.get("total_requests", 0)),
                  fill=self.COLORS["text_primary"], font=font_large)

        # 成功率卡片
        card_x2 = padding * 2 + card_width
        self._draw_rounded_rect(draw,
            (card_x2, y, card_x2 + card_width, y + card_height),
            12 * scale, self.COLORS["card_bg"], self.COLORS["card_border"])

        success_rate = data.get("success_rate", 0)
        rate_color = self.COLORS["accent_green"] if success_rate >= 95 else \
                     self.COLORS["accent_yellow"] if success_rate >= 80 else \
                     self.COLORS["accent_red"]

        draw.text((card_x2 + 16 * scale, y + 12 * scale), "成功率",
                  fill=self.COLORS["text_secondary"], font=font_small)
        draw.text((card_x2 + 16 * scale, y + 34 * scale), f"{success_rate}%",
                  fill=rate_color, font=font_large)

        y += card_height + 16 * scale

        # Token 和成功/失败统计
        self._draw_rounded_rect(draw,
            (padding, y, width - padding, y + 70 * scale),
            12 * scale, self.COLORS["card_bg"], self.COLORS["card_border"])

        # Token
        draw.text((padding + 16 * scale, y + 12 * scale), "总 Token",
                  fill=self.COLORS["text_secondary"], font=font_small)
        draw.text((padding + 16 * scale, y + 32 * scale), data.get("total_tokens", "0"),
                  fill=self.COLORS["accent_cyan"], font=font_medium)

        # 成功/失败
        mid_x = width // 2 + 20 * scale
        draw.text((mid_x, y + 12 * scale), "成功 / 失败",
                  fill=self.COLORS["text_secondary"], font=font_small)
        success_text = f"{data.get('success_count', 0)}"
        fail_text = f" / {data.get('failure_count', 0)}"
        draw.text((mid_x, y + 32 * scale), success_text,
                  fill=self.COLORS["accent_green"], font=font_medium)
        success_width = self._get_text_size(draw, success_text, font_medium)[0]
        draw.text((mid_x + success_width, y + 32 * scale), fail_text,
                  fill=self.COLORS["accent_red"], font=font_medium)

        y += 86 * scale

        # API 列表
        if apis:
            draw.text((padding, y), "各接口统计",
                      fill=self.COLORS["text_secondary"], font=font_small)
            y += 28 * scale

            max_requests = max((api.get("requests", 0) for api in apis), default=1)

            for api in apis[:8]:
                name = api.get("name", "")
                if len(name) > 20:
                    name = name[:18] + "..."
                requests = api.get("requests", 0)
                tokens = api.get("tokens", "0")

                # API 名称
                draw.text((padding + 8 * scale, y), name,
                          fill=self.COLORS["text_primary"], font=font_small)

                # 请求数和 Token（右对齐）
                info_text = f"{requests} 次 / {tokens}"
                info_width = self._get_text_size(draw, info_text, font_tiny)[0]
                draw.text((width - padding - info_width - 8 * scale, y + 2 * scale), info_text,
                          fill=self.COLORS["text_muted"], font=font_tiny)

                # 小进度条
                bar_width = 60 * scale
                bar_x = width - padding - info_width - bar_width - 20 * scale
                percent = int(requests / max_requests * 100) if max_requests > 0 else 0
                self._draw_progress_bar(draw, bar_x, y + 6 * scale, bar_width, 8 * scale, percent,
                                        self.COLORS["accent_blue"])

                y += 32 * scale

            y += 8 * scale

        # OAuth 账号信息
        if auth_info:
            draw.text((padding, y), f"OAuth 账号 ({auth_info['active']}/{auth_info['total']} 可用)",
                      fill=self.COLORS["text_secondary"], font=font_small)
            y += 28 * scale

            for provider in auth_info.get("providers", []):
                name = provider.get("name", "")
                active = provider.get("active", 0)
                total = provider.get("total", 0)

                # 状态指示
                status_color = self.COLORS["accent_green"] if active == total else \
                               self.COLORS["accent_yellow"] if active > 0 else \
                               self.COLORS["accent_red"]

                draw.ellipse([padding + 8 * scale, y + 4 * scale, padding + 16 * scale, y + 12 * scale],
                            fill=status_color)
                draw.text((padding + 24 * scale, y), f"{name}: {active}/{total}",
                          fill=self.COLORS["text_primary"], font=font_small)
                y += 26 * scale

        # 缩小到目标尺寸
        return self._downscale_image(img)

    def render_today(self, data: Dict[str, Any]) -> Image.Image:
        """渲染今日统计卡片"""
        base_width = 520
        scale = self.SCALE_FACTOR

        model_stats = data.get("model_stats") or []
        time_slots = data.get("time_slots") or []

        base_height = 200
        if model_stats:
            base_height += 40 + len(model_stats[:10]) * 34
        if time_slots:
            base_height += 100  # 增加时段分布的高度
        base_height += 40

        width = base_width * scale
        height = base_height * scale
        padding = self.padding * scale

        img = self._create_gradient_bg(width, height)
        draw = ImageDraw.Draw(img)

        font_title = get_font(24 * scale)
        font_large = get_font(32 * scale)
        font_medium = get_font(16 * scale)
        font_small = get_font(14 * scale)
        font_tiny = get_font(12 * scale)

        y = padding

        # 标题
        draw.text((padding, y), data.get("title", "今日统计"),
                  fill=self.COLORS["text_primary"], font=font_title)
        draw.text((padding, y + 32 * scale), data.get("subtitle", ""),
                  fill=self.COLORS["text_secondary"], font=font_small)
        y += 60 * scale

        # 今日统计卡片
        card_width = (width - padding * 3) // 2

        # 请求数
        self._draw_rounded_rect(draw,
            (padding, y, padding + card_width, y + 80 * scale),
            12 * scale, self.COLORS["card_bg"], self.COLORS["card_border"])
        draw.text((padding + 16 * scale, y + 12 * scale), "今日请求",
                  fill=self.COLORS["text_secondary"], font=font_small)
        draw.text((padding + 16 * scale, y + 34 * scale), str(data.get("today_requests", 0)),
                  fill=self.COLORS["accent_purple"], font=font_large)

        # Token
        card_x2 = padding * 2 + card_width
        self._draw_rounded_rect(draw,
            (card_x2, y, card_x2 + card_width, y + 80 * scale),
            12 * scale, self.COLORS["card_bg"], self.COLORS["card_border"])
        draw.text((card_x2 + 16 * scale, y + 12 * scale), "今日 Token",
                  fill=self.COLORS["text_secondary"], font=font_small)
        draw.text((card_x2 + 16 * scale, y + 34 * scale), data.get("today_tokens", "0"),
                  fill=self.COLORS["accent_cyan"], font=font_large)

        y += 96 * scale

        # 模型统计
        if model_stats:
            draw.text((padding, y), "各模型详情",
                      fill=self.COLORS["text_secondary"], font=font_small)
            y += 28 * scale

            max_requests = max((m.get("requests", 0) for m in model_stats), default=1)

            for model in model_stats[:10]:
                name = model.get("name", "")
                if len(name) > 22:
                    name = name[:20] + "..."
                requests = model.get("requests", 0)
                tokens = model.get("tokens", "0")
                failed = model.get("failed", 0)

                # 模型名称
                draw.text((padding + 8 * scale, y), name,
                          fill=self.COLORS["text_primary"], font=font_small)

                # 统计信息
                info_parts = [f"{requests} 次"]
                if failed > 0:
                    info_parts.append(f"失败 {failed}")
                info_parts.append(tokens)
                info_text = " / ".join(info_parts)

                info_width = self._get_text_size(draw, info_text, font_tiny)[0]

                # 失败高亮
                if failed > 0:
                    draw.text((width - padding - info_width - 8 * scale, y + 2 * scale), info_text,
                              fill=self.COLORS["accent_orange"], font=font_tiny)
                else:
                    draw.text((width - padding - info_width - 8 * scale, y + 2 * scale), info_text,
                              fill=self.COLORS["text_muted"], font=font_tiny)

                # 进度条
                bar_width = 50 * scale
                bar_x = width - padding - info_width - bar_width - 20 * scale
                percent = int(requests / max_requests * 100) if max_requests > 0 else 0
                color = self.COLORS["accent_orange"] if failed > 0 else self.COLORS["accent_purple"]
                self._draw_progress_bar(draw, bar_x, y + 6 * scale, bar_width, 8 * scale, percent, color)

                y += 32 * scale

            y += 8 * scale

        # 时段分布
        if time_slots and sum(s.get("count", 0) for s in time_slots) > 0:
            draw.text((padding, y), "时段分布",
                      fill=self.COLORS["text_secondary"], font=font_small)
            y += 28 * scale

            slot_width = (width - padding * 2 - 30 * scale) // 4
            max_count = max((s.get("count", 0) for s in time_slots), default=1)

            slot_colors = [
                self.COLORS["accent_blue"],
                self.COLORS["accent_cyan"],
                self.COLORS["accent_purple"],
                self.COLORS["accent_orange"]
            ]

            for i, slot in enumerate(time_slots):
                x = padding + i * (slot_width + 10 * scale)
                count = slot.get("count", 0)
                label = slot.get("label", "")

                # 柱状图
                bar_height = 50 * scale
                if max_count > 0:
                    fill_height = int(bar_height * count / max_count)
                else:
                    fill_height = 0

                # 背景
                self._draw_rounded_rect(draw,
                    (x, y, x + slot_width, y + bar_height),
                    6 * scale, self.COLORS["progress_bg"])

                # 填充
                if fill_height > 0:
                    fill_radius = min(6 * scale, fill_height // 2)
                    if fill_height < 4 * scale:
                        draw.rectangle(
                            [x, y + bar_height - fill_height, x + slot_width, y + bar_height],
                            fill=slot_colors[i])
                    else:
                        self._draw_rounded_rect(draw,
                            (x, y + bar_height - fill_height, x + slot_width, y + bar_height),
                            fill_radius, slot_colors[i])

                # 标签和数值
                draw.text((x + 4 * scale, y + bar_height + 6 * scale), label[:4],
                          fill=self.COLORS["text_muted"], font=font_tiny)
                count_text = str(count)
                count_width = self._get_text_size(draw, count_text, font_tiny)[0]
                draw.text((x + slot_width - count_width - 4 * scale, y + bar_height + 6 * scale),
                          count_text, fill=slot_colors[i], font=font_tiny)

        return self._downscale_image(img)

    def render_quota(self, data: Dict[str, Any]) -> Image.Image:
        """渲染配额状态卡片（支持多凭证类型）"""
        base_width = 580  # 加宽卡片以容纳凭证标签
        scale = self.SCALE_FACTOR

        accounts = data.get("accounts", [])

        # 按凭证类型分组账号
        provider_accounts: Dict[str, List[Dict[str, Any]]] = {}
        for account in accounts:
            provider = account.get("provider", "unknown")
            if provider not in provider_accounts:
                provider_accounts[provider] = []
            provider_accounts[provider].append(account)

        # 计算高度
        base_height = 80  # 标题区域
        for provider, accs in provider_accounts.items():
            base_height += 40  # 凭证类型标题
            for account in accs:
                base_height += 54  # 账号头部（含凭证标签）
                if account.get("error"):
                    base_height += 30
                else:
                    base_height += len(account.get("quotas", [])) * 52
                base_height += 12
            base_height += 16  # 分组间距
        base_height += 50  # 底部提示

        width = base_width * scale
        height = base_height * scale
        padding = self.padding * scale

        img = self._create_gradient_bg(width, height)
        draw = ImageDraw.Draw(img)

        font_title = get_font(24 * scale)
        font_section = get_font(18 * scale)
        font_medium = get_font(16 * scale)
        font_small = get_font(14 * scale)
        font_tiny = get_font(12 * scale)
        font_badge = get_font(10 * scale)

        y = padding

        # 标题
        draw.text((padding, y), data.get("title", "OAuth 配额状态"),
                  fill=self.COLORS["text_primary"], font=font_title)

        # 副标题（凭证统计摘要 + 查询时间）
        subtitle = data.get("subtitle", "")
        query_time = data.get("query_time", "")
        if query_time:
            subtitle = f"{subtitle}  ⏱️ {query_time}" if subtitle else f"⏱️ {query_time}"
        if subtitle:
            draw.text((padding, y + 34 * scale), subtitle,
                      fill=self.COLORS["text_secondary"], font=font_small)
        y += 60 * scale

        # 按凭证类型渲染
        for provider, accs in provider_accounts.items():
            provider_color = self.PROVIDER_COLORS.get(provider, self.COLORS["accent_blue"])
            provider_name = accs[0].get("provider_name", provider.title()) if accs else provider.title()
            provider_icon = accs[0].get("provider_icon", "📦") if accs else "📦"

            # 凭证类型分割线和标题
            draw.line([(padding, y), (width - padding, y)], fill=provider_color, width=2 * scale)
            section_title = f"{provider_icon} {provider_name}"
            draw.text((padding, y + 8 * scale), section_title,
                      fill=provider_color, font=font_section)
            y += 36 * scale

            for account in accs:
                # 账号卡片
                quotas = account.get("quotas", [])
                card_height = 48 * scale if account.get("error") else (48 + len(quotas) * 50) * scale

                # 绘制卡片边框，使用凭证类型颜色
                self._draw_rounded_rect(draw,
                    (padding, y, width - padding, y + card_height),
                    12 * scale, self.COLORS["card_bg"], provider_color)

                # 账号头部
                icon = account.get("icon", "")
                email = account.get("email", "")

                # 状态指示点
                icon_color = self.COLORS["accent_green"] if icon == "✅" else self.COLORS["accent_red"]
                draw.ellipse([padding + 16 * scale, y + 16 * scale, padding + 28 * scale, y + 28 * scale],
                            fill=icon_color)

                # 邮箱/名称
                draw.text((padding + 38 * scale, y + 14 * scale), email,
                          fill=self.COLORS["text_primary"], font=font_medium)

                y += 44 * scale

                if account.get("error"):
                    draw.text((padding + 38 * scale, y - 18 * scale), f"⚠️ {account['error']}",
                              fill=self.COLORS["accent_yellow"], font=font_small)
                else:
                    for quota in quotas:
                        label = quota.get("label", "")
                        percent = quota.get("percent", 0)
                        reset_time = quota.get("reset_time", "")

                        # 确定颜色
                        if percent >= 80:
                            bar_color = self.COLORS["accent_green"]
                        elif percent >= 50:
                            bar_color = self.COLORS["accent_yellow"]
                        elif percent >= 20:
                            bar_color = self.COLORS["accent_orange"]
                        else:
                            bar_color = self.COLORS["accent_red"]

                        # 第一行：标签 + 进度条 + 百分比
                        draw.text((padding + 20 * scale, y), label,
                                  fill=self.COLORS["text_secondary"], font=font_small)

                        # 进度条（位置调整）
                        bar_x = padding + 150 * scale
                        bar_width_val = 200 * scale
                        self._draw_progress_bar(draw, bar_x, y + 4 * scale, bar_width_val, 14 * scale, percent, bar_color)

                        # 百分比（紧跟进度条后面）
                        percent_text = f"{percent}%"
                        draw.text((bar_x + bar_width_val + 12 * scale, y), percent_text,
                                  fill=bar_color, font=font_small)

                        # 第二行：刷新时间（右对齐，在进度条下方）
                        reset_text = f"刷新: {reset_time}"
                        reset_width = self._get_text_size(draw, reset_text, font_tiny)[0]
                        draw.text((width - padding - reset_width - 20 * scale, y + 22 * scale),
                                  reset_text, fill=self.COLORS["text_muted"], font=font_tiny)

                        y += 48 * scale

                y += 14 * scale

            y += 8 * scale  # 凭证类型分组间距

        # 底部提示
        tip_text = "💡 配额每日自动刷新，百分比为剩余额度"
        draw.text((padding, y), tip_text,
                  fill=self.COLORS["text_muted"], font=font_small)

        return self._downscale_image(img)

    def render(self, data: Dict[str, Any]) -> Optional[Image.Image]:
        """根据数据类型渲染对应的卡片"""
        stats_type = data.get("stats_type", "")

        if stats_type == "overview":
            return self.render_overview(data)
        elif stats_type == "today":
            return self.render_today(data)
        elif stats_type == "quota":
            return self.render_quota(data)

        return None

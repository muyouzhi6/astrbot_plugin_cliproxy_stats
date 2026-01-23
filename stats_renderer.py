"""
美观的统计卡片渲染器
使用 Pillow 绘制现代卡片风格的统计图片
支持高分辨率渲染和 Token 分解显示
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


@lru_cache(maxsize=64)
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
    """统计卡片渲染器 - 增强版"""

    # 现代配色主题
    COLORS = {
        "bg_gradient_start": (24, 32, 48),       # 深蓝灰背景
        "bg_gradient_end": (12, 18, 32),         # 更深的蓝灰
        "card_bg": (38, 50, 72),                 # 卡片背景
        "card_bg_light": (48, 62, 88),           # 浅卡片背景
        "card_border": (58, 75, 100),            # 卡片边框
        "text_primary": (248, 250, 252),         # 主文字 - 亮白
        "text_secondary": (156, 172, 196),       # 次要文字 - 灰白
        "text_muted": (108, 126, 152),           # 更淡的文字
        "accent_blue": (66, 138, 255),           # 强调色 - 蓝
        "accent_green": (52, 211, 120),          # 成功 - 绿
        "accent_yellow": (250, 190, 40),         # 警告 - 黄
        "accent_orange": (255, 128, 48),         # 橙色
        "accent_red": (248, 80, 80),             # 错误 - 红
        "accent_purple": (178, 102, 255),        # 紫色 - Antigravity
        "accent_cyan": (56, 220, 248),           # 青色
        "accent_indigo": (108, 112, 255),        # 靛蓝色 - GeminiCLI
        "accent_pink": (248, 96, 168),           # 粉色
        "progress_bg": (28, 36, 52),             # 进度条背景
        "divider": (58, 75, 100),                # 分割线
    }

    # 凭证类型颜色映射
    PROVIDER_COLORS = {
        "antigravity": (178, 102, 255),   # 紫色
        "gemini": (108, 112, 255),        # 靛蓝色
        "gemini-cli": (108, 112, 255),    # 靛蓝色
        "claude": (255, 128, 48),         # 橙色
        "codex": (52, 200, 140),          # 翠绿色
        "iflow": (56, 200, 224),          # 青色
        "qwen": (248, 96, 168),           # 粉色
    }

    def __init__(self, high_res: bool = True):
        """初始化渲染器
        
        Args:
            high_res: 是否启用高分辨率渲染（3x），否则使用 2x
        """
        self.SCALE_FACTOR = 3 if high_res else 2
        self.padding = 28
        self.card_radius = 16
        self.card_padding = 24

    def _scale(self, value: int) -> int:
        """根据缩放因子调整数值"""
        return value * self.SCALE_FACTOR

    def _downscale_image(self, img: Image.Image) -> Image.Image:
        """将高分辨率图像缩小到目标尺寸，使用高质量抗锯齿"""
        target_width = img.width // self.SCALE_FACTOR
        target_height = img.height // self.SCALE_FACTOR
        return img.resize((target_width, target_height), Image.Resampling.LANCZOS)

    def _crop_to_content(self, img: Image.Image, final_y: int, padding: int = 0) -> Image.Image:
        """裁剪图片到实际内容高度，移除底部空白
        
        Args:
            img: 原始图片
            final_y: 内容实际结束的 y 坐标（已缩放）
            padding: 底部额外留白（已缩放）
        
        Returns:
            裁剪后的图片
        """
        # 计算裁剪高度（内容高度 + 底部留白）
        crop_height = final_y + padding
        # 确保不超过原图高度
        crop_height = min(crop_height, img.height)
        # 确保最小高度
        crop_height = max(crop_height, 100 * self.SCALE_FACTOR)
        
        if crop_height < img.height:
            return img.crop((0, 0, img.width, crop_height))
        return img

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
                           outline: Optional[Tuple[int, int, int]] = None,
                           outline_width: int = 1):
        """绘制圆角矩形"""
        x1, y1, x2, y2 = xy
        
        # 确保半径不超过矩形的一半
        max_radius = min((x2 - x1) // 2, (y2 - y1) // 2)
        radius = min(radius, max_radius)
        if radius < 1:
            draw.rectangle([x1, y1, x2, y2], fill=fill, outline=outline)
            return

        # 绘制填充
        draw.rectangle([x1 + radius, y1, x2 - radius, y2], fill=fill)
        draw.rectangle([x1, y1 + radius, x2, y2 - radius], fill=fill)
        draw.pieslice([x1, y1, x1 + radius * 2, y1 + radius * 2], 180, 270, fill=fill)
        draw.pieslice([x2 - radius * 2, y1, x2, y1 + radius * 2], 270, 360, fill=fill)
        draw.pieslice([x1, y2 - radius * 2, x1 + radius * 2, y2], 90, 180, fill=fill)
        draw.pieslice([x2 - radius * 2, y2 - radius * 2, x2, y2], 0, 90, fill=fill)

        # 绘制边框
        if outline:
            draw.arc([x1, y1, x1 + radius * 2, y1 + radius * 2], 180, 270, fill=outline, width=outline_width)
            draw.arc([x2 - radius * 2, y1, x2, y1 + radius * 2], 270, 360, fill=outline, width=outline_width)
            draw.arc([x1, y2 - radius * 2, x1 + radius * 2, y2], 90, 180, fill=outline, width=outline_width)
            draw.arc([x2 - radius * 2, y2 - radius * 2, x2, y2], 0, 90, fill=outline, width=outline_width)
            draw.line([x1 + radius, y1, x2 - radius, y1], fill=outline, width=outline_width)
            draw.line([x1 + radius, y2, x2 - radius, y2], fill=outline, width=outline_width)
            draw.line([x1, y1 + radius, x1, y2 - radius], fill=outline, width=outline_width)
            draw.line([x2, y1 + radius, x2, y2 - radius], fill=outline, width=outline_width)

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
        base_height += 50  # 包含查询时间显示空间

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

        # 显示查询时间
        query_time = data.get("query_time", "")
        if query_time:
            y += 8 * scale
            time_text = f"🔄 查询时间: {query_time}"
            time_width = self._get_text_size(draw, time_text, font_small)[0]
            draw.text((width - padding - time_width, y),
                      time_text, fill=self.COLORS["accent_cyan"], font=font_small)
            y += 20 * scale

        # 裁剪到实际内容高度
        img = self._crop_to_content(img, y, padding=16 * scale)
        
        # 缩小到目标尺寸
        return self._downscale_image(img)

    def render_today(self, data: Dict[str, Any]) -> Image.Image:
        """渲染今日统计卡片（增强版：支持 Token 分解和凭证统计）"""
        base_width = 680  # 加宽以容纳更多信息
        scale = self.SCALE_FACTOR

        model_stats = data.get("model_stats") or []
        time_slots = data.get("time_slots") or []
        auth_stats = data.get("auth_stats") or []
        token_breakdown = data.get("token_breakdown") or {}

        # 计算高度
        base_height = 240  # 基础区域（标题 + 统计卡片）
        if token_breakdown:
            base_height += 80  # Token 分解区域
        if model_stats:
            base_height += 50 + min(len(model_stats), 15) * 36
        if auth_stats:
            base_height += 50 + min(len(auth_stats), 8) * 32
        if time_slots:
            base_height += 120
        base_height += 60  # 底部空间

        width = base_width * scale
        height = base_height * scale
        padding = self.padding * scale

        img = self._create_gradient_bg(width, height)
        draw = ImageDraw.Draw(img)

        font_title = get_font(26 * scale)
        font_large = get_font(36 * scale)
        font_medium = get_font(18 * scale)
        font_small = get_font(15 * scale)
        font_tiny = get_font(13 * scale)

        y = padding

        # 标题
        draw.text((padding, y), data.get("title", "今日统计"),
                  fill=self.COLORS["text_primary"], font=font_title)
        
        # 成功率标签（右上角）
        success_rate = data.get("success_rate", 100)
        rate_color = self.COLORS["accent_green"] if success_rate >= 95 else \
                     self.COLORS["accent_yellow"] if success_rate >= 80 else \
                     self.COLORS["accent_red"]
        rate_text = f"成功率 {success_rate}%"
        rate_width = self._get_text_size(draw, rate_text, font_small)[0]
        draw.text((width - padding - rate_width, y + 8 * scale), rate_text,
                  fill=rate_color, font=font_small)
        
        draw.text((padding, y + 36 * scale), data.get("subtitle", ""),
                  fill=self.COLORS["text_secondary"], font=font_small)
        y += 70 * scale

        # 主统计卡片（3列：请求数、Token、成功率）
        card_width = (width - padding * 4) // 3
        card_height = 90 * scale

        # 请求数
        self._draw_rounded_rect(draw,
            (padding, y, padding + card_width, y + card_height),
            14 * scale, self.COLORS["card_bg"], self.COLORS["card_border"])
        draw.text((padding + 18 * scale, y + 14 * scale), "今日请求",
                  fill=self.COLORS["text_secondary"], font=font_small)
        draw.text((padding + 18 * scale, y + 40 * scale), str(data.get("today_requests", 0)),
                  fill=self.COLORS["accent_purple"], font=font_large)

        # Token
        card_x2 = padding * 2 + card_width
        self._draw_rounded_rect(draw,
            (card_x2, y, card_x2 + card_width, y + card_height),
            14 * scale, self.COLORS["card_bg"], self.COLORS["card_border"])
        draw.text((card_x2 + 18 * scale, y + 14 * scale), "今日 Token",
                  fill=self.COLORS["text_secondary"], font=font_small)
        draw.text((card_x2 + 18 * scale, y + 40 * scale), data.get("today_tokens", "0"),
                  fill=self.COLORS["accent_cyan"], font=font_large)

        # 模型数
        card_x3 = padding * 3 + card_width * 2
        self._draw_rounded_rect(draw,
            (card_x3, y, card_x3 + card_width, y + card_height),
            14 * scale, self.COLORS["card_bg"], self.COLORS["card_border"])
        draw.text((card_x3 + 18 * scale, y + 14 * scale), "活跃模型",
                  fill=self.COLORS["text_secondary"], font=font_small)
        draw.text((card_x3 + 18 * scale, y + 40 * scale), str(len(model_stats)),
                  fill=self.COLORS["accent_blue"], font=font_large)

        y += card_height + 20 * scale

        # Token 分解显示
        if token_breakdown:
            draw.text((padding, y), "Token 分解",
                      fill=self.COLORS["text_secondary"], font=font_small)
            y += 28 * scale

            # 4个小卡片显示 input/output/reasoning/cached
            token_items = [
                ("输入", token_breakdown.get("input", "0"), self.COLORS["accent_blue"]),
                ("输出", token_breakdown.get("output", "0"), self.COLORS["accent_green"]),
                ("推理", token_breakdown.get("reasoning", "0"), self.COLORS["accent_purple"]),
                ("缓存", token_breakdown.get("cached", "0"), self.COLORS["accent_cyan"]),
            ]
            
            item_width = (width - padding * 5) // 4
            for i, (label, value, color) in enumerate(token_items):
                x = padding + i * (item_width + padding)
                self._draw_rounded_rect(draw,
                    (x, y, x + item_width, y + 48 * scale),
                    10 * scale, self.COLORS["card_bg_light"])
                draw.text((x + 12 * scale, y + 8 * scale), label,
                          fill=self.COLORS["text_muted"], font=font_tiny)
                draw.text((x + 12 * scale, y + 26 * scale), value,
                          fill=color, font=font_small)
            
            y += 64 * scale

        # 模型统计
        if model_stats:
            draw.text((padding, y), "各模型详情",
                      fill=self.COLORS["text_secondary"], font=font_small)
            y += 30 * scale

            max_requests = max((m.get("requests", 0) for m in model_stats), default=1)

            for model in model_stats[:15]:
                name = model.get("name", "")
                if len(name) > 28:
                    name = name[:26] + "..."
                requests = model.get("requests", 0)
                tokens = model.get("tokens", "0")
                failed = model.get("failed", 0)

                # 模型名称
                draw.text((padding + 10 * scale, y), name,
                          fill=self.COLORS["text_primary"], font=font_small)

                # 统计信息
                info_parts = [f"{requests} 次"]
                if failed > 0:
                    info_parts.append(f"失败 {failed}")
                info_parts.append(tokens)
                info_text = " | ".join(info_parts)

                info_width = self._get_text_size(draw, info_text, font_tiny)[0]

                # 失败高亮
                text_color = self.COLORS["accent_orange"] if failed > 0 else self.COLORS["text_muted"]
                draw.text((width - padding - info_width - 10 * scale, y + 3 * scale), info_text,
                          fill=text_color, font=font_tiny)

                # 进度条
                bar_width = 60 * scale
                bar_x = width - padding - info_width - bar_width - 24 * scale
                percent = int(requests / max_requests * 100) if max_requests > 0 else 0
                color = self.COLORS["accent_orange"] if failed > 0 else self.COLORS["accent_purple"]
                self._draw_progress_bar(draw, bar_x, y + 6 * scale, bar_width, 10 * scale, percent, color)

                y += 34 * scale

            y += 12 * scale

        # 凭证使用统计
        if auth_stats:
            draw.text((padding, y), "凭证使用",
                      fill=self.COLORS["text_secondary"], font=font_small)
            y += 28 * scale

            for auth in auth_stats[:8]:
                auth_id = auth.get("auth_index", "unknown")
                if len(auth_id) > 20:
                    auth_id = auth_id[:18] + "..."
                requests = auth.get("requests", 0)
                tokens = auth.get("tokens", "0")
                failed = auth.get("failed", 0)

                # 凭证标识
                draw.text((padding + 10 * scale, y), auth_id,
                          fill=self.COLORS["text_primary"], font=font_tiny)

                # 统计
                info_text = f"{requests} 次 | {tokens}"
                if failed > 0:
                    info_text += f" | 失败 {failed}"
                info_width = self._get_text_size(draw, info_text, font_tiny)[0]
                text_color = self.COLORS["accent_orange"] if failed > 0 else self.COLORS["text_muted"]
                draw.text((width - padding - info_width - 10 * scale, y + 2 * scale), info_text,
                          fill=text_color, font=font_tiny)

                y += 30 * scale

            y += 10 * scale

        # 时段分布
        if time_slots and sum(s.get("count", 0) for s in time_slots) > 0:
            draw.text((padding, y), "时段分布",
                      fill=self.COLORS["text_secondary"], font=font_small)
            y += 30 * scale

            slot_width = (width - padding * 2 - 36 * scale) // 4
            max_count = max((s.get("count", 0) for s in time_slots), default=1)
            bar_height = 60 * scale

            slot_colors = [
                self.COLORS["accent_blue"],
                self.COLORS["accent_cyan"],
                self.COLORS["accent_purple"],
                self.COLORS["accent_orange"]
            ]

            for i, slot in enumerate(time_slots):
                x = padding + i * (slot_width + 12 * scale)
                count = slot.get("count", 0)
                label = slot.get("label", "")

                # 柱状图
                if max_count > 0:
                    fill_height = int(bar_height * count / max_count)
                else:
                    fill_height = 0

                # 背景
                self._draw_rounded_rect(draw,
                    (x, y, x + slot_width, y + bar_height),
                    8 * scale, self.COLORS["progress_bg"])

                # 填充
                if fill_height > 0:
                    fill_radius = min(8 * scale, fill_height // 2)
                    if fill_height < 6 * scale:
                        draw.rectangle(
                            [x, y + bar_height - fill_height, x + slot_width, y + bar_height],
                            fill=slot_colors[i])
                    else:
                        self._draw_rounded_rect(draw,
                            (x, y + bar_height - fill_height, x + slot_width, y + bar_height),
                            fill_radius, slot_colors[i])

                # 标签和数值
                draw.text((x + 6 * scale, y + bar_height + 8 * scale), label[:4],
                          fill=self.COLORS["text_muted"], font=font_tiny)
                count_text = str(count)
                count_width = self._get_text_size(draw, count_text, font_tiny)[0]
                draw.text((x + slot_width - count_width - 6 * scale, y + bar_height + 8 * scale),
                          count_text, fill=slot_colors[i], font=font_tiny)

            y += bar_height + 32 * scale

        # 显示查询时间
        query_time = data.get("query_time", "")
        if query_time:
            time_text = f"🔄 {query_time}"
            time_width = self._get_text_size(draw, time_text, font_small)[0]
            draw.text((width - padding - time_width, y),
                      time_text, fill=self.COLORS["accent_cyan"], font=font_small)
            y += 20 * scale

        # 裁剪到实际内容高度
        img = self._crop_to_content(img, y, padding=16 * scale)

        return self._downscale_image(img)

    def render_quota(self, data: Dict[str, Any], max_render_count: Optional[Dict[str, int]] = None) -> Image.Image:
        """渲染配额状态卡片（两列布局，更宽更短）
        
        Args:
            data: 配额数据，可包含 max_render_count 字段
            max_render_count: 各 provider 最大渲染数量，如 {"antigravity": 5, "gemini-cli": 10, "codex": 10}
                             0 或不存在表示不限制。也可以从 data["max_render_count"] 读取。
        """
        base_width = 880  # 加宽以支持两列
        scale = self.SCALE_FACTOR
        
        accounts = data.get("accounts", [])
        
        # 优先使用参数传入的配置，其次从 data 中读取
        if max_render_count is None:
            max_render_count = data.get("max_render_count")
        
        # 计算每个账号需要的高度
        def calc_account_height(account: Dict[str, Any]) -> int:
            if account.get("error"):
                return 70  # 账号头部 + 错误信息
            quotas = account.get("quotas", [])
            # 头部 40 + 每个配额 44（标签一行 + 进度条一行）
            return 48 + len(quotas) * 44
        
        # 按凭证类型分组
        provider_accounts: Dict[str, List[Dict[str, Any]]] = {}
        for account in accounts:
            provider = account.get("provider", "unknown")
            if provider not in provider_accounts:
                provider_accounts[provider] = []
            provider_accounts[provider].append(account)
        
        # 应用截断限制并记录截断数量
        truncated_counts: Dict[str, int] = {}
        if max_render_count:
            for provider in provider_accounts:
                # 使用标准化的 key: gemini -> gemini-cli
                config_key = "gemini-cli" if provider == "gemini" else provider
                max_count = max_render_count.get(config_key, 0)
                if max_count > 0 and len(provider_accounts[provider]) > max_count:
                    truncated_counts[provider] = len(provider_accounts[provider]) - max_count
                    provider_accounts[provider] = provider_accounts[provider][:max_count]
        
        # 计算总高度（两列布局）
        base_height = 90  # 标题区域
        for provider, accs in provider_accounts.items():
            base_height += 44  # 凭证类型标题
            # 两列布局：每两个账号一行
            row_heights = []
            for i in range(0, len(accs), 2):
                left_height = calc_account_height(accs[i])
                right_height = calc_account_height(accs[i + 1]) if i + 1 < len(accs) else 0
                row_heights.append(max(left_height, right_height) + 16)  # 行间距
            base_height += sum(row_heights)
            # 如果有截断，添加提示行高度
            if provider in truncated_counts:
                base_height += 32
            base_height += 12  # 分组间距
        base_height += 50  # 底部提示
        
        width = base_width * scale
        height = base_height * scale
        padding = self.padding * scale
        card_gap = 16 * scale  # 卡片间距
        card_width = (width - padding * 2 - card_gap) // 2  # 每个卡片宽度
        
        img = self._create_gradient_bg(width, height)
        draw = ImageDraw.Draw(img)
        
        font_title = get_font(24 * scale)
        font_section = get_font(17 * scale)
        font_medium = get_font(15 * scale)
        font_small = get_font(13 * scale)
        font_tiny = get_font(11 * scale)
        
        y = padding
        
        # 标题
        draw.text((padding, y), data.get("title", "OAuth 配额状态"),
                  fill=self.COLORS["text_primary"], font=font_title)
        
        # 副标题 + 查询时间
        subtitle = data.get("subtitle", "")
        query_time = data.get("query_time", "")
        if query_time:
            time_text = f"⏱️ {query_time}"
            time_width = self._get_text_size(draw, time_text, font_small)[0]
            draw.text((width - padding - time_width, y + 6 * scale),
                      time_text, fill=self.COLORS["accent_cyan"], font=font_small)
        if subtitle:
            draw.text((padding, y + 36 * scale), subtitle,
                      fill=self.COLORS["text_secondary"], font=font_small)
        y += 70 * scale
        
        # 按凭证类型渲染
        for provider, accs in provider_accounts.items():
            provider_color = self.PROVIDER_COLORS.get(provider, self.COLORS["accent_blue"])
            provider_name = accs[0].get("provider_name", provider.title()) if accs else provider.title()
            provider_icon = accs[0].get("provider_icon", "📦") if accs else "📦"
            
            # 凭证类型分割线和标题
            draw.line([(padding, y), (width - padding, y)], fill=provider_color, width=2 * scale)
            section_title = f"{provider_icon} {provider_name} ({len(accs)})"
            draw.text((padding, y + 10 * scale), section_title,
                      fill=provider_color, font=font_section)
            y += 40 * scale
            
            # 两列布局渲染账号
            for i in range(0, len(accs), 2):
                left_account = accs[i]
                right_account = accs[i + 1] if i + 1 < len(accs) else None
                
                left_height = calc_account_height(left_account) * scale
                right_height = (calc_account_height(right_account) * scale) if right_account else 0
                row_height = max(left_height, right_height)
                
                # 渲染左侧卡片
                self._render_account_card(draw, padding, y, card_width, left_height,
                                         left_account, provider_color, scale,
                                         font_medium, font_small, font_tiny)
                
                # 渲染右侧卡片
                if right_account:
                    right_x = padding + card_width + card_gap
                    self._render_account_card(draw, right_x, y, card_width, right_height,
                                             right_account, provider_color, scale,
                                             font_medium, font_small, font_tiny)
                
                y += row_height + 14 * scale
            
            # 如果有截断，显示提示信息
            if provider in truncated_counts:
                truncated_text = f"⋯ 还有 {truncated_counts[provider]} 个 {provider_name} 账号未显示"
                draw.text((padding, y), truncated_text,
                         fill=self.COLORS["text_muted"], font=font_small)
                y += 28 * scale
            
            y += 8 * scale  # 凭证类型分组间距
        
        # 底部提示
        tip_text = "💡 配额每日自动刷新，百分比为剩余额度"
        draw.text((padding, y), tip_text,
                  fill=self.COLORS["text_muted"], font=font_small)
        
        # 计算实际内容结束位置并裁剪
        final_y = y + 24 * scale  # 提示文字高度
        img = self._crop_to_content(img, final_y, padding=16 * scale)
        
        return self._downscale_image(img)
    
    def _render_account_card(self, draw: ImageDraw.Draw, x: int, y: int, 
                             card_width: int, card_height: int,
                             account: Dict[str, Any], provider_color: Tuple[int, int, int],
                             scale: int, font_medium, font_small, font_tiny):
        """渲染单个账号卡片"""
        card_padding = 14 * scale
        
        # 绘制卡片背景
        self._draw_rounded_rect(draw,
            (x, y, x + card_width, y + card_height),
            10 * scale, self.COLORS["card_bg"], self.COLORS["card_border"])
        
        # 账号头部
        icon = account.get("icon", "")
        email = account.get("email", "")
        
        # 状态指示点
        icon_color = self.COLORS["accent_green"] if icon == "✅" else self.COLORS["accent_red"]
        draw.ellipse([x + card_padding, y + card_padding + 2 * scale, 
                      x + card_padding + 10 * scale, y + card_padding + 12 * scale],
                    fill=icon_color)
        
        # 邮箱/名称（截断过长的文本）
        max_email_width = card_width - card_padding * 3 - 10 * scale
        display_email = email
        email_width = self._get_text_size(draw, display_email, font_medium)[0]
        while email_width > max_email_width and len(display_email) > 10:
            display_email = display_email[:-4] + "..."
            email_width = self._get_text_size(draw, display_email, font_medium)[0]
        
        draw.text((x + card_padding + 16 * scale, y + card_padding),
                  display_email, fill=self.COLORS["text_primary"], font=font_medium)
        
        inner_y = y + card_padding + 28 * scale
        
        if account.get("error"):
            draw.text((x + card_padding, inner_y), f"⚠️ {account['error']}",
                      fill=self.COLORS["accent_yellow"], font=font_small)
        else:
            quotas = account.get("quotas", [])
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
                
                # 第一行：标签（完整显示，不被挡住）
                # 截断过长的标签
                max_label_width = card_width - card_padding * 2 - 80 * scale
                display_label = label
                label_width = self._get_text_size(draw, display_label, font_small)[0]
                while label_width > max_label_width and len(display_label) > 8:
                    display_label = display_label[:-4] + "..."
                    label_width = self._get_text_size(draw, display_label, font_small)[0]
                
                draw.text((x + card_padding, inner_y), display_label,
                          fill=self.COLORS["text_secondary"], font=font_small)
                
                # 百分比（右对齐，同一行）
                percent_text = f"{percent}%"
                percent_width = self._get_text_size(draw, percent_text, font_small)[0]
                draw.text((x + card_width - card_padding - percent_width, inner_y),
                          percent_text, fill=bar_color, font=font_small)
                
                inner_y += 18 * scale
                
                # 第二行：进度条 + 刷新时间
                bar_width = card_width - card_padding * 2 - 100 * scale
                self._draw_progress_bar(draw, x + card_padding, inner_y, 
                                       bar_width, 10 * scale, percent, bar_color)
                
                # 刷新时间（右对齐）
                reset_text = reset_time
                reset_width = self._get_text_size(draw, reset_text, font_tiny)[0]
                draw.text((x + card_width - card_padding - reset_width, inner_y - 2 * scale),
                          reset_text, fill=self.COLORS["text_muted"], font=font_tiny)
                
                inner_y += 22 * scale

    def render_dashboard(self, data: Dict[str, Any]) -> Image.Image:
        """渲染综合仪表盘 - 简化版：垂直布局，自适应高度"""
        base_width = 800  # 单列布局，更紧凑
        scale = self.SCALE_FACTOR
        
        today_data = data.get("today", {})
        quota_data = data.get("quota", {})
        analysis_text = data.get("analysis", "")
        
        model_stats = today_data.get("model_stats") or []
        accounts = quota_data.get("accounts", [])
        
        # 按凭证类型分组账号
        provider_groups: Dict[str, List[Dict[str, Any]]] = {}
        for account in accounts:
            provider = account.get("provider", "unknown")
            if provider not in provider_groups:
                provider_groups[provider] = []
            provider_groups[provider].append(account)
        
        # 应用截断限制（从 quota_data 中获取配置）
        max_render_count = quota_data.get("max_render_count")
        truncated_counts: Dict[str, int] = {}
        if max_render_count:
            for provider in provider_groups:
                config_key = "gemini-cli" if provider == "gemini" else provider
                max_count = max_render_count.get(config_key, 0)
                if max_count > 0 and len(provider_groups[provider]) > max_count:
                    truncated_counts[provider] = len(provider_groups[provider]) - max_count
                    provider_groups[provider] = provider_groups[provider][:max_count]
        
        # 使用足够大的画布（后续裁剪）
        max_height = 5000
        width = base_width * scale
        height = max_height * scale
        padding = 24 * scale
        
        img = self._create_gradient_bg(width, height)
        draw = ImageDraw.Draw(img)
        
        # 字体
        font_title = get_font(24 * scale)
        font_section = get_font(16 * scale)
        font_medium = get_font(14 * scale)
        font_small = get_font(12 * scale)
        font_tiny = get_font(10 * scale)
        
        y = padding
        
        # ========== 1. 标题区域 ==========
        draw.text((padding, y), "📊 CLIProxyAPI 综合仪表盘",
                  fill=self.COLORS["text_primary"], font=font_title)
        
        query_time = data.get("query_time", "")
        if query_time:
            time_text = f"⏱️ {query_time}"
            time_width = self._get_text_size(draw, time_text, font_small)[0]
            draw.text((width - padding - time_width, y + 4 * scale),
                      time_text, fill=self.COLORS["accent_cyan"], font=font_small)
        
        subtitle = today_data.get("subtitle", "")
        if subtitle:
            draw.text((padding, y + 30 * scale), f"📅 {subtitle}",
                      fill=self.COLORS["text_secondary"], font=font_small)
        
        y += 52 * scale
        
        # ========== 2. 核心指标（横向5个小卡片） ==========
        card_gap = 10 * scale
        card_width = (width - padding * 2 - card_gap * 4) // 5
        card_height = 54 * scale
        
        metrics = [
            ("请求", str(today_data.get("today_requests", 0)), self.COLORS["accent_purple"]),
            ("Token", today_data.get("today_tokens", "0"), self.COLORS["accent_cyan"]),
            ("成功率", f"{today_data.get('success_rate', 100)}%", self.COLORS["accent_green"]),
            ("模型", str(len(model_stats)), self.COLORS["accent_blue"]),
            ("账号", str(len(accounts)), self.COLORS["accent_orange"]),
        ]
        
        for i, (label, value, color) in enumerate(metrics):
            x = padding + i * (card_width + card_gap)
            self._draw_rounded_rect(draw,
                (x, y, x + card_width, y + card_height),
                8 * scale, self.COLORS["card_bg"], self.COLORS["card_border"])
            draw.text((x + 8 * scale, y + 6 * scale), label,
                      fill=self.COLORS["text_muted"], font=font_tiny)
            draw.text((x + 8 * scale, y + 22 * scale), value,
                      fill=color, font=font_section)
        
        y += card_height + 16 * scale
        
        # ========== 3. 模型使用 TOP ==========
        section_start = y
        draw.text((padding, y), "🔥 模型使用 TOP",
                  fill=self.COLORS["text_primary"], font=font_section)
        y += 28 * scale
        
        if model_stats:
            max_requests = max((m.get("requests", 0) for m in model_stats), default=1)
            for m in model_stats[:12]:  # 最多12个
                name = m.get("name", "")
                if len(name) > 35:
                    name = name[:33] + ".."
                requests = m.get("requests", 0)
                tokens = m.get("tokens", "0")
                
                draw.text((padding + 8 * scale, y), name,
                          fill=self.COLORS["text_secondary"], font=font_small)
                
                info_text = f"{requests} | {tokens}"
                info_width = self._get_text_size(draw, info_text, font_tiny)[0]
                draw.text((width - padding - info_width, y + 2 * scale),
                          info_text, fill=self.COLORS["text_muted"], font=font_tiny)
                
                y += 22 * scale
        
        # Token 分解
        token_breakdown = today_data.get("token_breakdown")
        if token_breakdown:
            y += 8 * scale
            draw.line([(padding, y), (width - padding, y)],
                     fill=self.COLORS["divider"], width=1)
            y += 10 * scale
            
            token_items = [
                ("输入", token_breakdown.get("input", "0"), self.COLORS["accent_blue"]),
                ("输出", token_breakdown.get("output", "0"), self.COLORS["accent_green"]),
                ("推理", token_breakdown.get("reasoning", "0"), self.COLORS["accent_purple"]),
                ("缓存", token_breakdown.get("cached", "0"), self.COLORS["accent_cyan"]),
            ]
            
            item_width = (width - padding * 2) // 4
            for i, (label, value, color) in enumerate(token_items):
                ix = padding + i * item_width
                draw.text((ix, y), label, fill=self.COLORS["text_muted"], font=font_tiny)
                draw.text((ix + 36 * scale, y), value, fill=color, font=font_small)
            
            y += 20 * scale
        
        y += 16 * scale
        
        # ========== 4. 配额状态 ==========
        draw.text((padding, y), "⚡ 配额状态",
                  fill=self.COLORS["text_primary"], font=font_section)
        y += 28 * scale
        
        for provider, accs in provider_groups.items():
            provider_color = self.PROVIDER_COLORS.get(provider, self.COLORS["accent_blue"])
            provider_name = accs[0].get("provider_name", provider.title()) if accs else provider
            provider_icon = accs[0].get("provider_icon", "📦") if accs else "📦"
            
            draw.text((padding + 8 * scale, y), f"{provider_icon} {provider_name}",
                      fill=provider_color, font=font_small)
            y += 22 * scale
            
            for acc in accs:
                email = acc.get("email", "未知")
                if len(email) > 28:
                    email = email[:26] + ".."
                icon = acc.get("icon", "")
                icon_color = self.COLORS["accent_green"] if icon == "✅" else self.COLORS["accent_red"]
                
                draw.ellipse([padding + 16 * scale, y + 3 * scale, 
                             padding + 22 * scale, y + 9 * scale], fill=icon_color)
                draw.text((padding + 28 * scale, y), email,
                          fill=self.COLORS["text_muted"], font=font_tiny)
                y += 16 * scale
                
                for q in acc.get("quotas", []):
                    label = q.get("label", "")
                    if len(label) > 20:
                        label = label[:18] + ".."
                    percent = q.get("percent", 0)
                    
                    if percent >= 80:
                        bar_color = self.COLORS["accent_green"]
                    elif percent >= 50:
                        bar_color = self.COLORS["accent_yellow"]
                    elif percent >= 20:
                        bar_color = self.COLORS["accent_orange"]
                    else:
                        bar_color = self.COLORS["accent_red"]
                    
                    draw.text((padding + 28 * scale, y), label,
                              fill=self.COLORS["text_muted"], font=font_tiny)
                    
                    bar_x = padding + 180 * scale
                    bar_w = 80 * scale
                    self._draw_progress_bar(draw, bar_x, y + 2 * scale, bar_w, 8 * scale, percent, bar_color)
                    
                    draw.text((bar_x + bar_w + 8 * scale, y), f"{percent}%",
                              fill=bar_color, font=font_tiny)
                    
                    reset_time = q.get("reset_time", "")
                    if reset_time:
                        reset_width = self._get_text_size(draw, reset_time, font_tiny)[0]
                        draw.text((width - padding - reset_width, y),
                                  reset_time, fill=self.COLORS["text_muted"], font=font_tiny)
                    
                    y += 16 * scale
                
                y += 6 * scale
            
            # 显示截断提示
            if provider in truncated_counts:
                truncated_text = f"⋯ 还有 {truncated_counts[provider]} 个账号未显示"
                draw.text((padding + 28 * scale, y), truncated_text,
                         fill=self.COLORS["text_muted"], font=font_tiny)
                y += 18 * scale
            
            y += 8 * scale
        
        y += 8 * scale
        
        # ========== 5. 时段分布 ==========
        time_slots = today_data.get("time_slots") or []
        if time_slots and sum(s.get("count", 0) for s in time_slots) > 0:
            draw.text((padding, y), "📈 时段分布",
                      fill=self.COLORS["text_primary"], font=font_section)
            y += 28 * scale
            
            bar_height = 60 * scale
            slot_gap = 12 * scale
            slot_width = (width - padding * 2 - slot_gap * 3) // 4
            max_count = max((s.get("count", 0) for s in time_slots), default=1)
            
            slot_colors = [
                self.COLORS["accent_blue"],
                self.COLORS["accent_cyan"],
                self.COLORS["accent_purple"],
                self.COLORS["accent_orange"]
            ]
            
            for i, slot in enumerate(time_slots[:4]):
                sx = padding + i * (slot_width + slot_gap)
                count = slot.get("count", 0)
                label = slot.get("label", "")
                
                if max_count > 0:
                    fill_height = int(bar_height * count / max_count)
                else:
                    fill_height = 0
                
                self._draw_rounded_rect(draw,
                    (sx, y, sx + slot_width, y + bar_height),
                    6 * scale, self.COLORS["progress_bg"])
                
                if fill_height > 6 * scale:
                    self._draw_rounded_rect(draw,
                        (sx, y + bar_height - fill_height, sx + slot_width, y + bar_height),
                        6 * scale, slot_colors[i])
                
                # 标签在柱状图下方
                draw.text((sx + 4 * scale, y + bar_height + 6 * scale), label,
                          fill=self.COLORS["text_muted"], font=font_tiny)
                count_text = str(count)
                count_width = self._get_text_size(draw, count_text, font_small)[0]
                draw.text((sx + slot_width - count_width - 4 * scale, y + bar_height + 6 * scale),
                          count_text, fill=slot_colors[i], font=font_small)
            
            y += bar_height + 28 * scale
        
        y += 8 * scale
        
        # ========== 6. AI 分析 ==========
        if analysis_text:
            draw.text((padding, y), "🤖 AI 智能分析",
                      fill=self.COLORS["text_primary"], font=font_section)
            y += 28 * scale
            
            max_text_width = width - padding * 2 - 16 * scale
            lines = self._wrap_text(analysis_text, font_tiny, max_text_width, draw)
            
            for line in lines:
                if line.strip().startswith("###"):
                    title_line = line.replace("###", "").strip()
                    y += 6 * scale
                    draw.text((padding + 8 * scale, y), title_line,
                              fill=self.COLORS["accent_cyan"], font=font_small)
                    y += 18 * scale
                elif line.strip().startswith("**") and line.strip().endswith("**"):
                    # 加粗文本
                    bold_text = line.strip().strip("*")
                    draw.text((padding + 8 * scale, y), bold_text,
                              fill=self.COLORS["text_primary"], font=font_small)
                    y += 16 * scale
                elif line.strip():
                    draw.text((padding + 8 * scale, y), line,
                              fill=self.COLORS["text_secondary"], font=font_tiny)
                    y += 14 * scale
                else:
                    y += 8 * scale  # 空行
        
        y += 16 * scale
        
        # 裁剪到实际内容
        img = self._crop_to_content(img, y, padding=8 * scale)
        
        return self._downscale_image(img)
    
    def _wrap_text(self, text: str, font, max_width: int, draw: ImageDraw.Draw) -> List[str]:
        """文本自动换行"""
        lines = []
        for paragraph in text.split('\n'):
            if not paragraph.strip():
                lines.append("")
                continue
            
            words = list(paragraph)
            current_line = ""
            
            for char in words:
                test_line = current_line + char
                width = self._get_text_size(draw, test_line, font)[0]
                if width <= max_width:
                    current_line = test_line
                else:
                    if current_line:
                        lines.append(current_line)
                    current_line = char
            
            if current_line:
                lines.append(current_line)
        
        return lines

    def render(self, data: Dict[str, Any]) -> Optional[Image.Image]:
        """根据数据类型渲染对应的卡片"""
        stats_type = data.get("stats_type", "")

        if stats_type == "overview":
            return self.render_overview(data)
        elif stats_type == "today":
            return self.render_today(data)
        elif stats_type == "quota":
            return self.render_quota(data)
        elif stats_type == "dashboard":
            return self.render_dashboard(data)

        return None

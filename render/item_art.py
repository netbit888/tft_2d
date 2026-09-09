"""装备贴图：assets/items/{base|combine|special}/<item_id>.png（有图显图，缺图回退程序化图标）。

命名规则与棋子贴图（assets/units/<tid>.png）保持一致，并按类别分目录：
- 散件（基础件）放 base/：文件名 = 基础件 id，如 base/bow.png；
- 成装放 combine/：文件名 = "基础件a+基础件b"，如 combine/bow+wand.png（羊刀）；
- 特殊工具放 special/：如 special/gold_remover.png（金制拆卸器）；
- 除 PNG 外也探测 .webp / .jpg / .jpeg，任何一件缺图都自动回退下面的程序化绘制。

文件缺失会被负缓存（只探测一次），运行中放入图片需重启游戏才生效。
"""

from __future__ import annotations

from pathlib import Path

import pygame

from core.items import is_base_item, is_special_item, item_name

from . import theme
from .assets import render as render_text
from .widgets import panel

# 装备贴图根目录：assets/items/（内部按 base / combine / special 分子目录）
_ITEM_TEX_DIR = Path(__file__).resolve().parent.parent / "assets" / "items"
_EXTS = (".png", ".webp", ".jpg", ".jpeg")

# 原图缓存（含负缓存：找不到贴图记 None）与按尺寸缩放后的图标缓存
_TEX_CACHE: dict[str, pygame.Surface | None] = {}
_ICON_CACHE: dict[tuple[str, int], pygame.Surface | None] = {}


def _item_subdir(item_id: str) -> str | None:
    """装备贴图所在子目录：特殊工具 -> special；基础件 -> base；成装 -> combine。

    仅按 data/items.json 与 SPECIAL_ITEMS 的 id 检索；未知 id 返回 None（视为缺图）。
    """
    if is_special_item(item_id):
        return "special"
    if is_base_item(item_id):
        return "base"
    if "+" in item_id:
        return "combine"
    return None


def item_texture(item_id: str) -> pygame.Surface | None:
    """加载装备贴图原图；缺文件 / 加载失败返回 None 并负缓存，不阻塞游戏。"""
    if item_id in _TEX_CACHE:
        return _TEX_CACHE[item_id]
    sub = _item_subdir(item_id)
    tex: pygame.Surface | None = None
    if sub is not None:
        folder = _ITEM_TEX_DIR / sub
        for ext in _EXTS:
            path = folder / f"{item_id}{ext}"
            if not path.is_file():
                continue
            try:
                raw = pygame.image.load(str(path))
            except (pygame.error, ValueError):
                raw = None
            if raw is not None:
                try:
                    tex = raw.convert_alpha()
                except pygame.error:
                    tex = raw  # 视频未初始化等场景：原图含透明通道也可直接使用
                break
    _TEX_CACHE[item_id] = tex
    return tex


def has_item_art(item_id: str) -> bool:
    """该装备是否有贴图（没有则绘制层走程序化回退）。"""
    return item_texture(item_id) is not None


def item_icon(item_id: str, size: int) -> pygame.Surface | None:
    """按目标边长生成方形图标：等比缩放（contain）居中，四周透明；无贴图返回 None。"""
    tex = item_texture(item_id)
    if tex is None:
        return None
    size = max(1, int(size))
    key = (item_id, size)
    cached = _ICON_CACHE.get(key)
    if cached is not None:
        return cached

    w, h = tex.get_size()
    scale = min(size / max(1, w), size / max(1, h))
    dw, dh = max(1, int(w * scale)), max(1, int(h * scale))
    img = pygame.Surface((size, size), pygame.SRCALPHA)
    small = tex if (dw, dh) == (w, h) else pygame.transform.smoothscale(tex, (dw, dh))
    img.blit(small, ((size - dw) // 2, (size - dh) // 2))
    _ICON_CACHE[key] = img
    return img


def clear_cache() -> None:
    """清空贴图与图标缓存（换资源/改缩放后重建用）。"""
    _TEX_CACHE.clear()
    _ICON_CACHE.clear()


# ---------- 绘制：大图标（装备栏 / 自选台 / 拖拽跟手） ----------


def draw_item_icon(surface: pygame.Surface, rect: pygame.Rect, item_id: str, dim: bool = False) -> None:
    """画一件装备的格子图标：有贴图铺图标，缺图回退“底色 + 名字首字”。

    稀有度底色与描边在两种模式下都保留（成装/特殊工具金色，基础件灰白）。
    """
    is_combined = "+" in item_id
    if is_special_item(item_id):
        base = (74, 54, 20)  # 特殊工具：亮金底色
    elif is_combined:
        base = (58, 46, 24)
    else:
        base = theme.PANEL_LIGHT
    edge = theme.GOLD if (is_combined or is_special_item(item_id)) else theme.BORDER
    panel(surface, rect, base, radius=8, border=edge, width=max(2, 2 * theme.S))

    pad = max(2, int(4 * theme.S))
    art = item_icon(item_id, max(1, rect.w - pad * 2))
    if art is not None:
        if dim:  # 不可用/已失效：整枚图标压暗，仍然可辨认
            art = art.copy()
            dark = pygame.Surface(art.get_size(), pygame.SRCALPHA)
            dark.fill((0, 0, 0, 120))
            art.blit(dark, (0, 0))
        surface.blit(
            art,
            (rect.centerx - art.get_width() // 2, rect.centery - art.get_height() // 2),
        )
        return

    # 回退：取装备名第一个字做大图标（与原程序化外观一致）
    name = item_name(item_id)
    glyph = name[0] if name else "?"
    color = theme.TEXT if not dim else theme.TEXT_DIM
    g = render_text(glyph, theme.FS_NORMAL, color)
    surface.blit(g, (rect.centerx - g.get_width() // 2, rect.y + 4 * theme.S))


# ---------- 绘制：小徽章（棋盘 / 备战席棋子脚下） ----------


def draw_item_badge(surface: pygame.Surface, center, item_id: str, size: int | None = None) -> None:
    """棋子脚下的装备小徽章：有贴图显示缩略图，缺图沿用金色（成装）/ 灰色菱形状。"""
    s = theme.S
    size = max(6, int(size if size is not None else 12 * s))
    art = item_icon(item_id, size)
    if art is not None:
        bg = pygame.Rect(0, 0, size, size)
        bg.center = center
        pygame.draw.rect(surface, (12, 13, 18), bg, border_radius=3)
        surface.blit(art, art.get_rect(center=center))
        edge = theme.GOLD if "+" in item_id else theme.BORDER
        pygame.draw.rect(surface, edge, bg, width=1, border_radius=3)
        return

    half = max(3, int(4 * s))
    x, y = center
    color = theme.GOLD if "+" in item_id else theme.BORDER
    pts = [(x, y - half), (x + half, y), (x, y + half), (x - half, y)]
    pygame.draw.polygon(surface, color, pts)
    pygame.draw.polygon(surface, (12, 13, 18), pts, width=1)

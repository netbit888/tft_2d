"""左侧页签栏：竖排「羁绊 / 装备」方形按钮 + 命中检测。

左侧面板拆成“窄按钮栏 + 内容区”：点哪个页签，内容区就显示哪个页的内容
（羁绊详情 / 装备栏）。本模块只管按钮的几何、绘制与命中，不含内容页绘制。
"""

from __future__ import annotations

import pygame

from . import theme
from .assets import render
from .trait_art import hex_points
from .widgets import panel

TABS: tuple[str, ...] = ("traits", "items")
LABEL = {"traits": "羁绊", "items": "装备"}


def side_tab_rects() -> list[tuple[pygame.Rect, str]]:
    """两个页签按钮的 (矩形, 页签键)：栏内水平居中，自上而下排列。"""
    size = theme.SIDE_BTN
    x = theme.SIDE_PAD + (theme.SIDE_TAB_W - size) // 2
    y = theme.SIDE_PANEL_Y
    return [
        (pygame.Rect(x, y + i * (size + theme.SIDE_BTN_GAP), size, size), key)
        for i, key in enumerate(TABS)
    ]


def side_tab_at(pos) -> str | None:
    """屏幕坐标命中的页签键；不在按钮上返回 None。"""
    for rect, key in side_tab_rects():
        if rect.collidepoint(pos):
            return key
    return None


def _trait_glyph(surface, cx: float, cy: float, r: float, color) -> None:
    """羁绊符号：三颗档位菱形。"""
    half = max(2, int(r * 0.26))
    for dx in (-r * 0.52, 0.0, r * 0.52):
        px = cx + dx
        pts = [(px, cy - half), (px + half, cy), (px, cy + half), (px - half, cy)]
        pygame.draw.polygon(surface, color, pts)


def _item_glyph(surface, cx: float, cy: float, r: float, color) -> None:
    """装备符号：盾形轮廓。"""
    w = r * 0.62
    pts = [
        (cx - w, cy - r * 0.62),
        (cx + w, cy - r * 0.62),
        (cx + w, cy + r * 0.10),
        (cx, cy + r * 0.74),
        (cx - w, cy + r * 0.10),
    ]
    pygame.draw.polygon(surface, color, pts, width=max(1, int(2 * theme.S)))


def _s_badge(surface) -> None:
    """装备按钮右上角的金色小角标（对齐设计稿）。"""
    rect = next((r for r, k in side_tab_rects() if k == "items"), None)
    if rect is None:
        return
    r = max(7, int(9 * theme.S))
    center = (rect.right - int(4 * theme.S), rect.y + int(4 * theme.S))
    pygame.draw.circle(surface, theme.GOLD, center, r)
    pygame.draw.circle(surface, (12, 13, 18), center, r, width=1)
    img = render("S", theme.FS_MICRO, (26, 22, 12))
    surface.blit(img, img.get_rect(center=center))


def draw_side_tabs(surface: pygame.Surface, active: str, t: float = 0.0) -> None:
    """画左侧页签栏：选中态金框 + 高亮底，悬停提亮。"""
    s = theme.S
    mouse = pygame.mouse.get_pos()
    for rect, key in side_tab_rects():
        on = key == active
        hovered = rect.collidepoint(mouse)
        if on:
            bg = theme.PANEL_LIGHT
        else:
            bg = theme.shade(theme.PANEL, 1.25) if hovered else theme.PANEL
        panel(surface, rect, bg, radius=int(10 * s), border=theme.GOLD if on else theme.BORDER,
              width=2 if on else 1)

        cx, cy = rect.center
        r = rect.width * 0.30
        line = theme.GOLD if on else theme.TEXT_DIM
        pygame.draw.polygon(surface, line, hex_points(cx, cy, r), width=max(1, int(2 * s)))
        if key == "traits":
            _trait_glyph(surface, cx, cy, r, line)
        else:
            _item_glyph(surface, cx, cy, r, line)
    _s_badge(surface)

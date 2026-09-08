"""基础控件：圆角面板、按钮、血条、提示条。

所有尺寸都读 theme，不写死像素，改缩放因子即可整体放大。
"""

from __future__ import annotations

import math

import pygame

from . import theme
from .assets import font, render, text

_DIM_CACHE: dict[tuple, pygame.Surface] = {}


def panel(surface: pygame.Surface, rect, color=None, radius=10, border=None, width=1) -> None:
    color = color if color is not None else theme.PANEL
    r = max(1, int(radius))
    pygame.draw.rect(surface, color, rect, border_radius=r)
    if border:
        pygame.draw.rect(surface, border, rect, width=max(1, int(width)), border_radius=r)


def bar(surface: pygame.Surface, rect, ratio: float, color, bg=(28, 30, 38), radius=3) -> None:
    """进度条，ratio 取值 0~1。"""
    r = max(1, int(radius))
    pygame.draw.rect(surface, bg, rect, border_radius=r)
    ratio = max(0.0, min(1.0, ratio))
    if ratio > 0:
        fill = pygame.Rect(rect.x, rect.y, max(2, int(rect.width * ratio)), rect.height)
        pygame.draw.rect(surface, color, fill, border_radius=r)


def hp_color(ratio: float):
    if ratio > 0.5:
        return theme.HP_GREEN
    if ratio > 0.25:
        return theme.HP_YELLOW
    return theme.HP_RED


def dim_overlay(size: tuple[int, int], alpha: int = 165) -> pygame.Surface:
    """缓存全屏半透明遮罩，避免每帧新建一张几 MB 的 Surface。"""
    key = (size, alpha)
    surf = _DIM_CACHE.get(key)
    if surf is None:
        surf = pygame.Surface(size, pygame.SRCALPHA)
        surf.fill((8, 10, 16, alpha))
        _DIM_CACHE[key] = surf
    return surf


class Button:
    """带 hover / 按下 / 呼吸脉冲的按钮。"""

    def __init__(self, rect, label: str, color=None, enabled: bool = True, pulse: bool = False) -> None:
        self.rect = pygame.Rect(rect)
        self.label = label
        self.color = color if color is not None else theme.ACCENT
        self.enabled = enabled
        self.pulse = pulse
        self.hover = False
        self.pressed = False

    def handle(self, event: pygame.event.Event) -> bool:
        """处理鼠标事件，返回是否被点击。"""
        if not self.enabled:
            self.hover = False
            return False
        if event.type == pygame.MOUSEMOTION:
            self.hover = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.pressed = True
                return True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.pressed = False
        return False

    def draw(self, surface: pygame.Surface, t: float = 0.0) -> None:
        base = self.color
        if not self.enabled:
            base = (70, 74, 86)
        elif self.hover:
            base = tuple(min(255, c + 26) for c in base)
        if self.pressed:
            base = tuple(int(c * 0.86) for c in base)

        rect = self.rect
        if self.pulse and self.enabled:
            k = 0.5 + 0.5 * math.sin(t * 3.2)
            glow = pygame.Surface((rect.width + 12, rect.height + 12), pygame.SRCALPHA)
            pygame.draw.rect(
                glow,
                (*base, int(40 + 70 * k)),
                glow.get_rect(),
                border_radius=12,
            )
            surface.blit(glow, (rect.x - 6, rect.y - 6))
            grow = int(2 * k)
            rect = rect.inflate(grow * 2, grow * 2)

        pygame.draw.rect(surface, base, rect, border_radius=8)
        pygame.draw.rect(surface, (255, 255, 255, 40), rect, width=1, border_radius=8)
        text(
            surface,
            self.label,
            theme.FS_SMALL,
            (255, 255, 255) if self.enabled else theme.TEXT_DIM,
            rect.center,
            center=True,
        )


def tooltip(surface: pygame.Surface, lines, pos, width: int | None = None) -> None:
    """深色小提示条，lines 可以是字符串或字符串列表。"""
    if isinstance(lines, str):
        lines = [lines]
    pad = 8 * theme.S
    imgs = [render(s, theme.FS_TINY, theme.TEXT) for s in lines]
    w = max((i.get_width() for i in imgs), default=0) + pad * 2
    if width:
        w = max(w, width)
    h = sum(i.get_height() for i in imgs) + pad * 2 + (len(imgs) - 1) * 4 * theme.S
    rect = pygame.Rect(pos[0], pos[1], w, h)

    # 超出右/下边界时翻到反方向，避免提示框被窗口裁掉
    if rect.right > theme.WINDOW_W - 4:
        rect.right = pos[0]
    if rect.bottom > theme.WINDOW_H - 4:
        rect.bottom = pos[1]

    pygame.draw.rect(surface, (14, 16, 22), rect, border_radius=6)
    pygame.draw.rect(surface, theme.BORDER, rect, width=1, border_radius=6)
    y = rect.y + pad
    for i in imgs:
        surface.blit(i, (rect.x + pad, y))
        y += i.get_height() + 4 * theme.S


def chip(surface: pygame.Surface, rect, label: str, color, text_color=(255, 255, 255)) -> None:
    """小圆角标签（羁绊名 / 费用等）。"""
    pygame.draw.rect(surface, color, rect, border_radius=max(2, 4 * theme.S))
    text(surface, label, theme.FS_TINY, text_color, rect.center, center=True)


def line_height(size: int) -> int:
    return font(size).get_height()

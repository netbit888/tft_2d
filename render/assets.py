"""字体与绘制资源。

坑：pygame 的内置字体（Font(None)）不含中文，棋子名会渲染成方块，
必须显式加载系统中文字体，并做好 fallback 链。
"""

from __future__ import annotations

import ctypes
import os
import sys

import pygame

FONT_CANDIDATES = (
    "C:/Windows/Fonts/msyhc.ttc",  # 微软雅黑
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",  # 黑体
    "C:/Windows/Fonts/simsun.ttc",  # 宋体
    "/System/Library/Fonts/PingFang.ttc",  # macOS
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",  # Linux
)

# 文字缓存上限：伤害飘字会不断产生新 key，高分辨率下每条缓存的 Surface 也更大
_TEXT_CACHE_MAX = 600

_cache: dict[int, pygame.font.Font] = {}
_path: str | None = None
_text_cache: dict[tuple, pygame.Surface] = {}


def enable_dpi_awareness() -> None:
    """Windows 下声明 DPI 感知，否则 2560x1600 的窗口会被系统再缩放一次变糊。

    必须在 pygame.init() 之前调用，且失败不能影响启动。
    """
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAwareness(True)
    except Exception:
        pass


def _resolve_font_path() -> str:
    global _path
    if _path is None:
        for p in FONT_CANDIDATES:
            if os.path.exists(p):
                _path = p
                break
        if _path is None:
            raise RuntimeError(
                "没有找到可用的中文字体，请安装微软雅黑/黑体，"
                "或在 render/assets.py 的 FONT_CANDIDATES 里补上你系统里的字体路径"
            )
    return _path


def font(size: int) -> pygame.font.Font:
    """按字号取缓存的字体对象。"""
    if size not in _cache:
        _cache[size] = pygame.font.Font(_resolve_font_path(), size)
    return _cache[size]


def render(s: str, size: int, color) -> pygame.Surface:
    """渲染一行文字并返回缓存的 Surface（战斗飘字提前渲染用）。"""
    key = (s, size, tuple(color))
    img = _text_cache.get(key)
    if img is None:
        img = font(size).render(s, True, color)
        if len(_text_cache) > _TEXT_CACHE_MAX:
            _text_cache.clear()
        _text_cache[key] = img
    return img


def text(surface: pygame.Surface, s: str, size: int, color, pos, center: bool = False) -> None:
    """画一行文字。center=True 时 pos 为矩形中心。"""
    img = render(s, size, color)
    rect = img.get_rect(center=pos) if center else img.get_rect(topleft=pos)
    surface.blit(img, rect)


def text_shadow(
    surface: pygame.Surface, s: str, size: int, color, pos, center: bool = False, shadow=(0, 0, 0)
) -> None:
    """带描边阴影的文字，压在头像/卡面上时更清楚。"""
    img = render(s, size, color)
    rect = img.get_rect(center=pos) if center else img.get_rect(topleft=pos)
    off = max(1, size // 13)
    dark = font(size).render(s, True, shadow)
    surface.blit(dark, (rect.x, rect.y + off))
    surface.blit(img, rect)


def text_size(s: str, size: int) -> tuple[int, int]:
    return font(size).size(s)

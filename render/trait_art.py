"""羁绊图标绘制：官方贴图优先（assets/traits/<羁绊id>.png），缺图回退程序化六边形。

贴图由 tools/fetch_trait_icons.py 从官方 CDN 的 picture 字段下载（96x96 带透明）。
界面只用一两种尺寸，这里按 (羁绊id, 尺寸, 是否灰化) 缓存缩放结果，避免每帧重采样。
"""

from __future__ import annotations

from pathlib import Path

import pygame

from . import theme

_COS30 = 0.86602540378
_ICON_DIR = Path(__file__).resolve().parent.parent / "assets" / "traits"
_cache: dict[tuple[str, int, bool], pygame.Surface] = {}


def hex_points(cx: float, cy: float, r: float) -> list[tuple[float, float]]:
    """尖顶六边形的六个顶点（与棋盘地砖同一套几何）。"""
    w = _COS30 * r
    half = r * 0.5
    return [
        (cx, cy - r),
        (cx + w, cy - half),
        (cx + w, cy + half),
        (cx, cy + r),
        (cx - w, cy + half),
        (cx - w, cy - half),
    ]


def _trait_name(tid: str) -> str:
    from core.loader import load_traits

    info = load_traits().get(str(tid))
    return str(info.get("name", "")) if info else ""


def _load_texture(tid: str, size: int) -> pygame.Surface | None:
    path = _ICON_DIR / f"{tid}.png"
    if not path.is_file():
        return None
    try:
        raw = pygame.image.load(str(path))
    except Exception:  # noqa: BLE001 贴图损坏不该影响开局
        return None
    return pygame.transform.smoothscale(raw, (size, size))


def _procedural(tid: str, size: int) -> pygame.Surface:
    """没有官方贴图时：按羁绊配色画一个六边形徽章 + 名称首字，保证不空窗。"""
    from .assets import render
    from .board_view import trait_color

    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    cx = cy = size / 2
    r = size * 0.46
    pts = hex_points(cx, cy, r)
    color = trait_color(str(tid))
    pygame.draw.polygon(surf, theme.shade(color, 0.32), pts)
    pygame.draw.polygon(surf, color, pts, width=max(1, int(size * 0.07)))
    name = _trait_name(tid)
    if name:
        img = render(name[0], max(10, int(size * 0.5)), theme.TEXT)
        surf.blit(img, img.get_rect(center=(cx, cy)))
    return surf


def trait_icon(tid: str, size: int, dim: bool = False) -> pygame.Surface:
    """取羁绊图标（dim=True 返回压暗版，用于“未激活”档位）。"""
    size = max(8, int(size))
    key = (str(tid), size, bool(dim))
    hit = _cache.get(key)
    if hit is not None:
        return hit
    if len(_cache) > 400:
        _cache.clear()
    img = _load_texture(str(tid), size)
    if img is None:
        img = _procedural(tid, size)
    if dim:
        img = img.copy()
        img.fill((118, 118, 118, 255), special_flags=pygame.BLEND_RGB_MULT)
    _cache[key] = img
    return img


def draw_trait_icon(surface: pygame.Surface, center, size: int, tid: str, active: bool = True):
    """在 center 处画一枚羁绊图标，返回其矩形（供排版续接）。"""
    img = trait_icon(tid, size, dim=not active)
    rect = img.get_rect(center=(int(center[0]), int(center[1])))
    surface.blit(img, rect)
    return rect

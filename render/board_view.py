"""棋盘与棋子的绘制。

坐标说明：core 里己方（blue）占 row 0-3（屏幕下半）、敌方（red）占 row 4-7（屏幕上半）；
绘制时把行号翻转（display_row = 7 - core_row），让己方显示在下半部分。

棋盘画成蜂窝六边形：尖顶六边形逐列排开，相邻行整体错半格（odd-r 偏移）。
core 的战斗/摆位仍按 7x8 行列逻辑坐标算，绘制层只负责把 (col,row) 翻译成屏幕点，
命中判定改为点是否落在对应六边形内。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pygame

from core.loader import load_traits, load_units

from . import theme
from .assets import font
from .widgets import bar, hp_color, panel

# ---------- 坐标换算（蜂窝六边形，odd-r） ----------

_COS30 = 0.86602540378


def core_row_to_display(core_row: int) -> int:
    return theme.BOARD_ROWS - 1 - core_row


def display_row_to_core(display_row: int) -> int:
    return theme.BOARD_ROWS - 1 - display_row


def hex_point(col: float, core_row: float) -> tuple[float, float]:
    """core 坐标 -> 屏幕坐标，col/core_row 允许是浮点（战斗插值用）。

    行错位用余弦在整数行之间平滑过渡：偶数行错 0、奇数行错半列，
    移动中的单位不会在跨行时产生跳变。
    """
    disp = theme.BOARD_ROWS - 1 - core_row
    # 偶数行错 0、奇数行错半列，行间用余弦平滑过渡
    shift = theme.HEX_COL_STEP * 0.5 * (0.5 - 0.5 * math.cos(math.pi * disp))
    x = theme.BOARD_X + theme.HEX_COL_STEP * (col + 1.0) + shift
    y = theme.BOARD_Y + theme.HEX_R + theme.HEX_ROW_STEP * disp
    return x, y


def cell_center(col: int, core_row: int) -> tuple[int, int]:
    """某个格子中心的屏幕坐标（传 core 坐标）。"""
    x, y = hex_point(float(col), float(core_row))
    return int(round(x)), int(round(y))


def cell_rect(col: int, core_row: int) -> pygame.Rect:
    """某个格子的屏幕包围盒（传 core 坐标），棋子按它居中绘制。"""
    cx, cy = cell_center(col, core_row)
    size = theme.CELL
    return pygame.Rect(cx - size // 2, cy - size // 2, size, size)


def cell_polygon(col: int, core_row: int, shrink: int = 0) -> list[tuple[int, int]]:
    """尖顶六边形的六个顶点（从最上点顺时针），返回整数坐标。"""
    cx, cy = cell_center(col, core_row)
    r = max(1, theme.HEX_R - theme.TILE_INSET - shrink)
    w = int(round(_COS30 * r))
    half = (r + 1) // 2
    return [
        (cx, cy - r),
        (cx + w, cy - half),
        (cx + w, cy + half),
        (cx, cy + r),
        (cx - w, cy + half),
        (cx - w, cy - half),
    ]


def _in_polygon(px: float, py: float, pts) -> bool:
    """射线法点是否在多边形内。"""
    inside = False
    n = len(pts)
    j = n - 1
    for i in range(n):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if (yi > py) != (yj > py):
            cross = (xj - xi) * (py - yi) / ((yj - yi) or 1e-9) + xi
            if px < cross:
                inside = not inside
        j = i
    return inside


def cell_at(pos) -> tuple[int, int] | None:
    """屏幕坐标 -> (col, core_row)，不在任何六边形内返回 None。

    全量遍历 56 个六边形做包含测试，逻辑简单、不会漏边角。
    """
    x, y = pos
    for core_row in range(theme.BOARD_ROWS):
        for col in range(theme.BOARD_COLS):
            if _in_polygon(x, y, cell_polygon(col, core_row)):
                return col, core_row
    return None


# ---------- 棋子外观 ----------


@dataclass
class PieceVisual:
    """绘制一个棋子所需的全部信息（与 core 的数据结构解耦）。"""

    name: str
    team: str  # blue / red
    tag: str  # 职业单字，如"战"
    tag_color: tuple
    hp_ratio: float = 1.0
    mana_ratio: float = 0.0
    star: int = 1
    alive: bool = True
    tid: str = ""
    cost: int = 1
    show_bars: bool = False  # 只有战斗阶段画血条/蓝条


def trait_tag(traits: tuple[str, ...]) -> tuple[str, tuple]:
    """取第一个羁绊作为角标（单字 + 颜色）。"""
    if not traits:
        return "兵", theme.TRAIT_FALLBACK
    traits_data = load_traits()
    tid = traits[0]
    name = traits_data.get(tid, {}).get("name", tid)
    return name[0], theme.TRAIT_COLORS.get(tid, theme.TRAIT_FALLBACK)


def visual_from_tid(tid: str, star: int, team: str) -> PieceVisual:
    tpl = load_units()[tid]
    tag, color = trait_tag(tpl.traits)
    return PieceVisual(
        name=tpl.name, team=team, tag=tag, tag_color=color, star=star, tid=tid, cost=tpl.cost
    )


def visual_from_piece(piece, team: str) -> PieceVisual:
    """从玩家棋子构造外观（运营阶段用）。"""
    return visual_from_tid(piece.tid, piece.star, team)


def visual_from_unit(unit) -> PieceVisual:
    """从战斗单位构造外观（战斗阶段用）。"""
    tpl = load_units()[unit.tid]
    tag, color = trait_tag(tpl.traits)
    return PieceVisual(
        name=unit.name,
        team=unit.team,
        tag=tag,
        tag_color=color,
        hp_ratio=unit.hp_ratio,
        mana_ratio=(unit.mana / unit.max_mana if unit.max_mana else 0.0),
        star=unit.star,
        alive=unit.alive,
        tid=unit.tid,
        cost=tpl.cost,
        show_bars=True,
    )


# ---------- 头像（静态，全部缓存） ----------

_AVATAR_CACHE: dict[tuple, pygame.Surface] = {}
_FLASH_CACHE: dict[int, pygame.Surface] = {}


def _clear_caches() -> None:
    _AVATAR_CACHE.clear()
    _FLASH_CACHE.clear()
    _GRID_CACHE.clear()


def _avatar(v: PieceVisual, size: int) -> pygame.Surface:
    """程序化生成一个棋子头像：队伍光环 + 稀有度描边 + 渐变底 + 首字 + 星级。

    棋子在一局里外观不变（除了星级和生死），所以整张图缓存下来，
    每帧只做一次 blit，高分辨率下这是最大的一笔性能节省。
    """
    key = (v.tid, v.star, v.team, size, v.alive)
    cached = _AVATAR_CACHE.get(key)
    if cached is not None:
        return cached

    s = theme.S
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    c = (size // 2, size // 2)
    r = size // 2
    team_color = theme.TEAM_COLORS.get(v.team, theme.TRAIT_FALLBACK)
    if not v.alive:
        team_color = (96, 99, 110)

    # 队伍光环（外圈），用来在棋盘上一眼区分敌我
    pygame.draw.circle(surf, theme.shade(team_color, 0.55), c, r)
    pygame.draw.circle(surf, (10, 11, 15), c, r - max(1, 2 * s))

    # 羁绊色渐变底：一圈一圈画同心圆近似径向渐变
    inner_r = r - max(2, 3 * s)
    if inner_r > 2:
        trait = v.tag_color
        outer = theme.mix(trait, (18, 20, 27), 0.55)
        bright = theme.mix(trait, (255, 255, 255), 0.32)
        if not v.alive:
            outer = (52, 54, 62)
            bright = (96, 99, 110)
        steps = max(6, inner_r // 3)
        for i in range(steps):
            t = i / max(1, steps - 1)
            rr = int(inner_r * (1 - i / steps))
            if rr <= 0:
                break
            pygame.draw.circle(surf, theme.mix(outer, bright, t), c, rr)

    # 稀有度描边 + 星级描边
    rar = theme.rarity(v.cost)
    pygame.draw.circle(surf, rar["edge"], c, r - s, width=max(2, 3 * s))
    star_ring = theme.STAR_RING.get(v.star)
    if star_ring:
        pygame.draw.circle(surf, star_ring, c, r - max(3, 4 * s), width=max(1, 2 * s))

    # 首字（大头像唯一的内容；名牌与羁绊角标已去掉，后续换圆形贴图）
    if v.name:
        fs = max(10, int(size * 0.52))
        glyph = v.name[0]
        dark = font(fs).render(glyph, True, (12, 13, 18))
        light = font(fs).render(glyph, True, (255, 255, 255) if v.alive else (170, 173, 182))
        surf.blit(dark, (c[0] - dark.get_width() // 2, c[1] - dark.get_height() // 2 + max(1, s)))
        surf.blit(light, (c[0] - light.get_width() // 2, c[1] - light.get_height() // 2))

    # 星级（顶部一排金星）
    if v.star > 1:
        pip = max(2, int(size * 0.075))
        gap = int(pip * 2.2)
        total = (v.star - 1) * gap
        py = c[1] - r - max(2, 2 * s)
        for i in range(v.star):
            px = c[0] - total // 2 + i * gap
            pygame.draw.circle(surf, (12, 13, 18), (px, py), pip + max(1, s))
            pygame.draw.circle(surf, theme.GOLD, (px, py), pip)

    _AVATAR_CACHE[key] = surf
    return surf


def _flash_disc(size: int) -> pygame.Surface:
    """受击闪白用的白色圆盘，按尺寸缓存。"""
    surf = _FLASH_CACHE.get(size)
    if surf is None:
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.circle(surf, (255, 255, 255, 255), (size // 2, size // 2), size // 2)
        _FLASH_CACHE[size] = surf
    return surf


def piece_size(rect: pygame.Rect, scale: float = 1.0) -> int:
    return max(8, int(min(rect.width, rect.height) * theme.PIECE_RATIO * scale))


def draw_piece(
    surface: pygame.Surface,
    rect: pygame.Rect,
    v: PieceVisual,
    ghost: bool = False,
    scale: float = 1.0,
    flash: float = 0.0,
    alpha: float = 1.0,
) -> None:
    """在给定矩形里画一个棋子。

    ghost=True   半透明（拖拽预览）；
    scale>1      放大（拖拽跟手 / 吸附反馈）；
    flash>0      受击闪白强度（0~1，战斗阶段用）；
    alpha<1      整体淡出（阵亡时用）。
    """
    size = piece_size(rect, scale)
    av = _avatar(v, size)
    cx, cy = rect.center

    if ghost or alpha < 1.0:
        layer = av.copy()
        layer.set_alpha(170 if ghost else int(255 * max(0.0, min(1.0, alpha))))
        surface.blit(layer, (cx - size // 2, cy - size // 2))
        return

    surface.blit(av, (cx - size // 2, cy - size // 2))

    if flash > 0:
        disc = _flash_disc(size)
        disc.set_alpha(int(190 * min(1.0, flash)))
        surface.blit(disc, (cx - size // 2, cy - size // 2))

    if v.show_bars and v.alive:
        r = size // 2
        s = theme.S
        bar_w = int(r * 1.6)
        hp_h = max(4, int(7 * s))
        mp_h = max(2, int(3 * s))
        top = cy + r + max(1, s)
        bar(
            surface,
            pygame.Rect(cx - bar_w // 2, top, bar_w, hp_h),
            v.hp_ratio,
            hp_color(v.hp_ratio),
            bg=(12, 13, 18),
            radius=hp_h // 2,
        )
        bar(
            surface,
            pygame.Rect(cx - bar_w // 2, top + hp_h + max(1, s), bar_w, mp_h),
            v.mana_ratio,
            theme.MANA_BLUE,
            bg=(12, 13, 18),
            radius=mp_h // 2,
        )


# ---------- 棋盘 ----------

_GRID_CACHE: dict[int, pygame.Surface] = {}


def draw_grid(surface: pygame.Surface) -> None:
    """画 7x8 蜂窝六边形棋盘。棋盘是静态的，整块缓存，每帧一次 blit。"""
    key = theme.S
    cached = _GRID_CACHE.get(key)
    if cached is None:
        cached = _render_grid()
        _GRID_CACHE[key] = cached
    surface.blit(cached, (theme.BOARD_X, theme.BOARD_Y))


def _render_grid() -> pygame.Surface:
    s = theme.S
    w, h = theme.BOARD_W, theme.BOARD_H
    surf = pygame.Surface((w, h))
    surf.fill(theme.BG_SOFT)

    # 底板（把边缘包住，让棋盘有个整体轮廓）
    board_bg = pygame.Rect(4, 4, w - 8, h - 8)
    panel(surf, board_bg, (24, 27, 35), radius=12 * s, border=theme.BORDER_SOFT, width=1)

    own_top = theme.BOARD_ROWS // 2  # 己方 core row 0..3
    for core_row in range(theme.BOARD_ROWS):
        for col in range(theme.BOARD_COLS):
            # surface 贴到 (BOARD_X, BOARD_Y)，这里必须用相对棋盘原点的局部坐标
            cx, cy = cell_center(col, core_row)
            lx, ly = cx - theme.BOARD_X, cy - theme.BOARD_Y
            pts = [(x - theme.BOARD_X, y - theme.BOARD_Y) for x, y in cell_polygon(col, core_row)]

            if core_row < own_top:  # 己方半场（屏幕下半）
                base = theme.SELF_ROW_TINT if (col + core_row) % 2 == 0 else theme.shade(
                    theme.SELF_ROW_TINT, 0.82
                )
            else:
                base = theme.ENEMY_ROW_TINT if (col + core_row) % 2 == 0 else theme.shade(
                    theme.ENEMY_ROW_TINT, 0.82
                )
            pygame.draw.polygon(surf, base, pts)
            # 内侧暗一点，做出一点厚度
            inner = [(x, ly + (y - ly) * 0.88) for x, y in pts]
            pygame.draw.polygon(surf, theme.shade(base, 0.86), inner)
            pygame.draw.polygon(surf, theme.BORDER, pts, width=max(1, s))

    # 中线（两军交火分界）
    mid_y = h // 2
    pygame.draw.line(surf, theme.ACCENT, (4, mid_y), (w - 4, mid_y), max(2, 2 * s))
    return surf


def draw_deploy_highlight(surface: pygame.Surface, accent=None, t: float = 0.0) -> None:
    """拖拽摆位时高亮己方半场四行（core_row 0..3）的六边形边框。"""
    accent = accent or theme.ACCENT
    pulse = 0.55 + 0.45 * math.sin(t * 6.0)
    color = theme.mix(theme.shade(accent, 0.7), (255, 255, 255), 0.25 * pulse)
    for core_row in range(theme.BOARD_ROWS // 2):
        for col in range(theme.BOARD_COLS):
            pygame.draw.polygon(
                surface, color, cell_polygon(col, core_row, shrink=theme.TILE_INSET), width=max(2, 2 * theme.S)
            )


def draw_placements(surface: pygame.Surface, placements: list[dict], team: str) -> None:
    """把一支队伍按布阵画到棋盘上。

    placements 是 auto_place / build_team 的产出：[{"id", "star", "pos", "equip"}, ...]
    """
    for p in placements:
        col, row = int(p["pos"][0]), int(p["pos"][1])
        v = visual_from_tid(p["id"], int(p.get("star", 1)), team)
        draw_piece(surface, cell_rect(col, row), v)
        equip = p.get("equip", [])
        if equip:
            _draw_equip_badges(surface, cell_rect(col, row), equip)


def _draw_equip_badges(surface: pygame.Surface, rect: pygame.Rect, equip: list) -> None:
    """在棋子下方画装备小图标（菱形，高级装备金色）。"""
    n = min(len(equip), 3)
    gap = max(10, int(12 * theme.S))
    start_x = rect.centerx - (n - 1) * gap // 2
    y = rect.bottom - max(4, int(5 * theme.S))
    half = max(3, int(4 * theme.S))
    for k in range(n):
        it = equip[k]
        cx = start_x + k * gap
        color = theme.GOLD if "+" in it.item_id else theme.BORDER
        pts = [(cx, y - half), (cx + half, y), (cx, y + half), (cx - half, y)]
        pygame.draw.polygon(surface, color, pts)
        pygame.draw.polygon(surface, (12, 13, 18), pts, width=1)

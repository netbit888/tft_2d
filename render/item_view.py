"""装备栏与 8 人战况面板的绘制与命中检测。"""

from __future__ import annotations

import pygame

from core.items import is_special_item, item_name, load_items

from . import theme
from .assets import render, text
from .widgets import panel, tooltip


# ---------- 装备栏 ----------


def item_slot_rect(index: int) -> pygame.Rect:
    """装备栏格子：3 列 x 4 行网格。"""
    col = index % theme.ITEM_COLS
    row = index // theme.ITEM_COLS
    x = theme.ITEM_BENCH_X + 12 * theme.S + col * (theme.ITEM_CELL + theme.ITEM_GAP)
    y = theme.ITEM_BENCH_Y + 28 * theme.S + row * (theme.ITEM_CELL + theme.ITEM_GAP)
    return pygame.Rect(x, y, theme.ITEM_CELL, theme.ITEM_CELL)


def item_slot_at(pos) -> int | None:
    for i in range(theme.ITEM_COLS * theme.ITEM_ROWS):
        if item_slot_rect(i).collidepoint(pos):
            return i
    return None


def item_color(item_id: str) -> tuple:
    """高级装备 / 特殊工具（金制拆卸器）用金色描边，基础装备用灰白。"""
    if "+" in item_id or is_special_item(item_id):
        return theme.GOLD
    return theme.BORDER


def draw_item_icon(surface: pygame.Surface, rect: pygame.Rect, item_id: str, dim: bool = False) -> None:
    is_combined = "+" in item_id
    if is_special_item(item_id):
        base = (74, 54, 20)  # 特殊工具：亮金底色
    elif is_combined:
        base = (58, 46, 24)
    else:
        base = theme.PANEL_LIGHT
    edge = item_color(item_id)
    panel(surface, rect, base, radius=8, border=edge, width=max(2, 2 * theme.S))

    name = item_name(item_id)
    # 取名字第一个字做大图标
    glyph = name[0]
    color = theme.TEXT if not dim else theme.TEXT_DIM
    g = render(glyph, theme.FS_NORMAL, color)
    surface.blit(g, (rect.centerx - g.get_width() // 2, rect.y + 4 * theme.S))


def draw_item_bench(surface: pygame.Surface, bench: list, hover: int | None = None) -> None:
    """画装备栏（标题 + 3x4 网格）。"""
    bg = pygame.Rect(
        theme.ITEM_BENCH_X, theme.ITEM_BENCH_Y, theme.ITEM_BENCH_W, theme.ITEM_BENCH_H
    )
    panel(surface, bg, theme.PANEL, radius=10, border=theme.BORDER)

    text(
        surface,
        "装备",
        theme.FS_TINY,
        theme.TEXT,
        (bg.centerx, bg.y + 10 * theme.S),
        center=True,
    )

    total = theme.ITEM_COLS * theme.ITEM_ROWS
    for i in range(total):
        rect = item_slot_rect(i)
        if i < len(bench):
            draw_item_icon(surface, rect, bench[i].item_id)
        else:
            panel(surface, rect, (24, 26, 33), radius=8, border=(44, 48, 60))
        if i == hover:
            pygame.draw.rect(surface, theme.ACCENT, rect, width=2, border_radius=8)


def draw_combine_candidates(surface: pygame.Surface, bench: list, drag_item, drag_slot: int) -> None:
    """拖起一件基础装备时，给装备栏里'能合成'的目标格子描金色高亮。"""
    from core.items import combine_key

    for i, it in enumerate(bench):
        if i == drag_slot or it is drag_item:
            continue
        if combine_key(drag_item.item_id, it.item_id):
            rect = item_slot_rect(i)
            pygame.draw.rect(surface, theme.GOLD, rect, width=3, border_radius=8)


# ---------- 8 人战况面板 ----------


def draw_roster(
    surface: pygame.Surface,
    game,
    selected: int = 0,
    current_opp: int | None = None,
) -> list[tuple[pygame.Rect, int]]:
    """右侧 8 人战况：每名玩家的名字、血量、等级、淘汰状态。

    selected 为当前观察对象（0=自己）；current_opp 标记本回合配对对手。
    返回每行的 (命中矩形, 玩家索引)，供上层做点击切换观察视角。
    """
    if len(game.players) <= 2:
        return []

    bg = pygame.Rect(
        theme.ROSTER_X,
        theme.ROSTER_Y,
        theme.ROSTER_W,
        theme.ROSTER_ROW_H * game.num_players + 40 * theme.S,
    )
    panel(surface, bg, theme.PANEL, radius=10, border=theme.BORDER)

    text(
        surface,
        "战况",
        theme.FS_SMALL,
        theme.TEXT,
        (bg.centerx, bg.y + 15 * theme.S),
        center=True,
    )

    rows: list[tuple[pygame.Rect, int]] = []
    y = bg.y + 32 * theme.S
    for i, p in enumerate(game.players):
        # 玩家本人高亮
        is_you = i == 0
        row_color = theme.PANEL_LIGHT if is_you else None
        row = pygame.Rect(bg.x + 8 * theme.S, y, bg.width - 16 * theme.S, theme.ROSTER_ROW_H - 4 * theme.S)
        if row_color:
            pygame.draw.rect(surface, row_color, row, border_radius=6)
        rows.append((row, i))

        # 观察对象（金色外框）与"本回合对手"（青色细框）区分标记
        if i == selected:
            pygame.draw.rect(surface, theme.GOLD, row.inflate(3 * theme.S, 3 * theme.S), width=2, border_radius=7)
        elif current_opp is not None and i == current_opp and p.is_alive and not is_you:
            pygame.draw.rect(surface, theme.ACCENT, row.inflate(3 * theme.S, 3 * theme.S), width=1, border_radius=7)

        name = p.name if p.is_alive else f"✗ {p.name}"
        name_color = theme.TEXT if is_you else theme.TEXT_DIM
        if not p.is_alive:
            name_color = (120, 125, 138)
        text(surface, name, theme.FS_TINY, name_color, (row.x + 6 * theme.S, row.centery), center=False)

        # 血量
        hp_color = theme.HP_GREEN if p.hp > 50 else (theme.HP_YELLOW if p.hp > 20 else theme.HP_RED)
        if not p.is_alive:
            hp_color = (120, 125, 138)
        text(
            surface,
            f"{p.hp}",
            theme.FS_TINY,
            hp_color,
            (row.x + row.width - 70 * theme.S, row.centery),
            center=False,
        )

        # 等级
        text(
            surface,
            f"Lv{p.level}",
            theme.FS_MICRO,
            theme.TEXT_DIM,
            (row.x + row.width - 30 * theme.S, row.centery),
            center=False,
        )
        y += theme.ROSTER_ROW_H
    return rows


def piece_item_badges(surface: pygame.Surface, rect: pygame.Rect, equip: list) -> None:
    """在棋子头像下方画装备小图标。"""
    if not equip:
        return
    n = len(equip)
    gap = 14 * theme.S
    start_x = rect.centerx - (n - 1) * gap // 2
    y = rect.bottom - 16 * theme.S
    for k, it in enumerate(equip):
        cx = start_x + k * gap
        r = pygame.Rect(0, 0, 12 * theme.S, 12 * theme.S)
        r.center = (cx, y)
        color = theme.GOLD if "+" in it.item_id else theme.BORDER
        pygame.draw.rect(surface, color, r, border_radius=3)
        pygame.draw.rect(surface, (12, 13, 18), r, width=1, border_radius=3)

"""装备栏与 8 人战况面板的绘制与命中检测。"""

from __future__ import annotations

import pygame

from core.items import is_special_item, load_items

from . import theme
from .assets import text
from .item_art import draw_item_badge
from .widgets import panel, tooltip


# ---------- 装备栏（无上限背包：每页 3x4 格 + 滚轮翻页） ----------


def bench_page() -> int:
    """每页可见格子数（3 列 x 4 行 = 12）。"""
    return theme.ITEM_COLS * theme.ITEM_ROWS


def page_count(count: int) -> int:
    """count 件装备共占几页（至少 1 页）。"""
    page = bench_page()
    return max(1, (count + page - 1) // page)


def clamp_scroll(scroll: int, count: int) -> int:
    """把滚动偏移限制在可浏览范围内（0 .. 尾页首格）。"""
    if count <= 0:
        return 0
    page = bench_page()
    return max(0, min(scroll, max(0, count - page)))


def item_view_rect(view: int) -> pygame.Rect:
    """第 view 个可见位（0..页内）的格子矩形。"""
    col = view % theme.ITEM_COLS
    row = view // theme.ITEM_COLS
    x = theme.ITEM_BENCH_X + theme.ITEM_PAD_X + col * (theme.ITEM_CELL + theme.ITEM_GAP)
    y = theme.ITEM_BENCH_Y + theme.ITEM_TITLE_H + row * (theme.ITEM_CELL + theme.ITEM_GAP)
    return pygame.Rect(x, y, theme.ITEM_CELL, theme.ITEM_CELL)


def item_view_at(pos) -> int | None:
    """屏幕坐标命中的可见位（0..页内）；不在网格上返回 None。"""
    for v in range(bench_page()):
        if item_view_rect(v).collidepoint(pos):
            return v
    return None


def item_slot_rect(index: int, scroll: int = 0, count: int = 0) -> pygame.Rect:
    """绝对下标 index 的装备在当前滚动窗口内的格子；不在窗口内返回空矩形。"""
    view = index - clamp_scroll(scroll, count)
    if view < 0 or view >= bench_page():
        return pygame.Rect(0, 0, 0, 0)
    return item_view_rect(view)


def item_slot_at(pos, scroll: int = 0, count: int = 0) -> int | None:
    """屏幕坐标 -> 装备栏绝对下标（叠加滚动偏移）；不在网格/窗口内返回 None。"""
    view = item_view_at(pos)
    if view is None:
        return None
    return clamp_scroll(scroll, count) + view


def item_color(item_id: str) -> tuple:
    """高级装备 / 特殊工具（金制拆卸器）用金色描边，基础装备用灰白。"""
    if "+" in item_id or is_special_item(item_id):
        return theme.GOLD
    return theme.BORDER


# 装备图标绘制统一在 render/item_art.py：有贴图显贴图，缺图回退程序化图标。
# 这里重新导出，保持既有调用方（装备栏 / 自选台 / 拖拽跟手）的导入路径不变。
from .item_art import draw_item_icon  # noqa: F401  (re-export)


def draw_item_bench(
    surface: pygame.Surface, bench: list, hover: int | None = None, scroll: int = 0
) -> None:
    """画装备栏面板：标题（数量 + 翻页指示）+ 当前窗口内 3x4 格子。

    scroll 是列表开头偏移；库存超过一页时右上角显示 ▲/▼，鼠标悬停本面板滚轮翻页。
    装备栏背包不设上限，始终能装下、看得到、取得出。
    """
    bg = pygame.Rect(
        theme.ITEM_BENCH_X, theme.ITEM_BENCH_Y, theme.ITEM_BENCH_W, theme.ITEM_BENCH_H
    )
    panel(surface, bg, theme.PANEL, radius=10, border=theme.BORDER)

    count = len(bench)
    text(
        surface,
        f"装备（{count}）",
        theme.FS_TINY,
        theme.TEXT,
        (bg.centerx, bg.y + 9 * theme.S),
        center=True,
    )

    # 右上角翻页指示：亮起代表还能往上/往下滚
    if count > bench_page():
        sc = clamp_scroll(scroll, count)
        up = theme.GOLD if sc > 0 else theme.TEXT_DIM
        down = theme.GOLD if sc + bench_page() < count else theme.TEXT_DIM
        text(surface, "▲", theme.FS_MICRO, up, (bg.right - 13 * theme.S, bg.y + 3 * theme.S))
        text(surface, "▼", theme.FS_MICRO, down, (bg.right - 13 * theme.S, bg.y + 15 * theme.S))

    sc = clamp_scroll(scroll, count)
    for view in range(bench_page()):
        rect = item_view_rect(view)
        i = sc + view
        if i < count:
            draw_item_icon(surface, rect, bench[i].item_id)
        else:
            panel(surface, rect, (24, 26, 33), radius=8, border=(44, 48, 60))
        if hover is not None and i == hover:
            pygame.draw.rect(surface, theme.ACCENT, rect, width=2, border_radius=8)


def draw_combine_candidates(
    surface: pygame.Surface,
    bench: list,
    drag_item,
    drag_slot: int,
    scroll: int = 0,
) -> None:
    """拖起一件基础装备时，给装备栏里'能合成'的目标格子描金色高亮。"""
    from core.items import combine_key

    sc = clamp_scroll(scroll, len(bench))
    for i, it in enumerate(bench):
        if i == drag_slot or it is drag_item:
            continue
        view = i - sc
        if view < 0 or view >= bench_page():
            continue
        if combine_key(drag_item.item_id, it.item_id):
            rect = item_view_rect(view)
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
    """在棋子头像下方画装备小图标（有贴图显贴图）。"""
    if not equip:
        return
    n = len(equip)
    gap = 14 * theme.S
    start_x = rect.centerx - (n - 1) * gap // 2
    y = rect.bottom - 16 * theme.S
    for k, it in enumerate(equip):
        cx = start_x + k * gap
        draw_item_badge(surface, (cx, y), it.item_id)

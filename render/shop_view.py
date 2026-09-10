"""备战席与商店的绘制。

S2 的拖拽会复用这里的 bench_slot_at / shop_card_at 做命中检测。
卡片按费用套稀有度配色（1 灰 / 2 绿 / 3 蓝 / 4 紫 / 5 金），和棋子头像的描边同源。
"""

from __future__ import annotations

import math

import pygame

from core.loader import load_units
from core.player import odds_for_level
from core.shop import REFRESH_COST

from . import theme
from .assets import text, text_size
from .board_view import PieceVisual, draw_piece, shop_card_art, trait_tag, visual_from_tid
from .item_art import draw_item_badge
from .widgets import dim_overlay, panel

# ---------- 命中检测 ----------


def bench_slot_rect(index: int) -> pygame.Rect:
    return pygame.Rect(
        theme.BENCH_X + index * (theme.BENCH_CELL + theme.BENCH_GAP),
        theme.BENCH_Y,
        theme.BENCH_CELL,
        theme.BENCH_CELL,
    )


def bench_slot_at(pos) -> int | None:
    for i in range(theme.BENCH_SLOTS):
        if bench_slot_rect(i).collidepoint(pos):
            return i
    return None


def shop_card_rect(index: int) -> pygame.Rect:
    return pygame.Rect(
        theme.SHOP_X + index * (theme.SHOP_CARD_W + theme.SHOP_GAP),
        theme.SHOP_Y,
        theme.SHOP_CARD_W,
        theme.SHOP_CARD_H,
    )


def shop_card_at(pos) -> int | None:
    for i in range(theme.SHOP_SLOTS):
        if shop_card_rect(i).collidepoint(pos):
            return i
    return None


# ---------- 浮层几何（绘制与命中检测共用同一份，避免两处漂移） ----------


def shop_panel_rect() -> pygame.Rect:
    """浮层面板外框：点它之外即关闭商店。"""
    return pygame.Rect(
        theme.SHOP_PANEL_X, theme.SHOP_PANEL_Y, theme.SHOP_PANEL_W, theme.SHOP_PANEL_H
    )


def shop_refresh_rect() -> pygame.Rect:
    return pygame.Rect(
        theme.SHOP_REFRESH_X,
        theme.SHOP_REFRESH_Y,
        theme.SHOP_REFRESH_W,
        theme.SHOP_REFRESH_H,
    )


def shop_lock_rect() -> pygame.Rect:
    return pygame.Rect(
        theme.SHOP_LOCK_X, theme.SHOP_LOCK_Y, theme.SHOP_LOCK_W, theme.SHOP_LOCK_H
    )


def shop_close_rect() -> pygame.Rect:
    """右上关闭 ✕（正方形，边长取 SHOP_CLOSE_W）。"""
    size = theme.SHOP_CLOSE_W
    return pygame.Rect(theme.SHOP_CLOSE_X, theme.SHOP_CLOSE_Y, size, size)


# ---------- 绘制 ----------


def draw_bench(surface: pygame.Surface, bench, team: str = "blue") -> None:
    for i in range(theme.BENCH_SLOTS):
        rect = bench_slot_rect(i)
        panel(surface, rect, theme.PANEL, radius=8, border=theme.BORDER)
        if i < len(bench):
            p = bench[i]
            tpl = load_units()[p.tid]
            tag, color = trait_tag(tpl.traits)
            v = PieceVisual(
                name=tpl.name,
                team=team,
                tag=tag,
                tag_color=color,
                star=p.star,
                tid=p.tid,
                cost=tpl.cost,
            )
            draw_piece(surface, rect, v)
            if p.equip:
                _bench_equip_badges(surface, rect, p.equip)


def _bench_equip_badges(surface: pygame.Surface, rect: pygame.Rect, equip: list) -> None:
    n = min(len(equip), 3)
    gap = max(10, int(12 * theme.S))
    start_x = rect.centerx - (n - 1) * gap // 2
    y = rect.bottom - max(4, int(5 * theme.S))
    for k in range(n):
        it = equip[k]
        cx = start_x + k * gap
        draw_item_badge(surface, (cx, y), it.item_id)


def draw_shop(
    surface: pygame.Surface,
    slots,
    hints: list[int] | None = None,
    t: float = 0.0,
) -> None:
    """商店卡：名字 + 费用徽章 + 稀有度描边。

    hints 与 slots 等长：hints[i] 为 2/3 表示再买这张即可合成到对应星级
    （需求2：可升星提示），0/None 不标记。t 为全局时间，用来做呼吸光环。
    """
    s = theme.S

    for i, item in enumerate(slots):
        rect = shop_card_rect(i)
        if item.sold:
            panel(surface, rect, (24, 26, 33), radius=10, border=(44, 48, 60))
            text(surface, "已购入", theme.FS_SMALL, theme.TEXT_DIM, rect.center, center=True)
            continue

        tpl = load_units()[item.tid]
        rar = theme.rarity(item.cost)
        up = hints[i] if hints else 0

        # 卡面主体：有贴图原图铺满整卡，无贴图用渐变底+放大程序头像，
        # 底部渐暗带含名字，整体已按圆角裁好并缓存。
        radius = max(2, int(10 * s))
        surface.blit(shop_card_art(item.tid, rect.size, radius), rect.topleft)
        # 稀有度描边（盖在主体边沿，标注费用档位）
        pygame.draw.rect(
            surface, rar["edge"], rect, width=max(2, int(2 * s)), border_radius=radius
        )

        # 可升星提示（需求2）：金色呼吸外框 + 左上角星级徽章
        if up >= 2:
            pulse = 0.5 + 0.5 * math.sin(t * 5)
            ring = theme.mix(theme.GOLD, (255, 240, 190), 0.3 + 0.6 * pulse)
            pygame.draw.rect(
                surface,
                ring,
                rect.inflate(int(9 * s), int(9 * s)),
                width=max(2, int(2 * s)),
                border_radius=int(13 * s),
            )
            upb = pygame.Rect(0, 0, int(38 * s), int(22 * s))
            upb.topleft = (rect.x + 10 * s, rect.y + int(rect.height * 0.20))
            panel(surface, upb, theme.GOLD, radius=max(2, 4 * s), border=(12, 13, 18), width=1)
            text(surface, f"升{up}星", theme.FS_TINY, (22, 16, 4), upb.center, center=True)

        # 费用徽章
        badge = pygame.Rect(0, 0, int(34 * s), int(22 * s))
        badge.topright = (rect.right - 10 * s, rect.y + int(rect.height * 0.20))
        panel(surface, badge, rar["edge"], radius=max(2, 4 * s), border=(12, 13, 18), width=1)
        text(surface, str(item.cost), theme.FS_SMALL, (16, 18, 24), badge.center, center=True)


def _popup_button(surface: pygame.Surface, rect: pygame.Rect, label: str, color) -> None:
    """浮层按钮：hover 提亮 + 白描边，与 widgets.Button 观感一致但不持有状态。"""
    hover = rect.collidepoint(pygame.mouse.get_pos())
    base = tuple(min(255, c + 26) for c in color) if hover else color
    panel(surface, rect, base, radius=8)
    pygame.draw.rect(surface, (255, 255, 255, 40), rect, width=1, border_radius=8)
    text(surface, label, theme.FS_SMALL, (255, 255, 255), rect.center, center=True)


def draw_shop_odds(surface: pygame.Surface, level: int) -> None:
    """一行刷新概率：费用方块（稀有度色）+ 百分比，等级越高高费卡概率越大。"""
    s = theme.S
    odds = odds_for_level(level)
    x = theme.SHOP_ODDS_X
    text(
        surface,
        "刷新概率",
        theme.FS_TINY,
        theme.TEXT_DIM,
        (x - int(96 * s), theme.SHOP_ODDS_Y + int(3 * s)),
    )
    for cost in sorted(odds):
        pct = odds[cost]
        box = pygame.Rect(x, theme.SHOP_ODDS_Y, theme.SHOP_ODDS_BOX, theme.SHOP_ODDS_BOX)
        panel(surface, box, theme.rarity(cost)["edge"], radius=4, border=(12, 13, 18), width=1)
        text(surface, str(cost), theme.FS_MICRO, (16, 18, 24), box.center, center=True)
        text(
            surface,
            f"{pct}%",
            theme.FS_TINY,
            theme.TEXT if pct > 0 else theme.TEXT_DIM,
            (box.right + int(30 * s), box.centery),
            center=True,
        )
        x += theme.SHOP_ODDS_GAP


def draw_shop_popup(
    surface: pygame.Surface,
    slots,
    level: int,
    hints: list[int] | None = None,
    locked: bool = False,
    t: float = 0.0,
) -> None:
    """商店浮层：遮罩 + 面板 + 标题 + 卡面 + 概率行 + 刷新/锁定/关闭。

    打开时机与命中检测都在 app_state；这里只按 theme 里的浮层几何绘制。
    """
    s = theme.S
    surface.blit(dim_overlay((theme.WINDOW_W, theme.WINDOW_H), 150), (0, 0))

    rect = shop_panel_rect()
    panel(surface, rect, theme.PANEL, radius=int(14 * s), border=theme.BORDER, width=2)

    title = "商店"
    text(surface, title, theme.FS_TITLE, theme.TEXT, (rect.x + int(22 * s), rect.y + int(14 * s)))
    text(
        surface,
        f"{level} 级",
        theme.FS_SMALL,
        theme.GOLD,
        (
            rect.x + int(22 * s) + text_size(title, theme.FS_TITLE)[0] + int(12 * s),
            rect.y + int(24 * s),
        ),
    )

    draw_shop(surface, slots, hints=hints, t=t)
    draw_shop_odds(surface, level)

    _popup_button(surface, shop_refresh_rect(), f"刷新 {REFRESH_COST} 金", theme.ACCENT)
    _popup_button(
        surface,
        shop_lock_rect(),
        "已锁定" if locked else "锁定商店",
        theme.GOLD if locked else (70, 74, 86),
    )

    close = shop_close_rect()
    closing = close.collidepoint(pygame.mouse.get_pos())
    panel(surface, close, (86, 92, 108) if closing else (52, 56, 68), radius=int(8 * s))
    text(surface, "✕", theme.FS_SMALL, theme.TEXT, close.center, center=True)

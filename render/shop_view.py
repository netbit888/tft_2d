"""备战席与商店的绘制。

S2 的拖拽会复用这里的 bench_slot_at / shop_card_at 做命中检测。
卡片按费用套稀有度配色（1 灰 / 2 绿 / 3 蓝 / 4 紫 / 5 金），和棋子头像的描边同源。
"""

from __future__ import annotations

import pygame

from core.loader import load_traits, load_units

from . import theme
from .assets import render, text
from .board_view import PieceVisual, draw_piece, trait_tag
from .widgets import panel

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
    half = max(3, int(4 * theme.S))
    for k in range(n):
        it = equip[k]
        cx = start_x + k * gap
        color = theme.GOLD if "+" in it.item_id else theme.BORDER
        pts = [(cx, y - half), (cx + half, y), (cx, y + half), (cx - half, y)]
        pygame.draw.polygon(surface, color, pts)
        pygame.draw.polygon(surface, (12, 13, 18), pts, width=1)


def _rarity_header(surface: pygame.Surface, rect: pygame.Rect, rar: dict) -> None:
    """卡片顶部一条渐变高光，颜色跟着稀有度走。"""
    h = max(3, int(rect.height * 0.22))
    s = theme.S
    steps = max(3, h // max(1, s))
    for i in range(steps):
        t = 1 - i / steps
        y = rect.y + i * (h // steps)
        color = theme.mix(rar["fill"], rar["edge"], 0.25 + 0.5 * t)
        pygame.draw.rect(
            surface, color, (rect.x + 1, y, rect.width - 2, h // steps + 1), border_radius=0
        )


def _star_pips(surface: pygame.Surface, x: int, y: int, count: int, pip: int) -> None:
    """升星进度：实心小菱形表示已持有的张数。"""
    gap = int(pip * 2.0)
    dark = (44, 47, 58)
    for i in range(3):
        cx = x + i * gap
        half = pip
        pts = [(cx, y - half), (cx + half, y), (cx, y + half), (cx - half, y)]
        pygame.draw.polygon(surface, theme.GOLD if i < count else dark, pts)
        pygame.draw.polygon(surface, (12, 13, 18), pts, width=1)


def draw_shop(
    surface: pygame.Surface, slots, owned: dict[str, int] | None = None, pool=None
) -> None:
    """owned 是 tid -> 持有数量的映射（升星进度），pool 用来显示卡池余量。"""
    owned = owned or {}
    traits_data = load_traits()
    s = theme.S

    for i, item in enumerate(slots):
        rect = shop_card_rect(i)
        if item.sold:
            panel(surface, rect, (24, 26, 33), radius=10, border=(44, 48, 60))
            text(surface, "已购入", theme.FS_SMALL, theme.TEXT_DIM, rect.center, center=True)
            continue

        tpl = load_units()[item.tid]
        rar = theme.rarity(item.cost)

        panel(surface, rect, rar["fill"], radius=10, border=rar["edge"], width=max(2, 2 * s))
        _rarity_header(surface, rect, rar)

        # 名称
        text(
            surface,
            tpl.name,
            theme.FS_NORMAL,
            theme.TEXT,
            (rect.x + 12 * s, rect.y + int(rect.height * 0.26)),
        )

        # 费用徽章
        badge = pygame.Rect(0, 0, int(34 * s), int(22 * s))
        badge.topright = (rect.right - 10 * s, rect.y + int(rect.height * 0.20))
        panel(surface, badge, rar["edge"], radius=max(2, 4 * s), border=(12, 13, 18), width=1)
        text(surface, str(item.cost), theme.FS_SMALL, (16, 18, 24), badge.center, center=True)

        # 羁绊标签
        x = rect.x + 12 * s
        y = rect.y + int(rect.height * 0.48)
        for t in tpl.traits:
            name = traits_data.get(t, {}).get("name", t)
            color = theme.TRAIT_COLORS.get(t, theme.TRAIT_FALLBACK)
            w = len(name) * theme.FS_TINY + int(16 * s)
            tag = pygame.Rect(x, y, w, int(22 * s))
            panel(surface, tag, color, radius=max(2, 5 * s), border=(12, 13, 18), width=1)
            text(surface, name, theme.FS_TINY, (255, 255, 255), tag.center, center=True)
            x += w + 8 * s

        # 属性摘要 + 卡池余量
        info = f"HP {tpl.hp:.0f}  AD {tpl.ad:.0f}  射程 {tpl.attack_range}"
        left = pool.count(item.tid) if pool is not None else -1
        if left >= 0:
            info += f"  剩 {left}"
        color = theme.TEXT_DIM if left != 0 else theme.HP_RED
        text(
            surface,
            info,
            theme.FS_TINY,
            color,
            (rect.x + 12 * s, rect.bottom - int(24 * s)),
        )

        # 升星进度
        count = owned.get(item.tid, 0)
        if count:
            _star_pips(
                surface,
                rect.right - int(52 * s),
                rect.bottom - int(18 * s),
                min(3, count),
                max(3, int(5 * s)),
            )
            tip = "可升星！" if count >= 2 else "1/3"
            img = render(tip, theme.FS_MICRO, theme.GOLD if count >= 2 else theme.TEXT_DIM)
            surface.blit(img, (rect.right - img.get_width() - int(12 * s), rect.y + int(rect.height * 0.48) + int(24 * s)))

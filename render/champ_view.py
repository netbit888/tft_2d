"""棋子自选栏：部署期按 F3 打开，按费用分成 1~5 费五页。

- 页签与内容：顶部 1~5 费五个 tab，每页列出该费用的全部棋子（顺序同 units.json）；
- 点任意格子：免费获得 1 个该棋子到备战席（可连点），自动三合一升星；
- 面板 / 页签 / 关闭 / 遮罩 / 脚注完全复用 armory_view 的通用自选台骨架，
  差别只在每格内容：棋子头像 + 名字，而非装备图标。
"""

from __future__ import annotations

import pygame

from core.loader import load_units

from . import theme
from .armory_view import draw_overlay, overlay_geometry
from .assets import text
from .board_view import draw_piece, visual_from_tid

CHAMP_COSTS = (1, 2, 3, 4, 5)
TAB_LABELS = tuple(f"{c}费" for c in CHAMP_COSTS)
TITLE = "棋子自选栏"
FOOTER = "点击任意棋子免费获得 1 个（可连点）｜同名 3 张自动升星｜按 F3 / ESC 关闭"


def champ_entries(cost: int) -> list[str]:
    """某一费用的全部棋子 tid（顺序保持 units.json，不含没数据的）。"""
    return [tid for tid, tpl in load_units().items() if tpl.cost == cost]


def champ_geometry(cost: int) -> dict:
    """某一费用页的几何（布局随格子行数自适应）。"""
    return overlay_geometry(champ_entries(cost), len(CHAMP_COSTS))


def _champ_cell(surface: pygame.Surface, rect: pygame.Rect, tid: str, hover: bool) -> None:
    """棋子自选栏格子：棋子头像 + 名字，hover 描高亮框。"""
    s = theme.S
    tpl = load_units()[tid]
    size = int(58 * s)
    v = visual_from_tid(tid, 1, "blue")
    r = pygame.Rect(0, 0, size, size)
    r.center = (rect.centerx, rect.y + int(34 * s))
    draw_piece(surface, r, v)
    text(
        surface,
        tpl.name,
        theme.FS_MICRO,
        theme.TEXT,
        (rect.centerx, rect.bottom - int(13 * s)),
        center=True,
    )
    if hover:
        pygame.draw.rect(surface, theme.ACCENT, rect.inflate(-4 * s, -4 * s), width=2, border_radius=8)


def draw_champ_picker(surface: pygame.Surface, cost: int) -> None:
    """画棋子自选栏当前费用页（含全屏遮罩、tab 条、格子与脚注）。"""
    if cost not in CHAMP_COSTS:
        cost = CHAMP_COSTS[0]
    draw_overlay(
        surface,
        champ_entries(cost),
        CHAMP_COSTS.index(cost),
        TAB_LABELS,
        TITLE,
        FOOTER,
        _champ_cell,
    )

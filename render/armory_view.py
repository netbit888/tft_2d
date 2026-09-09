"""装备自选台（成装 / 散件双页）：部署期按 F2 打开。

- 页 0「成装」：列出全部成装与特殊工具（金制拆卸器），点任意成装获得 1 件（可连点）；
  金制拆卸器只在这里出现：拖到棋子身上卸下其全部装备回装备栏，道具不消耗；
- 页 1「散件」：列出全部基础装备，点任意散件获得 1 件（可连点）；
  散件可直接佩戴，也可在装备栏 / 棋子身上两两拖拽合成成装；
- 顶部 tab 切换页面，面板高度随当前页行数自适应；
  几何计算集中在 armory_geometry(tab)，点击命中与绘制共用同一份数据。
"""

from __future__ import annotations

import math

import pygame

from core.items import base_item_ids, item_name, load_items, special_item_ids

from . import theme
from .assets import render, text
from .item_view import draw_item_icon
from .widgets import dim_overlay, panel

# 与 tab 值 0/1 对应的文字
TAB_LABELS = ("成装", "散件")
TAB_TITLES = ("成装自选台", "散件自选台")
TAB_FOOTERS = (
    "点击任意成装获得 1 件（可连点）｜金制拆卸器：拖到棋子身上卸下全部装备，不消耗｜按 F2 / ESC 关闭",
    "点击任意散件获得 1 件（可连点）｜散件可直接佩戴，也可两两拖拽合成成装｜按 F2 / ESC 关闭",
)


def armory_entries(tab: int = 0) -> list[str]:
    """某一页的条目顺序：页 0=全部成装按数据序排布 + 特殊工具最后；页 1=全部基础散件。"""
    if tab == 1:
        return base_item_ids()
    return list(load_items()["combine"].keys()) + list(special_item_ids())


def armory_geometry(tab: int = 0) -> dict:
    """计算面板矩形、关闭按钮、顶部 tab 与每个格子的命中区（纯几何，绘制/点击共用）。

    面板高度随当前页行数自适应（散件页内容少、面板矮），水平居中位置不变。
    """
    s = theme.S
    cols = theme.ARMORY_COLS
    cell = theme.ARMORY_CELL
    step_x = theme.ARMORY_STEP_X
    step_y = theme.ARMORY_STEP_Y
    pad = theme.ARMORY_PAD
    title_h = theme.ARMORY_TITLE_H
    tab_h = theme.ARMORY_TAB_H
    foot_h = theme.ARMORY_FOOT_H
    entries = armory_entries(tab)
    rows = math.ceil(len(entries) / cols)

    content_w = (cols - 1) * step_x + cell
    content_h = rows * step_y
    w = pad * 2 + content_w
    h = pad * 2 + title_h + tab_h + content_h + foot_h
    panel_r = pygame.Rect(0, 0, w, h)
    panel_r.center = (theme.WINDOW_W // 2, theme.WINDOW_H // 2)

    grid_x0 = panel_r.x + pad
    grid_y0 = panel_r.y + pad + title_h + tab_h

    cells: list[dict] = []
    for k, item_id in enumerate(entries):
        col, row = k % cols, k // cols
        r = pygame.Rect(grid_x0 + col * step_x, grid_y0 + row * step_y, cell, step_y)
        cells.append({"rect": r, "item_id": item_id})

    close = pygame.Rect(0, 0, int(30 * s), int(30 * s))
    close.topright = (panel_r.right - int(10 * s), panel_r.y + int(10 * s))

    # 顶部 tab 条（标题与网格之间，整组水平居中）
    tab_w = int(110 * s)
    tab_gap = int(12 * s)
    tab_y = panel_r.y + pad + title_h + int(6 * s)
    tab_hh = tab_h - int(12 * s)
    group_w = tab_w * 2 + tab_gap
    tab_x0 = panel_r.centerx - group_w // 2
    tabs = [
        {"rect": pygame.Rect(tab_x0, tab_y, tab_w, tab_hh), "tab": 0},
        {"rect": pygame.Rect(tab_x0 + tab_w + tab_gap, tab_y, tab_w, tab_hh), "tab": 1},
    ]
    return {
        "panel": panel_r,
        "close": close,
        "tabs": tabs,
        "cells": cells,
        "title_y": panel_r.y + pad + title_h // 2,
        "footer_y": panel_r.bottom - foot_h // 2,
    }


def draw_armory(surface: pygame.Surface, tab: int = 0) -> None:
    """画整个自选台当前页（含全屏遮罩、tab 条、格子网格与提示脚注）。"""
    g = armory_geometry(tab)
    surface.blit(dim_overlay((theme.WINDOW_W, theme.WINDOW_H)), (0, 0))
    panel(surface, g["panel"], theme.PANEL, radius=14, border=theme.BORDER)

    text(
        surface,
        TAB_TITLES[tab],
        theme.FS_NORMAL,
        theme.TEXT,
        (g["panel"].centerx, g["title_y"]),
        center=True,
    )

    # 右上角关闭按钮
    close = g["close"]
    mouse = pygame.mouse.get_pos()
    hover = close.collidepoint(mouse)
    pygame.draw.circle(
        surface, theme.PANEL_LIGHT if hover else (46, 50, 62), close.center, close.w // 2
    )
    pygame.draw.circle(surface, theme.BORDER, close.center, close.w // 2, width=1)
    img = render("X", theme.FS_SMALL, theme.TEXT if hover else theme.TEXT_DIM)
    surface.blit(img, (close.centerx - img.get_width() // 2, close.centery - img.get_height() // 2))

    # 顶部 tab：当前页高亮，未选页 hover 增亮
    for t in g["tabs"]:
        r = t["rect"]
        active = t["tab"] == tab
        th = r.collidepoint(mouse)
        if active:
            face, fg = theme.ACCENT, (255, 255, 255)
        elif th:
            face, fg = theme.PANEL_LIGHT, theme.TEXT
        else:
            face, fg = (40, 43, 53), theme.TEXT_DIM
        pygame.draw.rect(surface, face, r, border_radius=8)
        text(surface, TAB_LABELS[t["tab"]], theme.FS_SMALL, fg, r.center, center=True)

    s = theme.S
    icon_size = theme.ITEM_CELL
    special_ids = special_item_ids()
    for c in g["cells"]:
        r = c["rect"]
        cell_hover = r.collidepoint(mouse)
        icon = pygame.Rect(0, 0, icon_size, icon_size)
        icon.midtop = (r.centerx, r.y + int(6 * s))
        draw_item_icon(surface, icon, c["item_id"])
        if c["item_id"] in special_ids or "+" in c["item_id"]:
            name_color = theme.GOLD
        else:
            name_color = theme.TEXT
        text(
            surface,
            item_name(c["item_id"]),
            theme.FS_MICRO,
            name_color,
            (r.centerx, r.y + int(6 * s) + icon.height + int(6 * s)),
            center=True,
        )
        if cell_hover:
            pygame.draw.rect(surface, theme.ACCENT, r.inflate(-4 * s, -4 * s), width=2, border_radius=8)

    text(
        surface,
        TAB_FOOTERS[tab],
        theme.FS_TINY,
        theme.TEXT_DIM,
        (g["panel"].centerx, g["footer_y"]),
        center=True,
    )

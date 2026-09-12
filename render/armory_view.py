"""装备自选台（成装 / 散件双页）：部署期按 F2 打开。

- 页 0「成装」：列出全部成装与特殊工具（金制拆卸器），点任意成装获得 1 件（可连点）；
  金制拆卸器只在这里出现：拖到棋子身上卸下其全部装备回装备栏，道具不消耗；
- 页 1「散件」：列出全部基础装备，点任意散件获得 1 件（可连点）；
  散件可直接佩戴，也可在装备栏 / 棋子身上两两拖拽合成成装；
- 顶部 tab 切换页面，面板高度随当前页行数自适应；
  几何计算集中在 overlay_geometry / armory_geometry，点击命中与绘制共用同一份数据。

模块同时提供通用的自选台骨架（overlay_geometry + draw_overlay）：顶部标题、右上
关闭、顶部 N 个页签、网格格子与脚注；棋子自选栏（render/champ_view，F3）复用这套
骨架，只是把"每格画装备图标"换成"每格画棋子头像"。
"""

from __future__ import annotations

import math

import pygame

from core.items import artifact_item_ids, base_item_ids, is_artifact_item, item_name, load_items, special_item_ids

from . import theme
from .assets import render, text
from .item_view import draw_item_icon
from .widgets import dim_overlay, panel

# 与 tab 值 0/1/2 对应的文字：成装 / 散件 / 神器
TAB_LABELS = ("成装", "散件", "神器")
TAB_TITLES = ("成装自选台", "散件自选台", "神器自选台")
TAB_FOOTERS = (
    "点击任意成装获得 1 件（可连点）｜金制拆卸器：拖到棋子身上卸下全部装备，不消耗｜按 F2 / ESC 关闭",
    "点击任意散件获得 1 件（可连点）｜散件可直接佩戴，也可两两拖拽合成成装｜按 F2 / ESC 关闭",
    "神器为具名强力件：点击获得 1 件（可连点），直接拖到棋子身上佩戴（不可合成）｜按 F2 / ESC 关闭",
)


def armory_entries(tab: int = 0) -> list[str]:
    """某一页的条目顺序：
    页 0=全部成装按数据序排布 + 特殊工具最后；页 1=全部基础散件；页 2=全部神器。"""
    if tab == 1:
        return base_item_ids()
    if tab == 2:
        return artifact_item_ids()
    return list(load_items()["combine"].keys()) + list(special_item_ids())


def overlay_geometry(entries: list, tab_count: int) -> dict:
    """通用自选台几何：面板矩形、关闭按钮、顶部 tab 与每个格子的命中区。

    entries 是当前页的条目（顺序与格子一一对应）；tab_count 决定顶部页签数量。
    面板高度随行数自适应、水平居中，绘制与点击共用同一份数据。
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
    rows = max(1, math.ceil(len(entries) / cols))

    content_w = (cols - 1) * step_x + cell
    content_h = rows * step_y
    w = pad * 2 + content_w
    h = pad * 2 + title_h + tab_h + content_h + foot_h
    panel_r = pygame.Rect(0, 0, w, h)
    panel_r.center = (theme.WINDOW_W // 2, theme.WINDOW_H // 2)

    grid_x0 = panel_r.x + pad
    grid_y0 = panel_r.y + pad + title_h + tab_h

    cells: list[dict] = []
    for k, entry in enumerate(entries):
        col, row = k % cols, k // cols
        r = pygame.Rect(grid_x0 + col * step_x, grid_y0 + row * step_y, cell, step_y)
        cells.append({"rect": r, "entry": entry})

    close = pygame.Rect(0, 0, int(30 * s), int(30 * s))
    close.topright = (panel_r.right - int(10 * s), panel_r.y + int(10 * s))

    # 顶部 tab 条（标题与网格之间，整组水平居中）
    tab_w = int(110 * s)
    tab_gap = int(12 * s)
    tab_y = panel_r.y + pad + title_h + int(6 * s)
    tab_hh = tab_h - int(12 * s)
    group_w = tab_w * tab_count + tab_gap * (tab_count - 1)
    tab_x0 = panel_r.centerx - group_w // 2
    tabs = [
        {"rect": pygame.Rect(tab_x0 + i * (tab_w + tab_gap), tab_y, tab_w, tab_hh), "tab": i}
        for i in range(tab_count)
    ]
    return {
        "panel": panel_r,
        "close": close,
        "tabs": tabs,
        "cells": cells,
        "title_y": panel_r.y + pad + title_h // 2,
        "footer_y": panel_r.bottom - foot_h // 2,
    }


def armory_geometry(tab: int = 0) -> dict:
    """装备自选台某一页的几何（装备 tab 只有 0/1 两页）。"""
    return overlay_geometry(armory_entries(tab), len(TAB_LABELS))


def draw_overlay(
    surface: pygame.Surface,
    entries: list,
    active: int,
    labels: tuple[str, ...],
    title: str,
    footer: str,
    cell_paint,
) -> None:
    """通用自选台绘制：全屏遮罩、标题、关闭钮、页签、网格（内容由 cell_paint 决定）与脚注。

    cell_paint(surface, rect, entry, hover) 负责画某一个格子里的内容。
    """
    g = overlay_geometry(entries, len(labels))
    surface.blit(dim_overlay((theme.WINDOW_W, theme.WINDOW_H)), (0, 0))
    panel(surface, g["panel"], theme.PANEL, radius=14, border=theme.BORDER)

    text(
        surface,
        title,
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
        is_active = t["tab"] == active
        th = r.collidepoint(mouse)
        if is_active:
            face, fg = theme.ACCENT, (255, 255, 255)
        elif th:
            face, fg = theme.PANEL_LIGHT, theme.TEXT
        else:
            face, fg = (40, 43, 53), theme.TEXT_DIM
        pygame.draw.rect(surface, face, r, border_radius=8)
        text(surface, labels[t["tab"]], theme.FS_SMALL, fg, r.center, center=True)

    for c in g["cells"]:
        cell_paint(surface, c["rect"], c["entry"], c["rect"].collidepoint(mouse))

    text(
        surface,
        footer,
        theme.FS_TINY,
        theme.TEXT_DIM,
        (g["panel"].centerx, g["footer_y"]),
        center=True,
    )


def _item_cell(surface: pygame.Surface, rect: pygame.Rect, item_id: str, hover: bool) -> None:
    """装备自选台格子：装备图标（有贴图显贴图）+ 名字；hover 描高亮框。"""
    s = theme.S
    icon_size = theme.ITEM_CELL
    special = item_id in special_item_ids() or is_artifact_item(item_id) or "+" in item_id
    icon = pygame.Rect(0, 0, icon_size, icon_size)
    icon.midtop = (rect.centerx, rect.y + int(6 * s))
    draw_item_icon(surface, icon, item_id)
    name_color = theme.GOLD if special else theme.TEXT
    text(
        surface,
        item_name(item_id),
        theme.FS_MICRO,
        name_color,
        (rect.centerx, rect.y + int(6 * s) + icon.height + int(6 * s)),
        center=True,
    )
    if hover:
        pygame.draw.rect(surface, theme.ACCENT, rect.inflate(-4 * s, -4 * s), width=2, border_radius=8)


def draw_armory(surface: pygame.Surface, tab: int = 0) -> None:
    """画装备自选台当前页（含全屏遮罩、tab 条、格子网格与提示脚注）。"""
    draw_overlay(
        surface,
        armory_entries(tab),
        tab,
        TAB_LABELS,
        TAB_TITLES[tab],
        TAB_FOOTERS[tab],
        _item_cell,
    )

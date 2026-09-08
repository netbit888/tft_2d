"""成装自选台：部署期按 F2 打开，列出全部成装与特殊工具（金制拆卸器）。

- 点任意成装 -> 直接获得 1 件（可连点，每次 1 件）；
- 金制拆卸器只在这里出现：拖到棋子身上卸下其全部装备回装备栏，道具不消耗；
- 几何计算集中在 armory_geometry()，点击命中与绘制共用同一份数据。
"""

from __future__ import annotations

import math

import pygame

from core.items import item_name, load_items, special_item_ids

from . import theme
from .assets import render, text
from .item_view import draw_item_icon
from .widgets import dim_overlay, panel


def armory_entries() -> list[str]:
    """面板条目顺序：全部成装按数据顺序排布，特殊工具（金制拆卸器）放在最后。"""
    return list(load_items()["combine"].keys()) + list(special_item_ids())


def armory_geometry() -> dict:
    """计算面板矩形、关闭按钮与每个格子的命中区（纯几何，绘制/点击共用）。"""
    s = theme.S
    cols = theme.ARMORY_COLS
    cell = theme.ARMORY_CELL
    step_x = theme.ARMORY_STEP_X
    step_y = theme.ARMORY_STEP_Y
    pad = theme.ARMORY_PAD
    entries = armory_entries()
    rows = math.ceil(len(entries) / cols)

    content_w = (cols - 1) * step_x + cell
    content_h = rows * step_y
    w = pad * 2 + content_w
    h = pad * 2 + theme.ARMORY_TITLE_H + content_h + theme.ARMORY_FOOT_H
    panel_r = pygame.Rect(0, 0, w, h)
    panel_r.center = (theme.WINDOW_W // 2, theme.WINDOW_H // 2)

    grid_x0 = panel_r.x + pad
    grid_y0 = panel_r.y + pad + theme.ARMORY_TITLE_H

    cells: list[dict] = []
    for k, item_id in enumerate(entries):
        col, row = k % cols, k // cols
        r = pygame.Rect(grid_x0 + col * step_x, grid_y0 + row * step_y, cell, step_y)
        cells.append({"rect": r, "item_id": item_id})

    close = pygame.Rect(0, 0, int(30 * s), int(30 * s))
    close.topright = (panel_r.right - int(10 * s), panel_r.y + int(10 * s))
    return {
        "panel": panel_r,
        "close": close,
        "cells": cells,
        "title_y": panel_r.y + theme.ARMORY_TITLE_H // 2,
        "footer_y": panel_r.bottom - theme.ARMORY_FOOT_H // 2,
    }


def draw_armory(surface: pygame.Surface) -> None:
    """画整个自选台（含全屏遮罩）。"""
    g = armory_geometry()
    surface.blit(dim_overlay((theme.WINDOW_W, theme.WINDOW_H)), (0, 0))
    panel(surface, g["panel"], theme.PANEL, radius=14, border=theme.BORDER)

    text(
        surface,
        "成装自选台",
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

    s = theme.S
    icon_size = theme.ITEM_CELL
    for c in g["cells"]:
        r = c["rect"]
        cell_hover = r.collidepoint(mouse)
        icon = pygame.Rect(0, 0, icon_size, icon_size)
        icon.midtop = (r.centerx, r.y + int(6 * s))
        draw_item_icon(surface, icon, c["item_id"])
        if c["item_id"] in special_item_ids() or "+" in c["item_id"]:
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
        "点击任意成装获得 1 件（可连点）｜金制拆卸器：拖到棋子身上卸下全部装备，不消耗｜按 F2 / ESC 关闭",
        theme.FS_TINY,
        theme.TEXT_DIM,
        (g["panel"].centerx, g["footer_y"]),
        center=True,
    )

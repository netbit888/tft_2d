"""底部 HUD 两个球（金铲铲风格）。

- 左下「经验球」：显示等级 + 当前/所需经验 + 升级花费，点（或按住）即买经验；
- 右下「金币球」：球顶徽章显示连胜/连败场数（0 = 连胜连败被打断），
  球心显示玩家金币，点一下打开商店浮层。

几何只读 theme（BALL_R / XP_BALL_* / GOLD_BALL_*），命中检测与绘制共用同一份数据。
"""

from __future__ import annotations

import math

import pygame

from core.player import MAX_LEVEL, upgrade_cost, xp_needed_for_level

from . import theme
from .assets import text, text_size
from .widgets import panel


# ---------- 命中检测 ----------


def ball_hit(pos, cx: int, cy: int, r: int | None = None) -> bool:
    """点是否落在某个球的圆形范围内。"""
    radius = theme.BALL_R if r is None else r
    return math.hypot(pos[0] - cx, pos[1] - cy) <= radius


def xp_ball_hit(pos) -> bool:
    return ball_hit(pos, theme.XP_BALL_X, theme.XP_BALL_Y)


def gold_ball_hit(pos) -> bool:
    return ball_hit(pos, theme.GOLD_BALL_X, theme.GOLD_BALL_Y)


# ---------- 绘制 ----------


def _ball_base(surface: pygame.Surface, cx: int, cy: int, rim) -> None:
    """球的公共底：外投影 + 圆盘 + 描边 + 内圈暗底。"""
    r = theme.BALL_R
    pygame.draw.circle(surface, (9, 11, 16), (cx, cy), r + int(3 * theme.S))
    pygame.draw.circle(surface, theme.PANEL, (cx, cy), r)
    pygame.draw.circle(surface, rim, (cx, cy), r, width=max(2, int(3 * theme.S)))
    pygame.draw.circle(surface, theme.BG_SOFT, (cx, cy), r - int(7 * theme.S))


def _coin(surface: pygame.Surface, center, radius: int) -> None:
    """小金币图标：金色圆盘 + 深色描边 + 中心方孔。"""
    pygame.draw.circle(surface, (120, 88, 20), center, radius)
    pygame.draw.circle(surface, theme.GOLD, center, max(1, radius - 1))
    pygame.draw.circle(surface, (150, 108, 26), center, max(1, radius // 3), width=1)


def draw_xp_ball(surface: pygame.Surface, player, t: float = 0.0) -> None:
    """左下经验球：等级 + 当前/所需经验 + 「购买经验」与花费，点它买经验。"""
    s = theme.S
    cx, cy = theme.XP_BALL_X, theme.XP_BALL_Y
    _ball_base(surface, cx, cy, theme.mix(theme.BORDER, theme.GOLD, 0.30))

    # 当前经验 / 升级所需
    if player.level >= MAX_LEVEL:
        exp_text, exp_color = "MAX", theme.GOLD
    else:
        exp_text = f"{player.xp}/{xp_needed_for_level(player.level + 1)}"
        exp_color = theme.TEXT
    text(surface, exp_text, theme.FS_SMALL, exp_color, (cx, cy - int(26 * s)), center=True)

    # 购买经验 + 花费（金币图标 + 数字），居中横排
    cost = upgrade_cost()
    coin_r = max(6, int(8 * s))
    cost_w = text_size(str(cost), theme.FS_SMALL)[0]
    group_w = coin_r * 2 + int(4 * s) + cost_w

    text(surface, "购买经验", theme.FS_SMALL, theme.TEXT, (cx, cy - int(2 * s)), center=True)
    row_y = cy + int(22 * s)
    x0 = cx - group_w // 2
    _coin(surface, (x0 + coin_r, row_y), coin_r)
    text(
        surface,
        str(cost),
        theme.FS_SMALL,
        theme.GOLD,
        (x0 + coin_r * 2 + int(4 * s) + cost_w // 2, row_y),
        center=True,
    )

    # 右下角小圆：等级
    lx, ly = cx + int(33 * s), cy + int(33 * s)
    lr = max(11, int(19 * s))
    pygame.draw.circle(surface, (10, 12, 17), (lx, ly), lr + int(2 * s))
    pygame.draw.circle(surface, theme.mix(theme.PANEL_LIGHT, theme.GOLD, 0.55), (lx, ly), lr)
    text(surface, str(player.level), theme.FS_SMALL, (26, 20, 6), (lx, ly), center=True)


def draw_gold_ball(
    surface: pygame.Surface, player, t: float = 0.0, gold: float | None = None
) -> None:
    """右下金币球：球心金币值 + 球顶连胜/连败徽章，点它打开商店。

    gold 用于传入手感数字（滚动中的显示值）；缺省直接读 player.gold。
    """
    s = theme.S
    cx, cy = theme.GOLD_BALL_X, theme.GOLD_BALL_Y
    _ball_base(surface, cx, cy, theme.mix(theme.BORDER, theme.GOLD, 0.75))

    # 球心：金币图标 + 金币数
    coin_r = max(8, int(11 * s))
    number = str(int(round(player.gold if gold is None else gold)))
    num_w = text_size(number, theme.FS_TITLE)[0]
    group_w = coin_r * 2 + int(4 * s) + num_w
    x0 = cx - group_w // 2
    _coin(surface, (x0 + coin_r, cy), coin_r)
    text(surface, number, theme.FS_TITLE, theme.GOLD, (x0 + coin_r * 2 + int(4 * s), cy - int(13 * s)))

    _draw_streak_badge(surface, cx, cy, int(getattr(player, "streak", 0)))


def _flame(surface: pygame.Surface, cx: int, cy: int, size: int, base, core) -> None:
    """程序化小火焰（不依赖字体里的 emoji）。"""
    r = size * 0.5
    outer = [
        (cx, cy - size),
        (cx + r * 0.95, cy - size * 0.05),
        (cx + r * 0.78, cy + r * 0.85),
        (cx, cy + size * 0.78),
        (cx - r * 0.78, cy + r * 0.85),
        (cx - r * 0.95, cy - size * 0.05),
    ]
    pygame.draw.polygon(surface, base, outer)
    inner = [
        (cx, cy - size * 0.42),
        (cx + r * 0.45, cy + r * 0.2),
        (cx, cy + size * 0.5),
        (cx - r * 0.45, cy + r * 0.2),
    ]
    pygame.draw.polygon(surface, core, inner)


def _draw_streak_badge(surface: pygame.Surface, cx: int, cy: int, streak: int) -> None:
    """球顶徽章：连胜（暖色）/ 连败（冷色）/ 打断归零（灰）。"""
    s = theme.S
    n = abs(streak)
    if n == 0:
        base, core, num_color = (96, 102, 116), (152, 158, 174), theme.TEXT_DIM
    elif streak > 0:
        base, core, num_color = (238, 116, 46), (255, 214, 112), theme.GOLD
    else:
        base, core, num_color = (74, 140, 224), (176, 218, 255), theme.ACCENT

    bw, bh = int(84 * s), int(32 * s)
    badge = pygame.Rect(0, 0, bw, bh)
    badge.center = (cx, cy - theme.BALL_R + int(6 * s))
    panel(
        surface,
        badge,
        (17, 19, 26),
        radius=bh // 2,
        border=theme.mix(theme.BORDER, base, 0.55),
    )

    _flame(surface, badge.x + int(20 * s), badge.centery, max(6, int(10 * s)), base, core)
    text(
        surface,
        str(n),
        theme.FS_SMALL,
        num_color,
        (badge.x + int(52 * s), badge.centery),
        center=True,
    )

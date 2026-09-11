"""战斗伤害统计面板（damage recap）。

数据来源：战斗事件流聚合（见 BattleView.stats_rows），core 不参与；
蓝/红两栏各按伤害降序列出：名字（星级）→ 伤害 / 承伤 / 治疗 / 施法。
战斗回放中按 Tab 开关，结算画面固定显示。
"""

from __future__ import annotations

import pygame

from . import theme
from .assets import text
from .widgets import panel

# 每栏最多显示的棋子行数（超出截断，按伤害降序保留前排）
MAX_ROWS = 10

# 数值列：从右往左依次排开（列距 COL_STEP）
COL_STEP = 46  # * theme.S
_COLS = (
    ("伤", "dmg", theme.GOLD),
    ("承", "taken", theme.TEXT_DIM),
    ("疗", "heal", theme.HP_GREEN),
    ("法", "casts", theme.MANA_BLUE),
)


def _fmt(v: float) -> str:
    n = int(round(v))
    return str(n) if n < 10000 else f"{n / 1000:.1f}k"


def draw_recap(
    surface: pygame.Surface, rows: list[dict], rect: pygame.Rect, title: str = "伤害统计"
) -> None:
    """在 rect 里画伤害统计：蓝左红右两栏。

    rows 是 BattleView.stats_rows() 的产出：
    [{"team", "name", "star", "dmg", "taken", "heal", "casts"}, ...]
    """
    s = theme.S
    panel(surface, rect, theme.PANEL, radius=10, border=theme.BORDER)
    text(surface, title, theme.FS_NORMAL, theme.TEXT, (rect.centerx, rect.y + 16 * s), center=True)

    blue = [r for r in rows if r["team"] == "blue"][:MAX_ROWS]
    red = [r for r in rows if r["team"] == "red"][:MAX_ROWS]

    col_w = rect.width // 2
    line_h = 22 * s
    for ci, (col_rows, team) in enumerate(((blue, "blue"), (red, "red"))):
        x = rect.x + ci * col_w
        color = theme.TEAM_COLORS[team]
        text(
            surface,
            "你的阵容" if team == "blue" else "对手阵容",
            theme.FS_SMALL,
            color,
            (x + col_w // 2, rect.y + 40 * s),
            center=True,
        )
        if not col_rows:
            text(
                surface,
                "（无数据）",
                theme.FS_TINY,
                theme.TEXT_DIM,
                (x + col_w // 2, rect.y + 64 * s),
                center=True,
            )
            continue

        # 列头：与数值列同列对齐（居中对齐各列）
        header_y = rect.y + 62 * s
        vx = x + col_w - 12 * s - COL_STEP * s // 2
        for label, _key, c in _COLS:
            text(surface, label, theme.FS_TINY, c, (vx, header_y), center=True)
            vx -= COL_STEP * s

        y = header_y + line_h
        for r in col_rows:
            star = "★" * r["star"] if r["star"] > 1 else ""
            text(surface, f"{star}{r['name']}", theme.FS_TINY, theme.TEXT, (x + 12 * s, y))
            vx = x + col_w - 12 * s - COL_STEP * s // 2
            for _label, key, c in _COLS:
                text(surface, _fmt(r[key]), theme.FS_TINY, c, (vx, y), center=True)
                vx -= COL_STEP * s
            y += line_h

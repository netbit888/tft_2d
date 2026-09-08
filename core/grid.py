"""棋盘网格。

棋盘是 7 列 × 8 行的逻辑网格，坐标为 (x=列, y=行)，单位位置是浮点坐标。
行号只用于区分半场与屏幕翻转：蓝方占行 0-3（屏幕下半），红方占行 4-7（屏幕上半）。
棋盘在渲染层画成蜂窝六边形（相邻行错半格），但战斗距离/移动仍用本文件的
行列逻辑坐标实现，绘制只负责把 (col,row) 翻译成屏幕坐标，互不耦合。
"""

from __future__ import annotations

COLS = 7
ROWS = 8

# 每方占据的行带（core 行号，含两端）：
# 蓝方 = 行 0-3，红方 = 行 4-7
TEAM_ROWS: dict[str, tuple[int, int]] = {
    "blue": (0, 3),
    "red": (4, 7),
}

# 自动补位时的行序（从交火线往自己后排排）。
# front 是靠近中线的行，back 是其后方行带。
AUTO_ROW_ORDER: dict[str, dict[str, tuple[int, ...]]] = {
    "blue": {"front": (3, 2, 1, 0), "back": (2, 1, 0)},
    "red": {"front": (4, 5, 6, 7), "back": (5, 6, 7)},
}


# ---------------------------------------------------------------------------
# 六边形格拓扑（战斗以六边形格为单位移动、每格最多一个单位）
#
# 渲染层把棋盘画成蜂窝：显示行 = ROWS-1-core_row，奇数“显示行”整行右移半格。
# 换回 core 行号后等价于：core 行为偶数的行错半格。据此定义：
#   * core 行为偶数：上/下两行的邻列是 {c, c+1}
#   * core 行为奇数：上/下两行的邻列是 {c-1, c}
#   * 同行左右邻居恒为 {c-1, c+1}
# 距离用轴向坐标（odd-r，r=显示行）闭式计算，与上述邻接关系严格一致。
# ---------------------------------------------------------------------------

def _axial(cell: tuple[int, int]) -> tuple[int, int]:
    """(col, core_row) -> 轴向坐标 (q, r)。r 取显示行（自下而上，与 core 行相反）。"""
    c, r = cell
    rr = ROWS - 1 - r                 # 显示行
    q = c - (rr - (rr & 1)) // 2
    return q, rr


def hex_neighbors(cell: tuple[int, int]) -> list[tuple[int, int]]:
    """返回 cell 在棋盘范围内的 6 个六边形邻居（无重复）。"""
    c, r = cell
    if r % 2 == 0:
        cand = ((c - 1, r), (c + 1, r),
                (c, r - 1), (c + 1, r - 1),
                (c, r + 1), (c + 1, r + 1))
    else:
        cand = ((c - 1, r), (c + 1, r),
                (c - 1, r - 1), (c, r - 1),
                (c - 1, r + 1), (c, r + 1))
    return [(cc, rr) for cc, rr in cand if 0 <= cc < COLS and 0 <= rr < ROWS]


def hex_distance(a: tuple[int, int], b: tuple[int, int]) -> int:
    """两个格子的六边形距离（邻格步数）。"""
    qa, ra = _axial(a)
    qb, rb = _axial(b)
    dq, dr = qa - qb, ra - rb
    return (abs(dq) + abs(dr) + abs(dq + dr)) // 2

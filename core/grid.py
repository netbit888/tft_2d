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


def clamp_pos(x: float, y: float) -> tuple[float, float]:
    """把坐标限制在棋盘范围内。"""
    return min(max(x, 0.0), COLS - 1), min(max(y, 0.0), ROWS - 1)


def chebyshev(a: tuple[float, float], b: tuple[float, float]) -> float:
    """棋盘距离（八方向），用于射程判定。"""
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    """欧氏距离，用于选敌与移动。"""
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def in_range(
    src: tuple[float, float], dst: tuple[float, float], attack_range: int
) -> bool:
    return chebyshev(src, dst) <= attack_range + 1e-6


def move_toward(
    pos: tuple[float, float],
    target: tuple[float, float],
    speed: float,
    dt: float,
    stop_at: float,
) -> tuple[float, float]:
    """朝 target 移动一步，保证停下时与 target 的棋盘距离不小于 stop_at。

    返回新坐标；若已在攻击距离内则原地不动。
    """
    d = chebyshev(pos, target)
    if d <= stop_at + 1e-6:
        return pos

    dx, dy = target[0] - pos[0], target[1] - pos[1]
    dist = (dx * dx + dy * dy) ** 0.5
    if dist < 1e-6:
        return pos

    ux, uy = dx / dist, dy / dist
    # 棋盘距离的缩减速率，取两轴分量的较大者
    rate = max(abs(ux), abs(uy)) or 1.0
    max_step = max(0.0, (d - stop_at) / rate)
    step = min(speed * dt, max_step, dist)
    if step <= 0.0:
        return pos

    return clamp_pos(pos[0] + ux * step, pos[1] + uy * step)


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

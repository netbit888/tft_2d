"""棋盘网格。

MVP 使用方格棋盘，坐标为 (x=列, y=行)，单位位置是浮点坐标。
将来若要换成金铲铲式的六边形棋盘，只需替换本文件的距离与移动实现。
"""

from __future__ import annotations

COLS = 7
ROWS = 4

# 每方占据的行：蓝色在上半场，红色在下半场。
# front = 靠近中线的那一排（放近战/坦克），back = 远离中线的那一排（放远程）。
TEAM_ROWS: dict[str, dict[str, int]] = {
    "blue": {"front": 1, "back": 0},
    "red": {"front": 2, "back": 3},
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

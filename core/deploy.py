"""摆位：玩家手动摆放优先，没摆的自动补齐。

第一版拖拽 UI 上线后，玩家摆过的棋子带 pos，其余交给自动规则；
将来要支持更多站位策略，只需要改这里，战斗层不用动。

手动摆放的全部规则（容量、半场、占格、交换）都收敛在 move_piece，
UI 只负责把鼠标位置翻译成目标位置，命令行和单测可以直接复用同一套规则。
"""

from __future__ import annotations

from dataclasses import dataclass

from .grid import AUTO_ROW_ORDER, COLS, ROWS, TEAM_ROWS
from .loader import load_units
from .player import MAX_BENCH, Piece, Player, unit_name

# 从中间向两侧展开，避免全都挤在一边
CENTER_ORDER = (3, 2, 4, 1, 5, 0, 6)


def _first_free_col(row: int, occupied: set[tuple[int, int]]) -> int | None:
    for col in CENTER_ORDER:
        if (col, row) not in occupied:
            return col
    return None


def _assign_auto(
    pieces: list[Piece], team: str, occupied: set[tuple[int, int]]
) -> list[tuple[Piece, tuple[int, int]]]:
    """给 pos 为 None 的棋子分配不冲突的格子：近战前排、远程后排。

    每方有四行可摆：近战从交火线那行开始，远程从其后排行带依次排；
    某一行排满 7 个自动退到下一行。
    """
    templates = load_units()
    rest = [p for p in pieces if p.pos is None]
    melee = [p for p in rest if templates[p.tid].attack_range <= 1]
    ranged = [p for p in rest if templates[p.tid].attack_range > 1]

    out: list[tuple[Piece, tuple[int, int]]] = []
    lo, hi = TEAM_ROWS[team]
    for group, slot in ((melee, "front"), (ranged, "back")):
        row_seq = AUTO_ROW_ORDER[team][slot]
        for p in group:
            col = None
            for row in row_seq:
                col = _first_free_col(row, occupied)
                if col is not None:
                    break
            if col is None:  # 兜底：半场里随便找空位
                for row in range(lo, hi + 1):
                    col = _first_free_col(row, occupied)
                    if col is not None:
                        break
            if col is None:
                continue
            occupied.add((col, row))
            out.append((p, (col, row)))
    return out


def auto_seat(pieces: list[Piece], team: str) -> list[tuple[Piece, tuple[int, int]]]:
    """把棋子排到站位上，返回 (棋子, 站位) 列表。

    已手动摆放的用玩家给的位置，其余按"近战前排、远程后排"自动补位，
    且不会覆盖玩家已经占用的格子。结果与 auto_place 完全一致，
    只是额外保留了棋子对象引用，供 UI 把"屏幕上的格子"反查回棋子做悬停详情。
    """
    occupied: set[tuple[int, int]] = set()
    seated: list[tuple[Piece, tuple[int, int]]] = []

    for p in pieces:
        if p.pos is not None:
            col, row = int(p.pos[0]), int(p.pos[1])
            seated.append((p, (col, row)))
            occupied.add((col, row))

    for p, (col, row) in _assign_auto(pieces, team, occupied):
        seated.append((p, (col, row)))

    return seated


def auto_place(pieces: list[Piece], team: str) -> list[dict]:
    """把棋子转换成 build_team 需要的布阵列表（由 auto_seat 派生）。"""
    placements: list[dict] = []
    for p, (col, row) in auto_seat(pieces, team):
        placements.append({"id": p.tid, "star": p.star, "pos": [col, row], "equip": p.equip})
    return placements


def assign_positions(pieces: list[Piece], team: str) -> None:
    """就地给 pos 为 None 的棋子补上确定位置（不覆盖已占格）。

    运营阶段调用后，棋盘上每个棋子的 pos 都非 None，使"显示位置 / 鼠标命中 /
    战斗站位"三者同源，避免补位上场的棋子看得见却拖不动。
    """
    occupied: set[tuple[int, int]] = set()
    for p in pieces:
        if p.pos is not None:
            occupied.add((int(p.pos[0]), int(p.pos[1])))
    for p, (col, row) in _assign_auto(pieces, team, occupied):
        p.pos = (col, row)


# ---------- 手动摆位 ----------


@dataclass
class MoveResult:
    """一次移动的结果。ok 表示是否真的动了，message 是可直接显示给玩家的提示。"""

    ok: bool
    message: str


def own_rows(team: str) -> tuple[int, ...]:
    """己方可以摆放的行（core 行号，每方 4 行）。"""
    lo, hi = TEAM_ROWS[team]
    return tuple(range(lo, hi + 1))


def piece_at(player: Player, col: int, row: int) -> Piece | None:
    """找出站在 (col, row) 的棋子，没有则返回 None（只查场上，不查备战席）。"""
    for p in player.board:
        if p.pos == (col, row):
            return p
    return None


def _locate(player: Player, piece: Piece) -> str | None:
    """判断棋子当前在场上还是备战席，都不在则返回 None。"""
    if any(p is piece for p in player.board):
        return "board"
    if any(p is piece for p in player.bench):
        return "bench"
    return None


def move_piece(
    player: Player,
    piece: Piece,
    dest: tuple[str, object],
    team: str = "blue",
) -> MoveResult:
    """把棋子移动到 dest，规则（容量 / 半场 / 占格）全部在这里判定。

    dest 有两种写法：
        ("board", (col, row))  放到棋盘的某个格子
        ("bench", index)       放到备战席的第 index 个槽位

    覆盖四种情形：备战席->空位、场上->空位、场上<->场上换位、备战席<->场上对调。
    """
    where = _locate(player, piece)
    if where is None:
        return MoveResult(False, "找不到这个棋子")

    kind, target = dest
    if kind == "board":
        return _move_to_board(player, piece, where, target, team)
    if kind == "bench":
        return _move_to_bench(player, piece, where, target)
    return MoveResult(False, "无效的目标位置")


def _move_to_board(
    player: Player,
    piece: Piece,
    where: str,
    target,
    team: str,
) -> MoveResult:
    col, row = int(target[0]), int(target[1])
    if not (0 <= col < COLS and 0 <= row < ROWS):
        return MoveResult(False, "超出棋盘范围")
    if row not in own_rows(team):
        return MoveResult(False, "只能放在自己半场")

    other = piece_at(player, col, row)
    if other is piece:
        return MoveResult(False, "")
    if other is not None:
        return _swap(player, piece, where, other, (col, row))

    if where == "bench" and len(player.board) >= player.board_cap:
        return MoveResult(False, f"上场人数已达上限 {player.board_cap}")

    if where == "bench":
        player.bench.remove(piece)
        player.board.append(piece)
    piece.pos = (col, row)
    return MoveResult(True, f"{unit_name(piece.tid)} 上场")


def _swap(
    player: Player,
    piece: Piece,
    where: str,
    other: Piece,
    cell: tuple[int, int],
) -> MoveResult:
    if where == "board":
        # 场上两个棋子互换站位，双方人数都不变
        piece.pos, other.pos = other.pos, piece.pos
        return MoveResult(True, f"{unit_name(piece.tid)} 与 {unit_name(other.tid)} 交换了位置")

    # 备战席 -> 已占用的格子：自己上场，把对方换回备战席。
    # 人数是净零变化（board +1-1、bench -1+1），所以不需要额外容量。
    player.bench.remove(piece)
    player.board.remove(other)
    player.board.append(piece)
    player.bench.append(other)
    piece.pos = cell
    other.pos = None
    return MoveResult(True, f"{unit_name(piece.tid)} 上场，{unit_name(other.tid)} 回到备战席")


def _move_to_bench(player: Player, piece: Piece, where: str, target) -> MoveResult:
    idx = max(0, int(target))

    if where == "board":
        if len(player.bench) >= MAX_BENCH:
            return MoveResult(False, "备战席已满，先卖掉或上场一个")
        player.board.remove(piece)
        player.bench.insert(min(idx, len(player.bench)), piece)
        piece.pos = None
        return MoveResult(True, f"{unit_name(piece.tid)} 已下场到备战席")

    # 备战席内部重排：拖到某个槽位就插到那里
    player.bench.remove(piece)
    player.bench.insert(min(idx, len(player.bench)), piece)
    return MoveResult(True, "")

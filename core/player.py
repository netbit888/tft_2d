"""玩家状态：血量、金币、场上棋子与备战席。

这里只存棋子的"规格"（tid + 星级），具体属性在开战前由 build_team 统一计算，
这样羁绊变化、数值改动都不需要同步维护两份数据。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .dataio import load_json
from .items import MAX_ITEMS_PER_PIECE, ItemInstance
from .loader import load_traits, load_units
from .pool import Pool

MAX_BENCH = 8  # 备战席容量
MAX_STAR = 3  # 星级上限
MAX_LEVEL = 10  # 等级上限


def _level_config() -> dict:
    """人口/经验曲线（level.json），由 core.dataio 统一缓存。"""
    return load_json("level.json")


def board_cap_for_level(level: int) -> int:
    """某等级的人口上限。"""
    levels = _level_config()["levels"]
    for row in levels:
        if row["level"] == level:
            return int(row["board_cap"])
    return int(levels[-1]["board_cap"])


def xp_needed_for_level(level: int) -> int:
    """升到某级需要的经验（该级门槛）。"""
    levels = _level_config()["levels"]
    for row in levels:
        if row["level"] == level:
            return int(row["xp_needed"])
    return int(levels[-1]["xp_needed"])


def upgrade_cost() -> int:
    return int(_level_config()["upgrade_cost"])


def upgrade_xp() -> int:
    return int(_level_config()["upgrade_xp"])


def odds_for_level(level: int) -> dict[int, int]:
    """某等级各费用棋子的刷新概率（百分比），返回 {费用: 百分比}。"""
    cfg = _level_config()
    raw = cfg.get("odds", {}).get(str(level))
    if raw is None:
        raw = cfg.get("odds", {}).get(str(MAX_LEVEL), [100, 0, 0])
    return {i + 1: int(v) for i, v in enumerate(raw)}


@dataclass(eq=False)
class Piece:
    """玩家拥有的一个棋子。

    pos 是玩家手动摆放的位置 (col, row)，为 None 时交给自动摆位。

    eq=False 很关键：两张同名同星、都没摆过的棋子是**两个不同的棋子**，
    必须按身份（is）而不是按值（==）比较，否则 remove/in 会认错对象，
    造成棋子上不了场甚至凭空消失。
    """

    tid: str
    star: int = 1
    pos: tuple[int, int] | None = None
    equip: list[ItemInstance] = field(default_factory=list)


@dataclass
class Player:
    name: str
    hp: int = 100
    gold: int = 0
    level: int = 1
    xp: int = 0
    board: list[Piece] = field(default_factory=list)  # 上场（最多 board_cap(level)）
    bench: list[Piece] = field(default_factory=list)  # 备战席
    pool: "Pool | None" = None  # 共享卡池，买卖时增减库存
    item_bench: list[ItemInstance] = field(default_factory=list)  # 装备栏
    alive: bool = True  # 8 人局淘汰标记
    locked: bool = False  # 商店锁定：本回合结束不刷新（下回合自动解锁）
    streak: int = 0  # 连胜/连败：>0 连胜、<0 连败、0 表示无连胜连败

    @property
    def is_alive(self) -> bool:
        return self.hp > 0 and self.alive

    @property
    def board_cap(self) -> int:
        return board_cap_for_level(self.level)

    @property
    def board_pop(self) -> int:
        """当前上场消耗的人口（普通棋子 1；远古巨龙等大型单位按自身 slots 计）。"""
        return sum(piece_slots(p) for p in self.board)

    def promote_from_bench(self) -> None:
        """备战席的棋子自动补位上场，直到人口放不下为止。"""
        while self.bench and self.board_pop + piece_slots(self.bench[0]) <= self.board_cap:
            self.board.append(self.bench.pop(0))

    def add_xp(self, amount: int) -> int:
        """加经验并自动升级，返回升到的等级数。"""
        self.xp += amount
        levels_gained = 0
        while self.level < MAX_LEVEL and self.xp >= xp_needed_for_level(self.level + 1):
            self.xp -= xp_needed_for_level(self.level + 1)
            self.level += 1
            levels_gained += 1
        return levels_gained


def unit_name(tid: str) -> str:
    return load_units()[tid].name


def unit_cost(tid: str) -> int:
    return load_units()[tid].cost


def piece_slots(piece: Piece) -> int:
    """该棋子上场占用的人口（弈子栏位）：默认 1，远古巨龙等大型单位为 2。"""
    return max(1, int(getattr(load_units()[piece.tid], "slots", 1)))


def piece_label(p: Piece) -> str:
    tpl = load_units()[p.tid]
    traits_data = load_traits()
    traits = "/".join(traits_data.get(t, {}).get("name", t) for t in tpl.traits)
    star = f"{p.star}星" if p.star > 1 else ""
    return f"{tpl.name}{star}({traits})"


def buy_xp(player: Player) -> str:
    """花金币升级（+4 经验 / 4 金币），返回提示文案。"""
    if player.level >= MAX_LEVEL:
        return "已达最高等级"
    cost = upgrade_cost()
    if player.gold < cost:
        return f"金币不足（升级需要 {cost} 金）"
    player.gold -= cost
    before = player.level
    gained = player.add_xp(upgrade_xp())
    if player.level > before:
        return f"升级到 {player.level} 级，人口上限 {player.board_cap}"
    return f"经验 +{upgrade_xp()}（{player.xp}/{xp_needed_for_level(player.level + 1)}）"


def try_upgrade(player: Player) -> list[str]:
    """三合一升星：3 个同名同星棋子合成 1 个高一星的。

    合成后的棋子会继承其中一个在场上棋子的站位；
    若三个都在备战席，则留在备战席（等场上有空位再上）。
    会循环检查，因此 3 个 2 星可以一路合成 3 星。
    """
    logs: list[str] = []
    while True:
        groups: dict[tuple[str, int], list[Piece]] = {}
        for p in list(player.board) + list(player.bench):
            groups.setdefault((p.tid, p.star), []).append(p)

        target = None
        for (tid, star), items in groups.items():
            if star < MAX_STAR and len(items) >= 3:
                target = (tid, star, items[:3])
                break
        if target is None:
            break

        tid, star, three = target
        anchor = next((p for p in three if p.pos is not None), None)
        # 升星前先收集三张棋子的装备，避免合成后凭空蒸发
        carry = [it for p in three for it in p.equip]
        for p in three:
            p.equip.clear()
            if p in player.board:
                player.board.remove(p)
            elif p in player.bench:
                player.bench.remove(p)

        merged = Piece(tid, star + 1)
        # 优先挂到新棋子上（单件上限 MAX_ITEMS_PER_PIECE），多余的放回装备栏。
        # 注意 item_bench 是 list，没有 .add()；直接 append 且不设上限，
        # 装备栏即使暂时放满也绝不丢装备（超出部分会在使用/合成腾出空位后重新可见）。
        merged.equip = carry[:MAX_ITEMS_PER_PIECE]
        for it in carry[MAX_ITEMS_PER_PIECE:]:
            player.item_bench.append(it)
        if anchor is not None:
            merged.pos = anchor.pos
        # 合成腾出了空位，优先留在场上；只有人口放不下且备战席还有位置时才回备战席
        if (
            anchor is not None
            or player.board_pop + piece_slots(merged) <= player.board_cap
            or len(player.bench) >= MAX_BENCH
        ):
            player.board.append(merged)
        else:
            player.bench.append(merged)
        logs.append(f"{unit_name(tid)} 升到 {star + 1} 星")

    if logs:
        player.promote_from_bench()  # 合成腾出的空位立刻补上
    return logs


def next_star_if_buy(player: Player, tid: str) -> int:
    """模拟“再买一张 tid”后能否触发三合一，返回合成到的目标星级（2 或 3）。

    只读统计、不改动任何状态；合成规则与 try_upgrade 完全一致。
    备战席已满（买了也放不下）或不会触发合成时返回 0。
    """
    if len(player.bench) >= MAX_BENCH:
        return 0
    n1 = n2 = 0
    for p in list(player.board) + list(player.bench):
        if p.tid == tid:
            if p.star == 1:
                n1 += 1
            elif p.star == 2:
                n2 += 1
    n1 += 1  # 假想买到这一张（新棋子都是 1 星）
    up2 = n1 // 3       # 1 星三合一，能出几个 2 星
    n2 += up2
    n1 %= 3
    if n2 >= 3:         # 2 星再合成 3 星
        return 3
    return 2 if up2 > 0 else 0

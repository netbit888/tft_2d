"""对局状态机：回合推进、战斗结算、扣血与胜负。

支持两种模式：
- 1v1（默认）：玩家（你）对人机（电脑），各 100 血。
- 8 人局（num_players=8）：8 名玩家共享卡池，每回合两两配对打 1v1，败者扣血、淘汰。

战斗内核（Combat）本身支持 N 队混战，但自走棋的"8 人局"仍是每次 1v1 的两两配对，
这样能最大化复用战斗回放与结算逻辑。
"""

from __future__ import annotations

from .combat import Combat
from .deploy import assign_positions, auto_place
from .items import FIRST_DROP_ROUND, drop_item
from .loader import build_team
from .models import CombatResult
from .player import Player, buy_xp
from .pool import Pool
from .rng import Rng
from .shop import Shop


class Game:
    START_GOLD = 10
    ROUND_INCOME = 5
    BASE_DAMAGE = 3  # 每回合固定伤害，避免僵持
    DAMAGE_PER_UNIT = 3  # 对方每个存活单位的伤害
    MAX_ROUND = 30

    # ---------- 经济与经验 ----------
    NATURAL_XP = 2  # 每回合开始自动获得的经验（不花钱也会慢慢涨人口）
    INTEREST_PER = 10  # 每存 10 金，回合结束 +1 利息
    MAX_INTEREST = 5  # 利息上限

    @classmethod
    def interest_of(cls, gold: int) -> int:
        """按当前金币计算利息（每 10 金 +1，上限 5）。"""
        return min(cls.MAX_INTEREST, int(gold) // cls.INTEREST_PER)

    def __init__(self, seed: int | None = None, num_players: int = 1) -> None:
        self.rng = Rng(seed)
        self.pool = Pool.create()  # 所有玩家共享卡池
        self.round = 1

        # num_players 语义：1 = 1v1（你 + 1 电脑），8 = 8 人局（你 + 7 电脑）
        self.num_players = max(2, int(num_players))  # 至少 2 人（1v1）
        if num_players == 1:
            self.num_players = 2

        # p1 = 玩家本人，其余是 AI（1v1 时对手就叫"电脑"，8 人局从"电脑2"开始）
        if self.num_players == 2:
            names = ["你", "电脑"]
        else:
            names = ["你"] + [f"电脑{i}" for i in range(2, self.num_players + 1)]
        self.players: list[Player] = [Player(name, pool=self.pool) for name in names]
        self.shops: list[Shop] = [
            Shop(self.rng, self.pool) for _ in range(self.num_players)
        ]

        # 1v1 兼容别名：you 永远指向玩家本人，enemy 指向当前对手
        self.you = self.players[0]
        self.enemy = self.players[1]
        self.shop_you = self.shops[0]
        self.shop_enemy = self.shops[1]

        self.pairings: list[tuple[int, int]] = []  # 本回合的 (玩家索引) 配对
        self.current_opponent: int = 1  # 玩家本人的当前对手索引
        self.last_ai_log: list[str] = []

    # ---------- 回合流程 ----------

    def begin_round(self) -> None:
        for i, p in enumerate(self.players):
            if not p.is_alive:
                continue
            # 1) 自然经验增长：每回合 +2，不花钱也会慢慢涨人口
            p.add_xp(self.NATURAL_XP)
            # 2) 利息：按本回合开始时的金币结算（每 10 金 +1，上限 5）
            if self.round > 1:
                p.gold += self.interest_of(p.gold)
            # 3) 固定收入（第 1 回合发初始金币）
            p.gold += self.START_GOLD if self.round == 1 else self.ROUND_INCOME
            # 4) 刷新商店（锁定时跳过，锁定只持续一回合，用完自动解锁）
            if not p.locked:
                self.shops[i].refresh(p.level)
            p.locked = False
            assign_positions(p.board, "blue" if i == 0 else "red")

    def prepare_battle(self) -> None:
        """开战前把备战席棋子补进场上空位。"""
        for p in self.players:
            if p.is_alive:
                p.promote_from_bench()

    def make_pairings(self) -> list[tuple[int, int]]:
        """为存活玩家生成两两配对（轮转法，尽量避免重复）。

        玩家本人（索引 0）优先与一名存活 AI 配对；其余存活 AI 两两配对。
        返回 [(a, b), ...]，a/b 是 players 索引。
        """
        alive = [i for i, p in enumerate(self.players) if p.is_alive]
        if len(alive) < 2:
            return []

        pairings: list[tuple[int, int]] = []
        rest = list(alive)
        # 玩家本人先配对
        if 0 in rest:
            rest.remove(0)
            if rest:
                self.rng.shuffle(rest)
                self.current_opponent = rest[0]
                pairings.append((0, rest[0]))
                rest = rest[1:]
        # 剩余 AI 两两配对
        self.rng.shuffle(rest)
        while len(rest) >= 2:
            a, b = rest.pop(), rest.pop()
            pairings.append((a, b))
        # 奇数个存活 AI：落单的轮空
        self.pairings = pairings
        return pairings

    def fight(self) -> Combat | None:
        """玩家本人 vs 当前对手的一场 1v1。"""
        a, b = 0, self.current_opponent
        pa, pb = self.players[a], self.players[b]
        if not pa.board or not pb.board:
            return None
        blue = build_team(auto_place(pa.board, "blue"), "blue")
        red = build_team(auto_place(pb.board, "red"), "red")
        return Combat(blue, red, seed=self.rng.randint(0, 2**31 - 1))

    def fight_pair(self, a: int, b: int) -> Combat | None:
        """两个玩家之间的 1v1（用于 AI 之间的对局）。"""
        pa, pb = self.players[a], self.players[b]
        if not pa.board or not pb.board:
            return None
        blue = build_team(auto_place(pa.board, "blue"), "blue")
        red = build_team(auto_place(pb.board, "red"), "red")
        return Combat(blue, red, seed=self.rng.randint(0, 2**31 - 1))

    @classmethod
    def damage_of(cls, survivors: int) -> int:
        return cls.BASE_DAMAGE + survivors * cls.DAMAGE_PER_UNIT

    def settle(self, result: CombatResult | None) -> str:
        """结算玩家本人 vs 当前对手的战斗。"""
        return self.settle_pair(0, self.current_opponent, result)

    def settle_pair(self, a: int, b: int, result: CombatResult | None) -> str:
        """结算任意两个玩家（a/b 是索引）的战斗，败者扣血。返回描述。"""
        pa, pb = self.players[a], self.players[b]
        if result is None:
            if not pa.board and not pb.board:
                return "双方都没有上场棋子，本回合空过"
            if not pa.board:
                dmg = self.damage_of(len(pb.board))
                pa.hp = max(0, pa.hp - dmg)
                return f"{pa.name} 未上场棋子，受到 {dmg} 点伤害"
            dmg = self.damage_of(len(pa.board))
            pb.hp = max(0, pb.hp - dmg)
            return f"{pb.name} 未上场棋子，受到 {dmg} 点伤害"

        if result.winner == "blue":
            dmg = self.damage_of(result.survivors.get("blue", 0))
            pb.hp = max(0, pb.hp - dmg)
            return f"{pa.name} 赢了，{pb.name} 受到 {dmg} 点伤害"
        if result.winner == "red":
            dmg = self.damage_of(result.survivors.get("red", 0))
            pa.hp = max(0, pa.hp - dmg)
            return f"{pb.name} 赢了，{pa.name} 受到 {dmg} 点伤害"
        return "本回合平局，双方都不掉血"

    def drop_items_for_round(self) -> list[tuple[int, str]]:
        """本回合所有存活玩家掉落装备，返回 [(玩家索引, 装备id), ...]。"""
        if self.round < FIRST_DROP_ROUND:
            return []
        drops = []
        for i, p in enumerate(self.players):
            if not p.is_alive:
                continue
            item = drop_item(self.rng)
            if item is not None:
                p.item_bench.append(
                    __import__("core.items", fromlist=["ItemInstance"]).ItemInstance(item)
                )
                drops.append((i, item))
        return drops

    def run_round(self) -> dict:
        """跑完整一个回合（8 人局）：运营 → 配对 → 战斗 → 结算 → 掉落。

        返回本回合的摘要信息（供渲染层展示）。
        """
        self.begin_round()
        self.make_pairings()

        results = []
        for a, b in self.pairings:
            combat = self.fight_pair(a, b)
            result = combat.run() if combat is not None else None
            msg = self.settle_pair(a, b, result)
            results.append((a, b, result, msg))

        # 淘汰判定
        for p in self.players:
            if p.hp <= 0:
                p.alive = False

        drops = self.drop_items_for_round()
        self.round += 1
        return {"results": results, "drops": drops}

    # ---------- 胜负 ----------

    def is_over(self) -> bool:
        alive = [p for p in self.players if p.is_alive]
        if not self.players[0].is_alive:
            return True
        if len(alive) <= 1:
            return True
        return self.round > self.MAX_ROUND

    def winner(self) -> str:
        """返回对局结果描述。"""
        you = self.players[0]
        alive = [p for p in self.players if p.is_alive]
        if not you.is_alive:
            return "你被淘汰了"
        if len(alive) == 1 and alive[0] is you:
            return "你赢了！吃鸡成功"
        # 按血量排名
        ranked = sorted(self.players, key=lambda p: (-p.hp, -p.level))
        return f"打满回合，你第 {ranked.index(you) + 1} 名"


def ai_upgrade(player: Player) -> str | None:
    """AI 升级节奏：金币充裕时买经验。"""
    return buy_xp(player)

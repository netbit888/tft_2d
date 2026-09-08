"""商店与运营操作。

第一版使用无限卡池（不做公共卡池与抽取概率表），按费用权重随机，
够用且不会让运气波动过大。后续接真实抽卡概率时只需替换 refresh()。
"""

from __future__ import annotations

from dataclasses import dataclass

from .loader import load_units
from .player import MAX_BENCH, Piece, Player, odds_for_level, try_upgrade, unit_cost, unit_name
from .rng import Rng

REFRESH_COST = 2


@dataclass
class ShopItem:
    tid: str
    cost: int
    sold: bool = False


class Shop:
    SIZE = 5

    def __init__(self, rng: Rng, pool=None) -> None:
        self.rng = rng
        self.pool = pool  # 共享卡池；为 None 时退化为无限卡池
        self.slots: list[ShopItem] = []
        self.refresh(1)

    def refresh(self, level: int = 1) -> None:
        """按等级的费用概率抽卡：先抽费用，再从该费用池里随机选棋子。

        等级越高，高费棋子出现概率越大（见 data/level.json 的 odds）。
        """
        templates = load_units()
        ids = self.pool.available() if self.pool is not None else list(templates.keys())
        if not ids:
            self.slots = []
            return

        odds = odds_for_level(level)  # {费用: 百分比}
        costs = [c for c, w in odds.items() if w > 0]
        weights = [odds[c] for c in costs]

        self.slots = []
        for _ in range(self.SIZE):
            cost = self.rng.weighted_choice(costs, weights)
            candidates = [t for t in ids if templates[t].cost == cost]
            if not candidates:  # 该费用无库存时兜底
                candidates = ids
            tid = self.rng.choice(candidates)
            self.slots.append(ShopItem(tid=tid, cost=0))
        for item in self.slots:
            item.cost = unit_cost(item.tid)

    def available(self) -> list[tuple[int, ShopItem]]:
        return [(i, it) for i, it in enumerate(self.slots) if not it.sold]


def refresh_shop(player: Player, shop: Shop) -> str:
    if player.gold < REFRESH_COST:
        return f"金币不足，刷新需要 {REFRESH_COST} 金"
    player.gold -= REFRESH_COST
    player.locked = False  # 手动刷新后锁定失效
    shop.refresh(player.level)
    return f"已刷新商店（-{REFRESH_COST} 金）"


def buy(player: Player, shop: Shop, index: int) -> str:
    """购买：棋子一律进入备战席，上场由玩家拖拽决定。

    开战时未上场的会自动补位（见 Game.prepare_battle），不会因忘拖而吃亏。
    """
    if not (0 <= index < len(shop.slots)):
        return "没有这个位置"
    item = shop.slots[index]
    if item.sold:
        return "该位置已售出"
    if player.gold < item.cost:
        return f"金币不足（需要 {item.cost} 金）"
    if len(player.bench) >= MAX_BENCH:
        return "备战席已满，先卖掉或上场一个"

    pool = shop.pool if shop.pool is not None else player.pool
    if pool is not None and not pool.take(item.tid):
        # 对手先一步买光了
        item.sold = True
        return f"{unit_name(item.tid)} 已被抢光了"

    player.gold -= item.cost
    item.sold = True
    player.bench.append(Piece(item.tid))

    msg = f"购入 {unit_name(item.tid)}（-{item.cost} 金）"
    upgrades = try_upgrade(player)
    if upgrades:
        msg += "，" + "、".join(upgrades) + "！"
    else:
        msg += "，已放入备战席"
    return msg


def sell_piece(player: Player, piece: Piece) -> str:
    """卖出指定棋子（按对象而非序号），UI 拖拽用。

    高星棋子由多张合成，卖出时按 3^(星级-1) 返还金币并归还卡池。
    """
    if piece in player.board:
        player.board.remove(piece)
    elif piece in player.bench:
        player.bench.remove(piece)
    else:
        return "找不到这个棋子"

    copies = 3 ** (piece.star - 1)  # 1星=1张，2星=3张，3星=9张
    gold = unit_cost(piece.tid) * copies
    player.gold += gold
    if player.pool is not None:
        player.pool.give(piece.tid, copies)

    # 装备回到装备栏（高级装备拆回两件基础件）
    from .items import is_base_item

    for it in piece.equip:
        if is_base_item(it.item_id):
            player.item_bench.append(it)
        elif it.components:
            from .items import ItemInstance

            for c in it.components:
                player.item_bench.append(ItemInstance(c))
    piece.equip.clear()

    star = f"{piece.star}星" if piece.star > 1 else ""
    return f"卖出 {unit_name(piece.tid)}{star}（+{gold} 金，卡池 +{copies}）"


def sell(player: Player, index: int) -> str:
    """卖出场上第 index 个棋子（从 1 开始计），全额返还。"""
    if not (1 <= index <= len(player.board)):
        return "没有这个棋子"
    piece = player.board.pop(index - 1)
    gold = unit_cost(piece.tid)
    player.gold += gold
    player.promote_from_bench()  # 备战席自动补位
    return f"卖出 {unit_name(piece.tid)}（+{gold} 金）"

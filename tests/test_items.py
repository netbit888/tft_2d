"""装备系统改动的不变量：
- 卖出带成装的棋子：成装整件回装备栏，不再拆回两件基础件；
- first_combine_with：按顺序找第一件可合成的基础件（顺序确定、结果可预期）；
- 装备栏背包不设容量上限，list 可无限扩展。
"""

from __future__ import annotations

from core import Game, buy
from core.items import ItemInstance, first_combine_with, item_name, load_items
from core.shop import sell_piece

# data/items.json 中稳定的基础件与成装样例（与数值无关，仅用结构）
BASE = list(load_items()["base"])
SWORD, BOW = "sword", "bow"
COMBINED = "sword+bow"  # 破甲弓：由长剑 + 反曲弓合成


def test_sell_piece_returns_combined_item_intact():
    """卖出带成装的棋子：成装整件回装备栏，不拆回两件基础件。"""
    g = Game(seed=3)
    p = g.you
    p.gold = 100

    slot = next(s for s in g.shops[0].slots if not s.sold)
    buy(p, g.shops[0], g.shops[0].slots.index(slot))
    piece = p.bench[0]
    piece.equip.append(ItemInstance(COMBINED))  # 成装挂在身上

    msg = sell_piece(p, piece)

    assert item_name(COMBINED) in msg, f"提示里应出现成装名：{msg}"
    ids = [it.item_id for it in p.item_bench]
    assert ids == [COMBINED], f"回栏装备应为成装本身，实际 {ids}"


def test_first_combine_with_picks_first_mate_in_order():
    """first_combine_with 应返回给定顺序中第一件可合成的件。"""
    advanced = "wand+chain"  # 成装不是基础件，应被跳过
    wand, chain = "wand", "chain"
    assert SWORD and BOW in BASE

    assert first_combine_with(SWORD, [advanced, BOW]) == BOW, "应跳过成装取第一可合成基础件"
    assert first_combine_with(SWORD, [BOW, wand]) == BOW, "顺序靠前者优先（结果确定）"
    assert first_combine_with(SWORD, [advanced, chain, wand]) == chain
    assert first_combine_with(SWORD, [advanced, advanced]) is None
    assert first_combine_with(COMBINED, [BOW]) is None, "成装不再参与合成探测"


def test_item_bench_is_unbounded():
    """装备栏是普通 list：可无限 append，不带 12 格硬上限。"""
    g = Game(seed=7)
    g.you.gold = 0
    for i in range(40):
        g.you.item_bench.append(ItemInstance(SWORD if i % 2 else BOW))
    assert len(g.you.item_bench) == 40, "装备栏背包不应被容量上限截断"

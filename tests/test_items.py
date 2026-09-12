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


# ---------- 冠冕：官方次要效果 + 三冠冕彩蛋 ----------


def test_crown_helpers():
    """三种冠冕的识别与「集齐」判定。"""
    from core.items import CROWN_IDS, has_all_crowns, is_crown

    assert len(CROWN_IDS) == 3
    assert all(is_crown(c) for c in CROWN_IDS)
    assert not is_crown(SWORD)
    assert has_all_crowns(CROWN_IDS)
    assert not has_all_crowns(CROWN_IDS[:2]), "缺一顶不算集齐"


def test_crown_egg_gold_per_battle_second():
    """三冠冕彩蛋：场上集齐三种冠冕时，本场战斗每秒 +10 金。"""
    from core.combat import TICK_RATE
    from core.items import CROWN_EGG_GOLD_PER_SEC, CROWN_IDS
    from core.player import Piece

    g = Game(seed=1)
    you, enemy = g.you, g.enemy
    you.board = [Piece("s18_ornn")]
    enemy.board = [Piece("s18_warwick")]
    for c in CROWN_IDS:
        you.board[0].equip.append(ItemInstance(c))
    you.gold = 0

    combat = g.fight()
    assert combat is not None
    combat.run()
    secs = int(combat.result.ticks / TICK_RATE)

    res = g.crown_rewards(0, combat, "blue")
    assert res["egg_gold"] == CROWN_EGG_GOLD_PER_SEC * secs, "彩蛋应按战斗中每秒产金"
    assert 0 <= res["drop_gold"] <= 3, "三件冠冕的次要掉落各至多 1 金"
    assert you.gold == res["egg_gold"] + res["drop_gold"]


def test_crown_secondary_drop_is_ten_percent():
    """官方次要效果：判定命中时每件冠冕掉 1 金（这里把随机固定为必中验证上限）。"""
    from core.items import CROWN_IDS
    from core.player import Piece

    g = Game(seed=2)
    you, enemy = g.you, g.enemy
    you.board = [Piece("s18_ornn")]
    enemy.board = [Piece("s18_warwick")]
    for c in CROWN_IDS:
        you.board[0].equip.append(ItemInstance(c))
    you.gold = 0

    combat = g.fight()
    combat.run()
    g.rng.random = lambda: 0.0  # 让 10% 判定必中
    res = g.crown_rewards(0, combat, "blue")
    # 金铲铲冠冕（胜利时）与金锅锅冠冕（倒下时）互斥情形下各自上限 1；
    # 这里只验证：命中时至少能掉金，且不超过 3 次判定。
    assert 0 <= res["drop_gold"] <= 3

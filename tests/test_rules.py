"""核心规则不变量：经济、人口曲线、卡池守恒。

这些都是改动内核后最容易悄悄被破坏、但肉眼看不出来的东西。
"""

from __future__ import annotations

from core import Game, buy, load_units, sell
from core.player import board_cap_for_level, odds_for_level, upgrade_cost, upgrade_xp, xp_needed_for_level


def test_round1_income_gives_start_gold():
    g = Game(seed=1)
    assert g.you.gold == 0 and g.enemy.gold == 0
    g.begin_round()
    assert g.you.gold == g.START_GOLD
    assert g.enemy.gold == g.START_GOLD


def test_level_curve_is_monotonic_and_valid():
    caps = [board_cap_for_level(lv) for lv in range(1, 10)]
    assert caps == sorted(caps) and caps[0] >= 1
    for lv in range(1, 10):
        assert sum(odds_for_level(lv).values()) == 100
        assert xp_needed_for_level(lv) >= 0
    assert upgrade_cost() > 0 and upgrade_xp() > 0


def test_pool_conservation_after_full_8p_match():
    """整局结束后：玩家持有 + 卡池剩余 == 卡池初始总量（每个棋子独立校验）。"""
    g = Game(seed=5, num_players=8)
    g.play_auto_match()
    for tid in load_units():
        held = 0
        for p in g.players:
            for piece in p.board + p.bench:
                if piece.tid == tid:
                    held += 3 ** (piece.star - 1)  # 1/2/3 星分别吃掉 1/3/9 张
        assert g.pool.count(tid) + held == g.pool.capacity[tid], (
            f"{tid} 卡池不守恒：剩余 {g.pool.count(tid)} + 持有 {held}"
            f" != 初始 {g.pool.capacity[tid]}"
        )


def test_buy_then_sell_returns_to_pool():
    g = Game(seed=2)
    p, shop = g.you, g.shops[0]
    p.gold = 100
    slot = next(s for s in shop.slots if s is not None and s.cost == 1)
    tid = slot.tid
    before = g.pool.count(tid)

    buy(p, shop, shop.slots.index(slot))
    assert p.bench, "买了却没有上备战席"
    assert g.pool.count(tid) == before - 1

    p.promote_from_bench()  # 命令行式直接上场
    sell(p, 1)
    assert g.pool.count(tid) == before, "卖出后应归还卡池"

"""3 星 5 费的可达成性验证（确定性断言，可进 CI）。

配套的蒙特卡洛概率表见 tools/roll_5cost.py；这里只验证“机制结论”级别的
硬事实，避免在单测里跑大样本概率（太慢且不稳）。

核心结论（由真实代码得出）：
  1. 10 级 5 费档概率 35%，且卡池每种 5 费只有 9 张、3 星需 9 张；
  2. 满池 + 足够金币时，一定能 D 出 3 星 5 费（正概率且事实上可达）；
  3. 目标若被抢走 ≥1 张，3 星 5 费不可能（硬上限，概率恒 0）。
"""

from __future__ import annotations

from core import (
    REFRESH_COST,
    Player,
    Pool,
    Rng,
    Shop,
    buy,
    load_units,
    refresh_shop,
)
from core.player import odds_for_level

TARGET = "s18_elderdragon"
FIVE_COST_IDS = [tid for tid, tpl in load_units().items() if tpl.cost == 5]


def _pool(target_left: int = 9, others_to_zero: int = 0) -> Pool:
    pool = Pool.create()
    pool.remaining[TARGET] = min(target_left, pool.capacity[TARGET])
    others = [t for t in FIVE_COST_IDS if t != TARGET]
    for t in others[:others_to_zero]:
        pool.remaining[t] = 0
    return pool


def _roll_to_star3(gold: int, seed: int, target_left: int = 9, others_to_zero: int = 0) -> bool:
    """预算内只 D 目标，返回是否达成 3 星。"""
    rng = Rng(seed)
    pool = _pool(target_left, others_to_zero)
    player = Player("tester", level=10, gold=gold, pool=pool)
    shop = Shop(rng, pool)
    copies = 0
    while player.gold >= REFRESH_COST and copies < 9:
        refresh_shop(player, shop)
        for idx, item in shop.available():
            if item.tid == TARGET and player.gold >= item.cost:
                buy(player, shop, idx)
                copies += 1
    return any(p.tid == TARGET and p.star == 3 for p in player.board + player.bench)


def test_level10_odds_have_35_percent_five_cost():
    odds = odds_for_level(10)
    assert odds[5] == 35
    assert sum(odds.values()) == 100
    assert odds == {1: 3, 2: 7, 3: 18, 4: 37, 5: 35}


def test_five_cost_pool_is_nine_and_star3_needs_nine():
    # 卡池每种 5 费 9 张、3 星需同棋子 9 张 → 想 3 星必须全拿
    pool = Pool.create()
    assert pool.capacity[TARGET] == 9
    assert len(FIVE_COST_IDS) == 10


def test_full_pool_with_enough_gold_reaches_star3():
    # 满池 + 充足预算：给定种子下应能买到 9 张并合成 3 星（正概率、事实上可达）
    hits = sum(_roll_to_star3(2000, seed) for seed in range(20))
    assert hits > 0, "满池 + 充足预算下应当能 D 出 3 星 5 费"


def test_contested_target_never_reaches_star3():
    # 目标被抢走哪怕 1 张（只剩 8 张），永远无法 3 星
    for left in (8, 5, 1):
        hits = sum(_roll_to_star3(5000, seed, target_left=left) for seed in range(20))
        assert hits == 0, f"目标只剩 {left} 张时不该能 3 星"


def test_pool_conservation_during_rolling():
    # 滚动过程中卡池守恒：买走的张数 + 剩余 = 初始 9
    rng = Rng(7)
    pool = _pool()
    player = Player("tester", level=10, gold=500, pool=pool)
    shop = Shop(rng, pool)
    bought = 0
    while player.gold >= REFRESH_COST and bought < 9:
        refresh_shop(player, shop)
        for idx, item in shop.available():
            if item.tid == TARGET and player.gold >= item.cost:
                buy(player, shop, idx)
                bought += 1
    assert pool.count(TARGET) + bought == 9

"""人机决策。

策略：随机购买，但优先买能凑成羁绊的棋子；金币充裕时升级；掉落装备自动装备到主力。
纯随机会因为完全不凑羁绊而弱得离谱，加这一点点倾向就能让对局有来有回。
"""

from __future__ import annotations

from .items import MAX_ITEMS_PER_PIECE, combine_key, item_name
from .loader import load_traits, load_units
from .player import MAX_BENCH, MAX_LEVEL, Player, buy_xp
from .rng import Rng
from .shop import Shop, buy
from .traits import count_traits_from_tids, trait_thresholds

MAX_BUYS_PER_ROUND = 10


def _reached_level(trait_def: dict, count: int) -> int:
    """当前人数命中的最高档位（跨过任一档即算一次“升档”）。"""
    return max([lv for lv in trait_thresholds(trait_def) if count >= lv], default=0)


def synergy_gain(tids: list[str], new_tid: str) -> float:
    """买入 new_tid 能带来多少羁绊收益。

    激活新档位权重最高，只是让已有羁绊多一层则权重较低。
    （官方羁绊档位同样计入——虽然本作效果未实装，仍让 AI 保持“凑羁绊”的运营习惯。）
    """
    templates = load_units()
    traits_data = load_traits()
    before = count_traits_from_tids(tids, templates)
    after = count_traits_from_tids(tids + [new_tid], templates)

    gain = 0.0
    for t in set(before) | set(after):
        trait_def = traits_data.get(t)
        if trait_def is None:
            continue
        b = _reached_level(trait_def, before.get(t, 0))
        a = _reached_level(trait_def, after.get(t, 0))
        if a > b:
            gain += 10.0  # 激活/升档
        elif after.get(t, 0) > before.get(t, 0):
            gain += 1.0  # 只是多一层
    return gain


def ai_take_turn(player: Player, shop: Shop, rng: Rng) -> list[str]:
    """AI 运营一个回合，返回操作记录（便于复盘它到底买了什么）。"""
    log: list[str] = []

    for _ in range(MAX_BUYS_PER_ROUND):
        board_full = player.board_pop >= player.board_cap  # 大型单位占多个人口，按人口判断
        bench_full = len(player.bench) >= MAX_BENCH
        if board_full and bench_full:
            break

        owned = [p.tid for p in player.board] + [p.tid for p in player.bench]
        scored = []
        for i, it in shop.available():
            if it.cost > player.gold:
                continue
            count = owned.count(it.tid)
            if board_full and count == 0:
                # 场上满了：只追同名棋子去凑升星，不再买新棋子占备战席
                continue
            # 能立刻升星 > 正在凑同名 > 纯羁绊收益
            score = 100.0 if count >= 2 else (30.0 if count == 1 else 0.0)
            score += synergy_gain(owned, it.tid)
            # 收益相同时用随机数打破平局，保证"随机但有倾向"
            scored.append((score, rng.random(), i))

        if not scored:
            break
        scored.sort(reverse=True)
        index = scored[0][2]
        msg = buy(player, shop, index)
        player.promote_from_bench()  # AI 买完直接上场（玩家则是手动拖）
        log.append(msg)

    return log


def ai_equip(player: Player, rng: Rng) -> list[str]:
    """AI 把装备栏的装备合成/装备到场上棋子，返回操作记录。"""
    log: list[str] = []

    # 先尝试两两合成
    while len(player.item_bench) >= 2:
        combined = False
        for i in range(len(player.item_bench)):
            for j in range(i + 1, len(player.item_bench)):
                key = combine_key(player.item_bench[i].item_id, player.item_bench[j].item_id)
                if key:
                    a, b = player.item_bench[i], player.item_bench[j]
                    player.item_bench.remove(a)
                    player.item_bench.remove(b)
                    from .items import ItemInstance

                    player.item_bench.append(ItemInstance(key))
                    log.append(f"合成 {item_name(key)}")
                    combined = True
                    break
            if combined:
                break
        if not combined:
            break

    # 装备到场上主力（按攻击力排序，优先给输出位）
    if player.board:
        main = max(player.board, key=lambda p: load_units()[p.tid].ad * p.star)
        while player.item_bench and len(main.equip) < MAX_ITEMS_PER_PIECE:
            it = player.item_bench.pop(0)
            main.equip.append(it)
            log.append(f"{item_name(it.item_id)} 装备到 {main.tid}")
    return log


def ai_upgrade_check(player: Player, round_num: int = 1) -> str | None:
    """AI 升级节奏：按回合推进目标等级，落后越多越激进。

    策略（模拟金铲铲的经济决策）：
    - 目标等级随回合递增（前期 4 级、中期 6 级、后期 8~10 级）；
    - 只落后 1 级：守住 50 金吃满利息，不急着升；
    - 落后 2 级及以上：激进冲级，只保留 10 金买棋子。
    """
    if round_num <= 3:
        target = 4
    elif round_num <= 6:
        target = 6
    elif round_num <= 9:
        target = 8
    elif round_num <= 12:
        target = 9
    else:
        target = 10
    target = min(MAX_LEVEL, target)

    while player.level < target and player.gold >= 4:
        behind = target - player.level
        # 落后 1 级守利息线（50），落后 2+ 级激进（保留 10 金买棋子）
        keep = 50 if behind <= 1 else 10
        if player.gold - 4 < keep:
            break
        buy_xp(player)
    return None
